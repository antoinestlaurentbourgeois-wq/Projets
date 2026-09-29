# -*- coding: utf-8 -*-
"""
Serveur web du Centre (Starlette).

Sécurité, dans l'ordre pour chaque requête :
  1. Hôte : seuls 127.0.0.1, localhost et les noms autorisés (protège contre le « DNS rebinding »).
  2. Écritures : en-tête « X-Centre: 1 » obligatoire et Origin identique à l'hôte s'il est présent.
  3. Session : tout exige une session valide, sauf la page de connexion et ses fichiers.
"""

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
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

from .config import Config
from .service import Centre, ErreurService
from .verrou import ErreurVerrou, Verrou
from .couts import ErreurCouts, IA, TARIFS_REFERENCE, libelle_ia
from .journal import lire_fin_journal, masquer

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
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
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
        self.hotes = {f"127.0.0.1:{p}", f"localhost:{p}", *config.hotes_autorises}

    def _hote_ok(self, hote):
        hote = hote.lower()
        return hote in self.hotes or hote.split(":")[0] in self.config.hotes_autorises

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        hote = _entete(scope, "host")
        chemin = scope["path"]
        methode = scope["method"]
        if not self._hote_ok(hote):
            return await self._refuser(scope, receive, send, 421, "Adresse non autorisée.")
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
            jeton = await run_in_threadpool(verrou.connexion, str(d.get("nip", "")), str(d.get("secret", "")))
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
        d = await _corps(request)
        if d is None or not isinstance(d.get("mode"), str):
            return _erreur("Mode manquant.")
        try:
            return _json(await run_in_threadpool(centre.changer_mode, d["mode"], session_courte(request)))
        except ErreurService as e:
            return _erreur(str(e), e.code)

    async def api_moteurs(request):
        return _json(await run_in_threadpool(centre.moteurs))

    async def api_ouvrir(request):
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
        return st

    async def api_couts(request):
        return _json(await run_in_threadpool(couts_complet))

    async def api_couts_plafonds(request):
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

    routes = [
        Route("/", page), Route("/connexion", page), Route("/manifest.webmanifest", page),
        Route("/sw.js", page), Route("/s/{nom}", statique),
        Route("/api/verrou", api_verrou), Route("/api/connexion", api_connexion, methods=["POST"]),
        Route("/api/deconnexion", api_deconnexion, methods=["POST"]),
        Route("/api/etat", api_etat), Route("/api/plan", api_plan),
        Route("/api/action", api_action_lire), Route("/api/action", api_action_lancer, methods=["POST"]),
        Route("/api/crew/mode", api_mode_lire), Route("/api/crew/mode", api_mode_changer, methods=["PUT"]),
        Route("/api/crew/moteurs", api_moteurs), Route("/api/ouvrir", api_ouvrir, methods=["POST"]),
        Route("/api/couts", api_couts), Route("/api/couts/plafonds", api_couts_plafonds, methods=["PUT"]),
        Route("/api/couts/deepseek", api_couts_deepseek),
        Route("/api/recus", api_recus), Route("/api/journal", api_journal),
    ]

    @asynccontextmanager
    async def duree_de_vie(app):
        centre.demarrer_fond()
        yield
        centre.arreter_fond()

    app = Starlette(routes=routes, lifespan=duree_de_vie)
    app.state.centre, app.state.verrou = centre, verrou
    return Garde(app, verrou, config)
