# -*- coding: utf-8 -*-
"""
Adaptateurs : un par façon de parler à une IA. Chacun est un générateur d'ÉVÉNEMENTS (dictionnaires) :

  {"t": "delta", "texte": "..."}                    morceau de réponse
  {"t": "session", "id": "..."}                     identifiant de session du programme (pour reprendre)
  {"t": "approbation", "demandes": [...]}           action refusée d'avance, à approuver par bouton
  {"t": "usage", "entree": n, "sortie": n, "cout_usd": x ou None}
  {"t": "fin", "annule": bool}
  {"t": "erreur", "message": "..."}

Deux familles :
  - API « compatible OpenAI » (LM Studio, Crew, DeepSeek, Gemini, Grok, OpenAI) : flux SSE ;
  - programmes OFFICIELS (claude, codex, gemini) connectés à votre abonnement : sortie lue ligne par ligne.
    Jamais `--dangerously-skip-permissions` ni équivalent : ni ici, ni nulle part.
"""

import json
import re
from dataclasses import dataclass, field

from .journal import masquer
from .reseau import ErreurReseau

MAX_ERREUR = 300


@dataclass
class RequeteChat:
    messages: list                       # [{"role": "user"|"assistant", "content": "..."}]
    modele: str = ""
    systeme: str = ""
    session_cli: str = ""                # reprise d'une session (Claude)
    outils_autorises: tuple = ()         # outils Claude approuvés pour ce tour
    ecriture: bool = False               # Codex : écriture dans l'atelier autorisée (bouton)
    atelier: str = ""


def evt_erreur(message):
    return {"t": "erreur", "message": masquer(str(message))[:MAX_ERREUR * 2]}


def message_http(fournisseur, code, corps):
    """Message clair pour un code HTTP d'erreur, sans jamais renvoyer d'en-tête."""
    detail = ""
    try:
        d = json.loads(corps)
        e = d.get("error", d) if isinstance(d, dict) else {}
        detail = e.get("message") or e.get("detail") or "" if isinstance(e, dict) else str(e)
        if not isinstance(detail, str):
            detail = json.dumps(detail, ensure_ascii=False)
    except (ValueError, TypeError, AttributeError):
        detail = (corps or "")[:MAX_ERREUR]
    base = {401: f"Clé refusée par {fournisseur}.", 403: f"Accès refusé par {fournisseur}.",
            402: f"Solde insuffisant chez {fournisseur}.", 404: f"{fournisseur} : modèle ou adresse introuvable.",
            429: f"{fournisseur} : trop de demandes, ou crédit épuisé.",
            400: f"{fournisseur} a refusé la demande."}.get(code, f"{fournisseur} a répondu {code}.")
    detail = masquer(detail).strip()[:MAX_ERREUR]
    return f"{base} {detail}".strip()


# ------------------------------------------------------------------------------------------
# API compatible OpenAI
# ------------------------------------------------------------------------------------------

class OpenAICompat:
    def __init__(self, reseau, fournisseur, url, lire_cle=None, cle_obligatoire=True, stream_usage=True):
        self.reseau = reseau
        self.fournisseur = fournisseur
        self.url = url
        self.lire_cle = lire_cle
        self.cle_obligatoire = cle_obligatoire
        self.stream_usage = stream_usage

    def repondre(self, req, annulation):
        entetes = {"Accept": "text/event-stream"}
        cle = self.lire_cle() if self.lire_cle else None
        if self.cle_obligatoire and not cle:
            yield evt_erreur(f"Clé {self.fournisseur} absente.")
            return
        if cle:
            entetes["Authorization"] = "Bearer " + cle
        del cle
        messages = ([{"role": "system", "content": req.systeme}] if req.systeme else []) + list(req.messages)
        corps = {"model": req.modele, "messages": messages, "stream": True}
        if self.stream_usage:
            corps["stream_options"] = {"include_usage": True}
        try:
            code, lignes = self.reseau.flux_post(self.url, entetes, corps, annulation=annulation)
        except ErreurReseau as e:
            yield evt_erreur(e)
            return
        if code is None:
            yield evt_erreur(f"{self.fournisseur} est injoignable : {masquer(lignes)}")
            return
        if code != 200:
            yield evt_erreur(message_http(self.fournisseur, code, "\n".join(lignes)))
            return
        usage = None
        annule = False
        for ligne in lignes:
            if annulation.annule():
                annule = True
                break
            if not ligne.startswith("data:"):
                continue
            donnees = ligne[5:].strip()
            if donnees == "[DONE]":
                break
            try:
                d = json.loads(donnees)
            except ValueError:
                continue
            if isinstance(d.get("error"), dict):
                yield evt_erreur(f"{self.fournisseur} : {d['error'].get('message', 'erreur')}")
                return
            if isinstance(d.get("usage"), dict):
                usage = d["usage"]
            for choix in d.get("choices") or []:
                texte = (choix.get("delta") or {}).get("content")
                if texte:
                    yield {"t": "delta", "texte": texte}
        if usage:
            cout = usage.get("cout_usd")               # fourni par Crew : coût RÉEL calculé chez lui
            yield {"t": "usage", "entree": int(usage.get("prompt_tokens") or 0), "sortie": int(usage.get("completion_tokens") or 0),
                   "cout_usd": float(cout) if isinstance(cout, (int, float)) and not isinstance(cout, bool) else None}
        yield {"t": "fin", "annule": annule}

    def lister_modeles(self, url_modeles):
        """Identifiants de modèles disponibles (GET /models). Liste vide si impossible."""
        entetes = {}
        cle = self.lire_cle() if self.lire_cle else None
        if cle:
            entetes["Authorization"] = "Bearer " + cle
        del cle
        try:
            code, corps = self.reseau.requete("GET", url_modeles, entetes, delai=15)
        except ErreurReseau:
            return []
        if code != 200:
            return []
        try:
            d = json.loads(corps)
            liste = d.get("data") if isinstance(d, dict) else d
            ids = [str(m.get("id")) for m in liste if isinstance(m, dict) and m.get("id")]
        except (ValueError, TypeError, AttributeError):
            return []
        return sorted({re.sub(r"^models/", "", i) for i in ids})


# ------------------------------------------------------------------------------------------
# Programmes officiels
# ------------------------------------------------------------------------------------------

OUTILS_LECTURE_CLAUDE = ("Read", "Glob", "Grep", "LS")
# Fichiers sensibles que Claude ne doit jamais lire, même en lecture seule (Read peut sortir de l'atelier).
LECTURES_INTERDITES = ("Read(**/.env)", "Read(**/.env.*)", "Read(**/.claude/.credentials.json)", "Read(**/.codex/auth.json)",
                       "Read(**/.gemini/**)", "Read(**/verrou.json)", "Read(**/secrets/**)", "Read(**/*.pem)", "Read(**/id_rsa*)",
                       "Read(**/id_ed25519*)", "Read(**/.ssh/**)")
_ID_SESSION = re.compile(r"^[A-Za-z0-9_-]{6,100}$")
_MODELE = re.compile(r"^[A-Za-z0-9._:/-]{1,80}$")
_BASH_SUR = re.compile(r"^[A-Za-z0-9 _.,:=/\\\-]{1,200}$")
_OUTIL_SUR = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
OUTILS_ECRITURE = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def modele_valide(m):
    m = m or ""
    return bool(_MODELE.match(m)) and ".." not in m and not m.startswith(("/", "-"))


def motif_autorisation(outil, entree):
    """Motif `--allowedTools` pour approuver UNE demande refusée. None si trop risqué à approuver ici."""
    if not _OUTIL_SUR.match(str(outil or "")):
        return None
    if outil == "Bash":
        commande = (entree or {}).get("command") if isinstance(entree, dict) else None
        if not isinstance(commande, str) or not _BASH_SUR.match(commande):
            return None
        return f"Bash({commande})"
    if outil == "WebFetch":
        url = (entree or {}).get("url") if isinstance(entree, dict) else None
        hote = re.match(r"^https://([A-Za-z0-9.-]{1,120})(?:[/?#]|$)", url or "")
        return f"WebFetch(domain:{hote.group(1)})" if hote else None
    return outil


def resume_demande(outil, entree):
    """Phrase lisible décrivant l'action demandée (texte affiché tel quel, jamais interprété)."""
    e = entree if isinstance(entree, dict) else {}
    if outil == "Bash":
        return "Exécuter la commande : " + str(e.get("command", "?"))[:300]
    if outil in OUTILS_ECRITURE:
        return f"{'Modifier' if outil != 'Write' else 'Écrire'} le fichier : {e.get('file_path') or e.get('notebook_path') or '?'}"
    if outil == "WebFetch":
        return "Consulter la page web : " + str(e.get("url", "?"))[:300]
    if outil == "WebSearch":
        return "Chercher sur le web : " + str(e.get("query", "?"))[:300]
    return f"Utiliser l'outil « {outil} »"


def transcription(messages, limite=60000):
    """Historique en texte, pour les programmes qui ne gardent pas de session."""
    morceaux, total = [], 0
    for m in reversed(messages):
        t = ("Utilisateur : " if m["role"] == "user" else "Assistant : ") + m["content"]
        total += len(t)
        if total > limite and morceaux:
            break
        morceaux.append(t)
    return "\n\n".join(reversed(morceaux))


class ProgrammeBase:
    def __init__(self, processus, fournisseur, trouver_exe, fabriquer_env=None):
        self.processus = processus
        self.fournisseur = fournisseur
        self.trouver_exe = trouver_exe
        self.fabriquer_env = fabriquer_env or (lambda: None)

    def _lancer(self, args, req, stdin_texte, annulation):
        proc = self.processus.lancer(args, cwd=req.atelier or None, env=self.fabriquer_env(), stdin_texte=stdin_texte)
        annulation.sur_annulation(proc.terminer)
        return proc


class ClaudeCLI(ProgrammeBase):
    def repondre(self, req, annulation):
        exe = self.trouver_exe()
        if not exe:
            yield evt_erreur("Le programme « claude » est introuvable (Claude Code n'est pas installé ou pas dans le PATH).")
            return
        outils = list(OUTILS_LECTURE_CLAUDE) + [o for o in req.outils_autorises if o not in OUTILS_LECTURE_CLAUDE]
        args = [exe, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
                "--allowedTools", ",".join(outils),
                "--disallowedTools", ",".join(LECTURES_INTERDITES), "--permission-mode", "default", "--max-turns", "12"]
        if req.modele and modele_valide(req.modele):
            args += ["--model", req.modele]
        if req.session_cli and _ID_SESSION.match(req.session_cli):
            args += ["--resume", req.session_cli]
            invite = req.messages[-1]["content"]
        else:
            invite = transcription(req.messages) if len(req.messages) > 1 else req.messages[-1]["content"]
        try:
            proc = self._lancer(args, req, (req.systeme + "\n\n" if req.systeme else "") + invite, annulation)
        except ErreurReseau as e:
            yield evt_erreur(e)
            return
        diffuse, final, resultat = False, "", None
        for ligne in proc.lignes():
            if annulation.annule():
                break
            try:
                d = json.loads(ligne)
            except ValueError:
                continue
            t = d.get("type")
            if t == "system" and d.get("session_id"):
                yield {"t": "session", "id": str(d["session_id"])}
            elif t == "stream_event":
                delta = (d.get("event") or {}).get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    diffuse = True
                    yield {"t": "delta", "texte": delta["text"]}
            elif t == "assistant":
                for bloc in (d.get("message") or {}).get("content") or []:
                    if bloc.get("type") == "text":
                        final += bloc.get("text", "")
            elif t == "result":
                resultat = d
        if annulation.annule():
            proc.terminer()
            yield {"t": "fin", "annule": True}
            return
        proc.attendre(10)
        if resultat is None:
            err = masquer(proc.stderr_texte()).strip()[:MAX_ERREUR]
            yield evt_erreur("Claude n'a pas répondu" + (f" : {err}" if err else "") +
                             ". Êtes-vous connecté ? (lancez « claude » une fois dans un terminal pour vous connecter)")
            return
        if resultat.get("session_id"):
            yield {"t": "session", "id": str(resultat["session_id"])}
        if resultat.get("is_error") or str(resultat.get("subtype", "success")).startswith("error"):
            yield evt_erreur(f"Claude : {resultat.get('result') or resultat.get('subtype') or 'erreur'}")
            return
        if not diffuse:
            texte = resultat.get("result") or final
            if texte:
                yield {"t": "delta", "texte": str(texte)}
        u = resultat.get("usage") or {}
        yield {"t": "usage", "entree": int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0),
               "sortie": int(u.get("output_tokens") or 0),
               "cout_usd": resultat.get("total_cost_usd") if isinstance(resultat.get("total_cost_usd"), (int, float)) else None}
        refus = []
        for r in resultat.get("permission_denials") or []:
            if not isinstance(r, dict):
                continue
            outil, entree = str(r.get("tool_name", "?")), r.get("tool_input") or {}
            refus.append({"id": str(r.get("tool_use_id") or f"r{len(refus)}"), "outil": outil,
                          "resume": resume_demande(outil, entree),
                          "motif": motif_autorisation(outil, entree)})
        if refus:
            yield {"t": "approbation", "demandes": refus}
        yield {"t": "fin", "annule": False}


class CodexCLI(ProgrammeBase):
    def repondre(self, req, annulation):
        exe = self.trouver_exe()
        if not exe:
            yield evt_erreur("Le programme « codex » est introuvable (Codex CLI n'est pas installé ou pas dans le PATH).")
            return
        args = [exe, "exec", "--json", "--skip-git-repo-check", "-C", req.atelier,
                "-s", "workspace-write" if req.ecriture else "read-only"]
        if req.modele and modele_valide(req.modele):
            args += ["-m", req.modele]
        args.append("-")
        prompt = (req.systeme + "\n\n" if req.systeme else "") + transcription(req.messages)
        try:
            proc = self._lancer(args, req, prompt, annulation)
        except ErreurReseau as e:
            yield evt_erreur(e)
            return
        erreur, usage, vu = "", None, False
        for ligne in proc.lignes():
            if annulation.annule():
                break
            try:
                d = json.loads(ligne)
            except ValueError:
                continue
            t = d.get("type")
            if t == "thread.started" and d.get("thread_id"):
                yield {"t": "session", "id": str(d["thread_id"])}
            elif t == "item.completed":
                item = d.get("item") or {}
                if item.get("type") == "agent_message" and item.get("text"):
                    yield {"t": "delta", "texte": ("\n\n" if vu else "") + str(item["text"])}
                    vu = True
            elif t == "turn.completed":
                usage = d.get("usage") or {}
            elif t in ("error", "turn.failed"):
                erreur = str(d.get("message") or (d.get("error") or {}).get("message") or "erreur")
        if annulation.annule():
            proc.terminer()
            yield {"t": "fin", "annule": True}
            return
        proc.attendre(10)
        if erreur:
            yield evt_erreur(f"Codex : {erreur}")
            return
        if not vu:
            err = masquer(proc.stderr_texte()).strip()[:MAX_ERREUR]
            yield evt_erreur("Codex n'a pas répondu" + (f" : {err}" if err else "") +
                             ". Êtes-vous connecté ? (lancez « codex login » dans un terminal, « Se connecter avec ChatGPT »)")
            return
        if usage is not None:
            yield {"t": "usage", "entree": int(usage.get("input_tokens") or 0),
                   "sortie": int(usage.get("output_tokens") or 0), "cout_usd": None}
        yield {"t": "fin", "annule": False}


class GeminiCLI(ProgrammeBase):
    def repondre(self, req, annulation):
        exe = self.trouver_exe()
        if not exe:
            yield evt_erreur("Le programme « gemini » est introuvable (Gemini CLI n'est pas installé ou pas dans le PATH).")
            return
        args = [exe, "-p", "Reponds a la demande recue sur l'entree standard."]
        if req.modele and modele_valide(req.modele):
            args += ["-m", req.modele]
        prompt = (req.systeme + "\n\n" if req.systeme else "") + transcription(req.messages)
        try:
            proc = self._lancer(args, req, prompt, annulation)
        except ErreurReseau as e:
            yield evt_erreur(e)
            return
        vu = False
        for ligne in proc.lignes():
            if annulation.annule():
                break
            vu = True
            yield {"t": "delta", "texte": ligne + "\n"}
        if annulation.annule():
            proc.terminer()
            yield {"t": "fin", "annule": True}
            return
        code = proc.attendre(10)
        if not vu or code not in (0, None):
            err = masquer(proc.stderr_texte()).strip()[:MAX_ERREUR]
            yield evt_erreur("Gemini n'a pas répondu" + (f" : {err}" if err else "") +
                             ". Êtes-vous connecté avec votre compte Google ? (lancez « gemini » une fois dans un terminal)")
            return
        yield {"t": "fin", "annule": False}
