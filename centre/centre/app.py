# -*- coding: utf-8 -*-
"""
Serveur web du Centre (Starlette).

Sécurité, dans l'ordre pour chaque requête :
  1. Hôte : seuls 127.0.0.1, localhost et les noms autorisés (protège contre le « DNS rebinding »).
  2. Écritures : en-tête « X-Centre: 1 » obligatoire et Origin identique à l'hôte s'il est présent.
  3. Session : tout exige une session valide, sauf la page de connexion et ses fichiers.
"""

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .config import Config
from .service import Centre, ErreurService
from .verrou import ErreurVerrou, Verrou
from .couts import ErreurCouts, IA, TARIFS_REFERENCE, libelle_ia
from .conversations import ErreurConversation
from .journal import lire_fin_journal, masquer
from .salles import ErreurSalle, MODELES_CREW, SALLES
from .tiroir import ErreurTiroir
from .voix import ErreurVoix
from .rappels import ErreurRappel
from . import bulletin as bulletin_mod, departements as departements_mod, gardien as gardien_mod, rapport as rapport_mod
from . import sauvegarde as sauvegarde_mod, verite as verite_mod

journal = logging.getLogger("centre")

DOSSIER_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
COOKIE = "centre_session"

# Fichiers servis sans session (nécessaires à la page de connexion et à l'installation PWA).
PUBLICS = {"/connexion", "/manifest.webmanifest", "/sw.js", "/s/style.css", "/s/connexion.js",
           "/s/icone-192.png", "/s/icone-512.png", "/s/icone.svg",
           "/api/verrou", "/api/connexion"}
PAGES = {  # chemin -> fichier du dossier static
    "/connexion": "connexion.html", "/manifest.webmanifest": "manifest.webmanifest", "/sw.js": "sw.js",
    "/": "app.html",
}
ENTETES_SECURITE = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
                                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def _entete(scope, nom):
    nom = nom.lower().encode()
    for k, v in scope.get("headers", []):
        if k == nom:
            return v.decode("latin-1")
    return ""


class Garde:
    """Middleware ASGI : hôte, CSRF, session."""

    def __init__(self, app, verrou, config):
        self.app, self.verrou, self.config = app, verrou, config
        p = config.port
        self.locaux = {f"127.0.0.1:{p}", f"localhost:{p}"}
        self.hotes = self.locaux | set(config.hotes_autorises)

    def _hote_ok(self, hote):
        hote = hote.lower()
        return hote in self.hotes or hote.split(":")[0] in self.config.hotes_autorises

    def _identite_ok(self, scope, hote):
        """Accès distant : l'identité Tailscale (ajoutée par « tailscale serve ») est exigée. Une exposition publique par
        erreur (« tailscale funnel », redirection de port…) n'apporte pas cet en-tête : elle est donc refusée."""
        if hote.lower() in self.locaux or not self.config.exiger_identite_tailscale:
            return True
        login = _entete(scope, "tailscale-user-login").strip().lower()
        if not login:
            return False
        autorises = self.config.utilisateurs_tailscale
        return not autorises or login in autorises

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            hote = _entete(scope, "host")
            scope["centre_distant"] = hote.lower() not in self.locaux
            if scope["type"] == "http" and self._hote_ok(hote):
                send = self._avec_entetes(send, hote, scope["centre_distant"])
        if scope["type"] == "websocket":
            return await self._websocket(scope, receive, send)
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        hote = _entete(scope, "host")
        chemin = scope["path"]
        methode = scope["method"]
        if not self._hote_ok(hote):
            return await self._refuser(scope, receive, send, 421, "Adresse non autorisée.")
        if not self._identite_ok(scope, hote):
            return await self._refuser(scope, receive, send, 403, "Accès refusé.")
        if methode not in ("GET", "HEAD", "OPTIONS"):
            origine = _entete(scope, "origin")
            if _entete(scope, "x-centre") != "1" or (origine and urlparse(origine).netloc.lower() != hote.lower()):
                return await self._refuser(scope, receive, send, 403, "Requête refusée.")
        jeton = self._jeton(scope)
        scope["centre_jeton"] = jeton
        if chemin not in PUBLICS and not self.verrou.session_valide(jeton):
            if methode == "GET" and not chemin.startswith("/api/"):
                return await RedirectResponse("/connexion", 303, headers=ENTETES_SECURITE)(scope, receive, send)
            return await self._refuser(scope, receive, send, 401, "Connexion requise.")
        await self.app(scope, receive, send)

    @staticmethod
    def _avec_entetes(send, hote, distant):
        """HSTS pour les accès distants ; et la CSP nomme explicitement l'hôte (validé) pour les WebSockets : d'anciens Safari
        n'appliquent pas « connect-src 'self' » aux ws:/wss:."""
        ws = f"wss://{hote}" if distant else f"ws://{hote}"

        async def envoyer(message):
            if message["type"] == "http.response.start":
                entetes = []
                for k, v in message.get("headers", []):
                    if k == b"content-security-policy":
                        v = v.replace(b"connect-src 'self'", ("connect-src 'self' " + ws).encode("latin-1"))
                    entetes.append((k, v))
                if distant:
                    entetes.append((b"strict-transport-security", b"max-age=31536000"))
                message = dict(message, headers=entetes)
            await send(message)
        return envoyer

    async def _websocket(self, scope, receive, send):
        """Une WebSocket n'est acceptée que si : hôte connu, origine = hôte (contre le « cross-site WebSocket
        hijacking »), session valide. Sinon la poignée de main est refusée avant tout échange."""
        hote = _entete(scope, "host")
        origine = _entete(scope, "origin")
        jeton = self._jeton(scope)
        scope["centre_jeton"] = jeton
        ok = (self._hote_ok(hote) and self._identite_ok(scope, hote) and origine
              and urlparse(origine).netloc.lower() == hote.lower() and self.verrou.session_valide(jeton))
        if not ok:
            await receive()                                  # message « websocket.connect »
            return await send({"type": "websocket.close", "code": 1008})
        await self.app(scope, receive, send)

    @staticmethod
    def _jeton(scope):
        c = SimpleCookie()
        try:
            c.load(_entete(scope, "cookie"))
        except Exception:
            return None
        return c[COOKIE].value if COOKIE in c else None

    @staticmethod
    async def _refuser(scope, receive, send, code, message):
        await JSONResponse({"erreur": message}, status_code=code, headers=ENTETES_SECURITE)(scope, receive, send)


def _json(donnees, code=200):
    return JSONResponse(donnees, status_code=code, headers=ENTETES_SECURITE)


def _erreur(message, code=400, **extra):
    return _json({"erreur": message, **extra}, code)


async def _corps(request):
    try:
        d = await request.json()
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def creer_app(centre=None, verrou=None, config=None):
    config = config or (centre.config if centre else Config())
    centre = centre or Centre(config)
    verrou = verrou or Verrou(config.chemin("verrou.json"), config.duree_session)

    def session_courte(request):
        return verrou.identifiant_court(request.scope.get("centre_jeton"))

    # ----- pages ---------------------------------------------------------------------------------

    def fichier(nom):
        entetes = dict(ENTETES_SECURITE)
        entetes["Cache-Control"] = "no-cache"
        return FileResponse(os.path.join(DOSSIER_STATIC, nom), headers=entetes)

    async def page(request):
        nom = PAGES[request.url.path]
        if request.url.path == "/connexion" and verrou.session_valide(request.scope.get("centre_jeton")):
            return RedirectResponse("/", 303, headers=ENTETES_SECURITE)
        return fichier(nom)

    async def statique(request):
        nom = request.path_params["nom"]
        chemin = os.path.join(DOSSIER_STATIC, nom)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", nom) or not os.path.isfile(chemin) or nom in (
                "app.html", "connexion.html", "sw.js", "manifest.webmanifest"):
            return PlainTextResponse("Introuvable.", 404)
        return fichier(nom)

    # ----- verrou -----------------------------------------------------------------------------------

    async def api_verrou(request):
        return _json({"defini": verrou.est_defini(), "attente": verrou.attente_restante(),
                      "connecte": verrou.session_valide(request.scope.get("centre_jeton"))})

    async def api_connexion(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            meta = {"distant": bool(request.scope.get("centre_distant")), "agent": request.headers.get("user-agent", "")}
            jeton = await run_in_threadpool(verrou.connexion, str(d.get("nip", "")), str(d.get("secret", "")), meta)
        except ErreurVerrou as e:
            centre.recus.ajouter("connexion", "refusee", motif=str(e))
            journal.warning("Connexion refusée : %s", e)
            return _erreur(str(e), 429 if "Patientez" in str(e) else 401, attente=verrou.attente_restante())
        centre.recus.ajouter("connexion", "ok", session=verrou.identifiant_court(jeton))
        secure = request.url.scheme == "https" or _entete(request.scope, "x-forwarded-proto") == "https"
        rep = _json({"ok": True})
        rep.set_cookie(COOKIE, jeton, max_age=config.duree_session, httponly=True, samesite="strict",
                       secure=secure, path="/")
        return rep

    def sensible(request):
        """Depuis un appareil distant, une action sensible exige un NIP confirmé dans les 5 dernières minutes."""
        if request.scope.get("centre_distant") and not verrou.nip_recent(request.scope.get("centre_jeton")):
            centre.recus.ajouter("nip_requis", "refuse", chemin=request.url.path, session=session_courte(request))
            return _json({"erreur": "Confirmez votre NIP pour cette action.", "nip_requis": True}, 403)
        return None

    async def api_confirmer_nip(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            await run_in_threadpool(verrou.confirmer_nip, request.scope.get("centre_jeton"), str(d.get("nip", "")))
        except ErreurVerrou as e:
            centre.recus.ajouter("confirmation_nip", "refusee", session=session_courte(request))
            return _erreur(str(e), 429 if "Patientez" in str(e) else 401, attente=verrou.attente_restante())
        centre.recus.ajouter("confirmation_nip", "ok", session=session_courte(request))
        return _json({"ok": True, "duree": verrou.DUREE_NIP})

    async def api_securite(request):
        jeton = request.scope.get("centre_jeton")
        return _json({"sessions": verrou.sessions(jeton), "distant": bool(request.scope.get("centre_distant")),
                      "hotes_autorises": list(config.hotes_autorises), "identite_exigee": config.exiger_identite_tailscale,
                      "utilisateurs_tailscale": list(config.utilisateurs_tailscale),
                      "nip_confirme": verrou.nip_recent(jeton)})

    async def api_deconnecter_autres(request):
        refus = sensible(request)
        if refus:
            return refus
        n = verrou.deconnecter_autres(request.scope.get("centre_jeton"))
        centre.recus.ajouter("deconnexion_des_autres", "ok", nombre=n, session=session_courte(request))
        return _json({"fermees": n})

    async def api_deconnexion(request):
        verrou.deconnexion(request.scope.get("centre_jeton"))
        rep = _json({"ok": True})
        rep.delete_cookie(COOKIE, path="/")
        return rep

    # ----- centre ------------------------------------------------------------------------------------

    async def api_etat(request):
        return _json(await run_in_threadpool(centre.etat))

    async def api_plan(request):
        try:
            liees = await run_in_threadpool(centre.plan, request.query_params.get("sens", ""),
                                            request.query_params.get("ident", ""))
        except ErreurService as e:
            return _erreur(str(e), e.code)
        return _json({"liees": liees})

    async def api_action_lancer(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            job = await run_in_threadpool(centre.lancer_action, str(d.get("sens", "")),
                                          d.get("ident"), bool(d.get("avec_liees")), session_courte(request))
        except ErreurService as e:
            return _erreur(str(e), e.code, **e.extra)
        return _json(job, 202)

    async def api_action_lire(request):
        return _json({"action": centre.job_json()})

    async def api_mode_lire(request):
        return _json(await run_in_threadpool(centre.lire_mode))

    async def api_mode_changer(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None or not isinstance(d.get("mode"), str):
            return _erreur("Mode manquant.")
        try:
            return _json(await run_in_threadpool(centre.changer_mode, d["mode"], session_courte(request)))
        except ErreurService as e:
            return _erreur(str(e), e.code)

    async def api_moteurs(request):
        return _json(await run_in_threadpool(centre.moteurs))

    async def api_autorisations(request):
        return _json(await run_in_threadpool(centre.autorisations))

    async def api_autorisation_definir(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            return _json(await run_in_threadpool(centre.definir_autorisation, d.get("nom"), d.get("autorise"), d.get("limite_jour"), session_courte(request)))
        except ErreurService as e:
            return _erreur(str(e), e.code)

    async def api_chef(request):
        return _json(await run_in_threadpool(centre.chef))

    async def api_chef_definir(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            return _json(await run_in_threadpool(centre.definir_chef, d.get("modele"), session_courte(request)), 202)
        except ErreurService as e:
            return _erreur(str(e), e.code)

    async def api_ouvrir(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None or not isinstance(d.get("ident"), str):
            return _erreur("Application manquante.")
        try:
            return _json(await run_in_threadpool(centre.ouvrir, d["ident"], session_courte(request)))
        except ErreurService as e:
            return _erreur(str(e), e.code)

    # ----- coûts --------------------------------------------------------------------------------------

    def couts_complet():
        st = centre.couts_json()
        st["ia"] = {k: libelle_ia(k) for k in IA}
        st["tarifs"] = TARIFS_REFERENCE
        st["tarifs_texte"] = centre.salles.tarifs.lire()
        return st

    async def api_couts(request):
        return _json(await run_in_threadpool(couts_complet))

    async def api_couts_plafonds(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            p = await run_in_threadpool(centre.couts.definir_plafonds, d.get("jour"), d.get("mois"))
        except ErreurCouts as e:
            return _erreur(str(e), 422)
        centre.recus.ajouter("plafonds", "ok", plafonds=p, session=session_courte(request))
        return _json(await run_in_threadpool(couts_complet))

    async def api_couts_deepseek(request):
        forcer = request.query_params.get("forcer") == "1"
        return _json(await run_in_threadpool(centre.deepseek.lire, forcer))

    # ----- journal ----------------------------------------------------------------------------------------

    async def api_recus(request):
        return _json({"recus": centre.recus.derniers(100)})

    async def api_journal(request):
        lignes = await run_in_threadpool(lire_fin_journal, config.dossier_donnees, 200)
        return _json({"lignes": [masquer(l) for l in lignes]})


    # ----- salles de discussion -------------------------------------------------------------------------------------

    salles = centre.salles

    def sse(evenement):
        return "data: " + json.dumps(evenement, ensure_ascii=False) + "\n\n"

    def flux(execution, depuis=0):
        """Générateur SSE : relit les événements d'une exécution ; peut être repris à tout moment."""
        n = depuis
        while True:
            nouveaux, fini = execution.lire(n, 15.0)
            for e in nouveaux:
                yield sse(e)
            n += len(nouveaux)
            if fini:
                return
            if not nouveaux:
                yield ": ping\n\n"

    def reponse_flux(execution, depuis=0):
        entetes = dict(ENTETES_SECURITE)
        entetes["X-Accel-Buffering"] = "no"
        return StreamingResponse(flux(execution, depuis), media_type="text/event-stream", headers=entetes)

    def erreur_salle(e):
        return _erreur(str(e), getattr(e, "code", 400), **getattr(e, "extra", {}))

    async def api_salles(request):
        def faire():
            mode, libelle = salles.politique.mode()
            nuage, msg = salles.politique.nuage_autorise()
            return {"salles": salles.catalogue(), "actives": salles.en_cours(),
                    "politique": {"mode": mode, "libelle": libelle, "nuage": nuage, "message": msg},
                    "memoire": salles.memoire.etat()}
        return _json(await run_in_threadpool(faire))

    async def api_salle_reglage(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            r = await run_in_threadpool(salles.definir_reglage, request.path_params["salle"], d.get("auth"), d.get("modele"))
        except ErreurSalle as e:
            return erreur_salle(e)
        centre.recus.ajouter("reglage_salle", "ok", salle=request.path_params["salle"], reglage=r, session=session_courte(request))
        return _json(r)

    async def api_salle_modeles(request):
        try:
            salle = request.path_params["salle"]
            r = {"modeles": await run_in_threadpool(salles.modeles_disponibles, salle)}
            if salle == "crew":
                r["explications"] = dict(MODELES_CREW)
                r["defaut"] = MODELES_CREW[0][0]
            return _json(r)
        except ErreurSalle as e:
            return erreur_salle(e)

    async def api_salle_estimation(request):
        try:
            n = int(request.query_params.get("longueur", "0"))
            h = 0
            cid = request.query_params.get("conversation")
            if cid:
                h = sum(len(m.get("texte", "")) for m in salles.conversation(cid)["messages"][-20:])
            return _json(await run_in_threadpool(salles.estimer, request.path_params["salle"], max(0, n), h))
        except ValueError:
            return _erreur("Longueur invalide.")
        except ErreurSalle as e:
            return erreur_salle(e)

    async def api_conversations(request):
        salle = request.query_params.get("salle")
        return _json({"conversations": await run_in_threadpool(salles.conversations.lister, salle if salles.existe(salle) else None),
                      "actives": salles.en_cours()})

    async def api_conversation_creer(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            c = await run_in_threadpool(salles.creer_conversation, str(d.get("salle", "")), str(d.get("titre", "")))
        except ErreurSalle as e:
            return erreur_salle(e)
        return _json(c, 201)

    async def api_conversation_lire(request):
        try:
            c = await run_in_threadpool(salles.conversation, request.path_params["cid"])
        except ErreurSalle as e:
            return erreur_salle(e)
        c["en_cours"] = request.path_params["cid"] in salles.en_cours()
        return _json(c)

    async def api_conversation_renommer(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            c = await run_in_threadpool(salles.conversations.renommer, request.path_params["cid"], d.get("titre"))
        except ErreurConversation as e:
            return erreur_salle(e)
        return _json({"id": c["id"], "titre": c["titre"]})

    async def api_conversation_supprimer(request):
        refus = sensible(request)
        if refus:
            return refus
        cid = request.path_params["cid"]
        if cid in salles.en_cours():
            return _erreur("Arrêtez d'abord la réponse en cours.", 409)
        try:
            await run_in_threadpool(salles.conversations.supprimer, cid)
        except ErreurConversation as e:
            return erreur_salle(e)
        centre.recus.ajouter("conversation_supprimee", "ok", conversation=cid, session=session_courte(request))
        return _json({"ok": True})

    async def api_message(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        options = {"memoire": bool(d.get("memoire")), "autoriser_ecriture": bool(d.get("autoriser_ecriture")),
                   "tiroir": [str(x) for x in d.get("tiroir", [])[:10]] if isinstance(d.get("tiroir"), list) else []}
        t = d.get("table_ronde")
        if isinstance(t, dict):
            options["table_ronde"] = {"participants": [str(x) for x in t.get("participants", [])[:12]] if isinstance(t.get("participants"), list) else [],
                                      "critique": bool(t.get("critique")), "synthese": t.get("synthese") is not False,
                                      "confirme_depassement": bool(t.get("confirme_depassement"))}
        try:
            ex = await run_in_threadpool(salles.demarrer_envoi, request.path_params["cid"], str(d.get("texte", "")),
                                         options, session_courte(request))
        except ErreurSalle as e:
            return erreur_salle(e)
        return reponse_flux(ex)

    async def api_flux(request):
        ex = salles.execution(request.path_params["cid"])
        if ex is None:
            return _erreur("Aucune réponse en cours ni récente.", 404)
        try:
            depuis = max(0, int(request.query_params.get("depuis", "0")))
        except ValueError:
            depuis = 0
        return reponse_flux(ex, depuis)

    async def api_arreter(request):
        return _json({"arrete": salles.arreter(request.path_params["cid"])})

    async def api_approbation(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None or not isinstance(d.get("decisions"), dict):
            return _erreur("Décisions manquantes.")
        decisions = {str(k): str(v) for k, v in d["decisions"].items()}
        try:
            ex = await run_in_threadpool(salles.demarrer_approbation, request.path_params["cid"], decisions, session_courte(request))
        except ErreurSalle as e:
            return erreur_salle(e)
        return reponse_flux(ex)

    async def api_relais(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            r = await run_in_threadpool(salles.preparer_relais, request.path_params["cid"], str(d.get("vers", "")),
                                        d.get("message_id"), str(d.get("portee", "reponse")))
        except ErreurSalle as e:
            return erreur_salle(e)
        return _json(r, 201)

    async def api_tr_options(request):
        return _json(await run_in_threadpool(salles.table_ronde.options))

    async def api_tr_estimation(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        from . import tableronde as tr_mod
        try:
            participants = tr_mod.nettoyer(d.get("participants"))
        except tr_mod.ErreurTableRonde as e:
            return _erreur(str(e), 400)
        messages = []
        cid = d.get("conversation")
        if cid:
            try:
                conv = await run_in_threadpool(salles.conversation, str(cid))
                messages = [{"role": m["role"], "content": m["texte"]} for m in conv["messages"][-20:] if m.get("texte") and not m.get("erreur")]
            except ErreurSalle as e:
                return erreur_salle(e)
        messages.append({"role": "user", "content": str(d.get("texte") or "")[:30000] or "?"})
        est = await run_in_threadpool(salles.table_ronde.estimer, messages, participants, bool(d.get("critique")), d.get("synthese") is not False)
        return _json(est)

    async def api_tiroir_lister(request):
        return _json({"elements": await run_in_threadpool(salles.tiroir.lister)})

    async def api_tiroir_lire(request):
        try:
            return _json(await run_in_threadpool(salles.tiroir.obtenir, request.path_params["ident"]))
        except ErreurTiroir as e:
            return erreur_salle(e)

    async def api_tiroir_ajouter(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            e = await run_in_threadpool(salles.tiroir.ajouter, d.get("titre"), d.get("texte"), d.get("zone", "prive"), d.get("origine", ""))
        except ErreurTiroir as ex:
            return erreur_salle(ex)
        return _json({k: v for k, v in e.items() if k != "texte"}, 201)

    async def api_tiroir_zone(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            e = await run_in_threadpool(salles.tiroir.changer_zone, request.path_params["ident"], d.get("zone"))
        except ErreurTiroir as ex:
            return erreur_salle(ex)
        centre.recus.ajouter("tiroir_zone", "ok", ident=e["id"], zone=e["zone"], session=session_courte(request))
        return _json({"id": e["id"], "zone": e["zone"]})

    async def api_tiroir_supprimer(request):
        try:
            await run_in_threadpool(salles.tiroir.supprimer, request.path_params["ident"])
        except ErreurTiroir as ex:
            return erreur_salle(ex)
        return _json({"ok": True})

    async def api_memoire_chercher(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        passages, msg = await run_in_threadpool(salles.memoire.chercher, d.get("question"), 5, False)
        return _json({"passages": passages, "message": msg})

    async def api_tarifs(request):
        refus = sensible(request)
        if refus:
            return refus
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            t = await run_in_threadpool(salles.tarifs.definir, str(d.get("salle", "")), d.get("entree"), d.get("sortie"))
        except ErreurSalle as e:
            return erreur_salle(e)
        centre.recus.ajouter("tarifs", "ok", salle=d.get("salle"), session=session_courte(request))
        return _json({"tarifs_texte": t})

    # ----- voix ------------------------------------------------------------------------------------------------------

    voix = centre.voix

    async def api_voix_options(request):
        return _json(await run_in_threadpool(voix.options))

    async def api_voix_transcrire(request):
        try:
            if int(request.headers.get("content-length", "0")) > 8_000_000:
                return _erreur("Enregistrement trop gros.", 413)
        except ValueError:
            return _erreur("Requête invalide.")
        octets = await request.body()
        fournisseur = request.query_params.get("fournisseur", "openai")
        if fournisseur not in ("openai", "xai"):
            return _erreur("Fournisseur inconnu.", 400)
        try:
            duree = float(request.query_params.get("duree", "0"))
        except ValueError:
            duree = 0.0
        try:
            r = await run_in_threadpool(voix.transcrire, octets, request.headers.get("content-type", ""), fournisseur, duree)
        except ErreurVoix as e:
            return _erreur(str(e), e.code)
        return _json(r)

    async def api_voix_parler(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        fournisseur = str(d.get("fournisseur", "openai"))
        if fournisseur not in ("openai", "xai"):
            return _erreur("Fournisseur inconnu.", 400)
        try:
            audio, type_mime, tronque = await run_in_threadpool(
                voix.parler, str(d.get("conversation", "")), str(d.get("message_id", "")), fournisseur, str(d.get("voix", "")) or None)
        except ErreurVoix as e:
            return _erreur(str(e), e.code)
        entetes = dict(ENTETES_SECURITE)
        entetes["X-Tronque"] = "1" if tronque else "0"
        return Response(audio, media_type=type_mime, headers=entetes)

    async def ws_voix(ws: WebSocket):
        await ws.accept()
        try:
            params = await asyncio.wait_for(ws.receive_json(), 10)
        except Exception:
            await ws.close(1008)
            return
        if not isinstance(params, dict) or params.get("t") != "demarrer":
            await ws.close(1008)
            return
        session = voix.nouvelle_session(ws, params)
        try:
            await session.courir()
        except WebSocketDisconnect:
            pass
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    # ----- extras (phase 5) --------------------------------------------------------------------------------------------

    async def api_rappels(request):
        return _json({"rappels": await run_in_threadpool(centre.rappels.lister, request.query_params.get("tous") == "1")})

    async def api_rappels_dus(request):
        return _json({"dus": await run_in_threadpool(centre.rappels.dus)})

    async def api_rappel_ajouter(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            r = await run_in_threadpool(centre.rappels.ajouter, d.get("texte"), d.get("echeance"), d.get("recurrence", "aucune"), d.get("zone", "prive"))
        except ErreurRappel as e:
            return _erreur(str(e), e.code)
        return _json(r, 201)

    async def api_rappel_modifier(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        ident = request.path_params["ident"]
        try:
            if d.get("action") == "terminer":
                r = await run_in_threadpool(centre.rappels.terminer, ident)
            elif d.get("action") == "reporter":
                r = await run_in_threadpool(centre.rappels.reporter, ident, d.get("minutes"))
            else:
                return _erreur("Action inconnue.")
        except ErreurRappel as e:
            return _erreur(str(e), e.code)
        return _json(r)

    async def api_rappel_supprimer(request):
        try:
            await run_in_threadpool(centre.rappels.supprimer, request.path_params["ident"])
        except ErreurRappel as e:
            return _erreur(str(e), e.code)
        return _json({"ok": True})

    async def api_departements(request):
        deps, problemes = await run_in_threadpool(departements_mod.charger, config)
        return _json({"departements": deps, "problemes": problemes})

    async def api_bulletin(request):
        return _json(await run_in_threadpool(bulletin_mod.composer, centre))

    async def api_bulletin_lire(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        fournisseur = str(d.get("fournisseur", "openai"))
        if fournisseur not in ("openai", "xai"):
            return _erreur("Fournisseur inconnu.", 400)
        b = await run_in_threadpool(bulletin_mod.composer, centre)
        try:
            audio, type_mime, tronque = await run_in_threadpool(voix.parler_texte, b["texte_voix"], fournisseur, str(d.get("voix", "")) or None)
        except ErreurVoix as e:
            return _erreur(str(e), e.code)
        entetes = dict(ENTETES_SECURITE)
        entetes["X-Tronque"] = "1" if tronque else "0"
        return Response(audio, media_type=type_mime, headers=entetes)

    async def api_verifier(request):
        d = await _corps(request)
        if d is None:
            return _erreur("Requête illisible.")
        try:
            r = await run_in_threadpool(verite_mod.verifier, centre, request.path_params["cid"], str(d.get("message_id", "")), str(d.get("salle", "")))
        except ErreurSalle as e:
            return erreur_salle(e)
        return _json(r)

    async def api_sauvegardes(request):
        return _json({"sauvegardes": await run_in_threadpool(sauvegarde_mod.lister, config)})

    async def api_sauvegarder(request):
        refus = sensible(request)
        if refus:
            return refus
        r = await run_in_threadpool(sauvegarde_mod.sauvegarder, config)
        centre.recus.ajouter("sauvegarde", "ok" if r["ok"] else "erreur", nom=r.get("nom"), fichiers=r.get("fichiers"), session=session_courte(request))
        return _json(r, 200 if r["ok"] else 500)

    async def api_gardien(request):
        return _json(await run_in_threadpool(gardien_mod.lire, config))

    def _jours(request):
        try:
            return max(1, min(int(request.query_params.get("jours", "30")), 366))
        except ValueError:
            return 30

    async def api_rapport(request):
        return _json(await run_in_threadpool(rapport_mod.construire, config, _jours(request)))

    async def api_rapport_csv(request):
        r = await run_in_threadpool(rapport_mod.construire, config, _jours(request))
        entetes = dict(ENTETES_SECURITE)
        entetes["Content-Disposition"] = 'attachment; filename="rapport-usage.csv"'
        return Response(rapport_mod.en_csv(r).encode("utf-8"), media_type="text/csv; charset=utf-8", headers=entetes)

    routes = [
        Route("/", page), Route("/connexion", page), Route("/manifest.webmanifest", page),
        Route("/sw.js", page), Route("/s/{nom}", statique),
        Route("/api/verrou", api_verrou), Route("/api/connexion", api_connexion, methods=["POST"]),
        Route("/api/deconnexion", api_deconnexion, methods=["POST"]),
        Route("/api/confirmer-nip", api_confirmer_nip, methods=["POST"]), Route("/api/securite", api_securite),
        Route("/api/securite/deconnecter-autres", api_deconnecter_autres, methods=["POST"]),
        Route("/api/etat", api_etat), Route("/api/plan", api_plan),
        Route("/api/action", api_action_lire), Route("/api/action", api_action_lancer, methods=["POST"]),
        Route("/api/crew/mode", api_mode_lire), Route("/api/crew/mode", api_mode_changer, methods=["PUT"]),
        Route("/api/crew/moteurs", api_moteurs), Route("/api/crew/autorisations", api_autorisations), Route("/api/crew/chef", api_chef),
        Route("/api/crew/chef", api_chef_definir, methods=["PUT"]),
        Route("/api/crew/autorisations", api_autorisation_definir, methods=["PUT"]), Route("/api/ouvrir", api_ouvrir, methods=["POST"]),
        Route("/api/couts", api_couts), Route("/api/couts/plafonds", api_couts_plafonds, methods=["PUT"]),
        Route("/api/couts/deepseek", api_couts_deepseek),
        Route("/api/recus", api_recus), Route("/api/journal", api_journal),
        Route("/api/salles", api_salles), Route("/api/salles/{salle}/reglage", api_salle_reglage, methods=["PUT"]),
        Route("/api/salles/{salle}/modeles", api_salle_modeles), Route("/api/salles/{salle}/estimation", api_salle_estimation),
        Route("/api/conversations", api_conversations), Route("/api/conversations", api_conversation_creer, methods=["POST"]),
        Route("/api/conversations/{cid}", api_conversation_lire),
        Route("/api/conversations/{cid}", api_conversation_renommer, methods=["PUT"]),
        Route("/api/conversations/{cid}", api_conversation_supprimer, methods=["DELETE"]),
        Route("/api/conversations/{cid}/messages", api_message, methods=["POST"]),
        Route("/api/conversations/{cid}/flux", api_flux),
        Route("/api/conversations/{cid}/arreter", api_arreter, methods=["POST"]),
        Route("/api/conversations/{cid}/approbation", api_approbation, methods=["POST"]),
        Route("/api/conversations/{cid}/relais", api_relais, methods=["POST"]),
        Route("/api/table-ronde/options", api_tr_options), Route("/api/table-ronde/estimation", api_tr_estimation, methods=["POST"]),
        Route("/api/tiroir", api_tiroir_lister), Route("/api/tiroir", api_tiroir_ajouter, methods=["POST"]),
        Route("/api/tiroir/{ident}", api_tiroir_lire), Route("/api/tiroir/{ident}", api_tiroir_zone, methods=["PUT"]),
        Route("/api/tiroir/{ident}", api_tiroir_supprimer, methods=["DELETE"]),
        Route("/api/memoire/chercher", api_memoire_chercher, methods=["POST"]),
        Route("/api/couts/tarifs", api_tarifs, methods=["PUT"]),
        Route("/api/voix/options", api_voix_options), Route("/api/voix/transcrire", api_voix_transcrire, methods=["POST"]),
        Route("/api/voix/parler", api_voix_parler, methods=["POST"]), WebSocketRoute("/ws/voix", ws_voix),
        Route("/api/rappels", api_rappels), Route("/api/rappels", api_rappel_ajouter, methods=["POST"]),
        Route("/api/rappels/dus", api_rappels_dus), Route("/api/rappels/{ident}", api_rappel_modifier, methods=["PUT"]),
        Route("/api/rappels/{ident}", api_rappel_supprimer, methods=["DELETE"]),
        Route("/api/departements", api_departements), Route("/api/bulletin", api_bulletin),
        Route("/api/bulletin/lire", api_bulletin_lire, methods=["POST"]),
        Route("/api/conversations/{cid}/verifier", api_verifier, methods=["POST"]),
        Route("/api/sauvegardes", api_sauvegardes), Route("/api/sauvegardes", api_sauvegarder, methods=["POST"]),
        Route("/api/gardien", api_gardien), Route("/api/rapport", api_rapport), Route("/api/rapport.csv", api_rapport_csv),
    ]

    @asynccontextmanager
    async def duree_de_vie(app):
        centre.demarrer_fond()
        yield
        centre.arreter_fond()

    app = Starlette(routes=routes, lifespan=duree_de_vie)
    app.state.centre, app.state.verrou = centre, verrou
    return Garde(app, verrou, config)
