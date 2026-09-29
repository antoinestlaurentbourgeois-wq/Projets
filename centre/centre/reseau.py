# -*- coding: utf-8 -*-
"""
Accès réseau et processus, isolés dans deux petites classes pour pouvoir les remplacer par des
simulateurs dans les tests.

  Reseau.flux_post(...)   requête HTTP POST dont on lit la réponse ligne par ligne (SSE, JSON par ligne)
  Reseau.requete(...)     requête ordinaire (code, texte)
  Processus.lancer(...)   programme officiel (claude, codex, gemini) dont on lit la sortie ligne par ligne

Seuls les hôtes de la liste blanche sont joignables : une adresse inattendue lève ErreurReseau.
Aucun en-tête (donc aucune clé) n'est jamais écrit dans un journal ou un message d'erreur.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

HOTES_LOCAUX = ("127.0.0.1",)
HOTES_NUAGE = ("api.deepseek.com", "api.openai.com", "api.x.ai", "generativelanguage.googleapis.com",
               "api.anthropic.com")
_ARG_SUR = re.compile(r"^[A-Za-z0-9 _.,:=+@/\\()\-]*$")
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class ErreurReseau(Exception):
    """Problème de communication ; le message est affichable tel quel."""


class Annulation:
    """Permet d'arrêter une réponse en cours (bouton Stop, plafond atteint, déconnexion)."""

    def __init__(self):
        self._evt = threading.Event()
        self._actions = []
        self._verrou = threading.Lock()

    def annule(self):
        return self._evt.is_set()

    def sur_annulation(self, fonction):
        with self._verrou:
            if self._evt.is_set():
                fonction()
            else:
                self._actions.append(fonction)

    def declencher(self):
        with self._verrou:
            self._evt.set()
            actions, self._actions = self._actions, []
        for a in actions:
            try:
                a()
            except Exception:
                pass


def hote_autorise(url, nuage_autorise=True):
    p = urllib.parse.urlparse(url)
    if p.hostname in HOTES_LOCAUX and p.scheme in ("http", "ws"):
        return True
    return nuage_autorise and p.hostname in HOTES_NUAGE and p.scheme in ("https", "wss")


class Reseau:
    """Réseau réel (urllib). Les proxys système sont utilisés pour le nuage, jamais pour 127.0.0.1."""

    def _ouvrir(self, url, methode, entetes, donnees, delai):
        if not hote_autorise(url):
            raise ErreurReseau("adresse refusée (hôte non autorisé)")
        requete = urllib.request.Request(url, data=donnees, headers=dict(entetes), method=methode)
        local = urllib.parse.urlparse(url).hostname in HOTES_LOCAUX
        ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({})) if local \
            else urllib.request.build_opener()
        return ouvreur.open(requete, timeout=delai)

    def requete(self, methode, url, entetes=None, corps=None, delai=30, octets=False, max_octets=20_000_000):
        """(code, texte ou octets). Code None si personne ne répond."""
        donnees = None
        entetes = dict(entetes or {})
        if corps is not None:
            if isinstance(corps, (bytes, bytearray)):
                donnees = bytes(corps)
            else:
                donnees = json.dumps(corps).encode("utf-8")
                entetes.setdefault("Content-Type", "application/json")
        try:
            with self._ouvrir(url, methode, entetes, donnees, delai) as rep:
                brut = rep.read(max_octets)
                return rep.status, (brut if octets else brut.decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try:
                brut = e.read(50_000)
            except OSError:
                brut = b""
            return e.code, (brut if octets else brut.decode("utf-8", "replace"))
        except ErreurReseau:
            raise
        except (urllib.error.URLError, OSError, ValueError) as e:
            return None, str(getattr(e, "reason", e))

    def flux_post(self, url, entetes, corps, delai=600, annulation=None):
        """Envoie `corps` (JSON) et renvoie (code, itérateur de lignes de texte).

        Si le code n'est pas 200, l'itérateur contient le corps de l'erreur.
        Code None : personne ne répond (le second élément est alors le message).
        """
        entetes = dict(entetes)
        entetes.setdefault("Content-Type", "application/json")
        donnees = json.dumps(corps).encode("utf-8")
        try:
            rep = self._ouvrir(url, "POST", entetes, donnees, delai)
            code = rep.status
        except urllib.error.HTTPError as e:
            rep, code = e, e.code
        except ErreurReseau:
            raise
        except (urllib.error.URLError, OSError, ValueError) as e:
            return None, str(getattr(e, "reason", e))
        if annulation is not None:
            annulation.sur_annulation(lambda: rep.close())

        def lignes():
            try:
                while True:
                    ligne = rep.readline(1_000_000)
                    if not ligne:
                        return
                    yield ligne.decode("utf-8", "replace").rstrip("\r\n")
            except (OSError, ValueError):
                return            # connexion fermée (arrêt demandé ou coupure)
            finally:
                try:
                    rep.close()
                except Exception:
                    pass
        return code, lignes()


class ProcessusEnCours:
    def __init__(self, popen):
        self.popen = popen

    def lignes(self):
        try:
            for brut in iter(self.popen.stdout.readline, b""):
                yield brut.decode("utf-8", "replace").rstrip("\r\n")
        finally:
            try:
                self.popen.stdout.close()
            except Exception:
                pass

    def terminer(self):
        try:
            if self.popen.poll() is None:
                if sys.platform == "win32":     # arrête aussi les programmes enfants
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.popen.pid)],
                                   capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=15)
                else:
                    self.popen.kill()
        except Exception:
            pass

    def attendre(self, delai=10):
        try:
            return self.popen.wait(delai)
        except subprocess.TimeoutExpired:
            self.terminer()
            return None

    def stderr_texte(self):
        try:
            return self.popen.stderr.read(20_000).decode("utf-8", "replace")
        except Exception:
            return ""


class Processus:
    """Lance un programme (jamais par un interpréteur de commandes : pas d'injection possible)."""

    def trouver(self, nom, candidats=()):
        trouve = shutil.which(nom)
        if trouve:
            return trouve
        for c in candidats:
            if c and os.path.isfile(c):
                return c
        return None

    def lancer(self, args, cwd=None, env=None, stdin_texte=None):
        # Sous Windows, un .cmd/.bat passe par cmd.exe : on refuse alors tout argument avec un caractère spécial.
        if str(args[0]).lower().endswith((".cmd", ".bat")):
            for a in args[1:]:
                if not _ARG_SUR.match(str(a)):
                    raise ErreurReseau("argument refusé (caractère spécial interdit)")
        try:
            p = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW, shell=False)
        except OSError as e:
            raise ErreurReseau(f"impossible de lancer le programme : {e}")
        try:
            if stdin_texte is not None:
                p.stdin.write(stdin_texte.encode("utf-8"))
            p.stdin.close()
        except OSError:
            pass
        return ProcessusEnCours(p)
