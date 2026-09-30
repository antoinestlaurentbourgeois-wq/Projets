# -*- coding: utf-8 -*-
import asyncio
import json
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from centre.config import Config as _Config  # noqa: E402

# Même logique que le serveur : variable CENTRE_PANNEAU, puis panneau voisin (dépôt),
# puis I:\Python\crewai-routage\panneau (installation réelle).
PANNEAU = _Config().dossier_panneau
if PANNEAU not in sys.path:
    sys.path.insert(0, PANNEAU)

from simulateur import Simulateur  # noqa: E402  (fourni par le panneau)
from starlette.testclient import TestClient  # noqa: E402

from centre.app import creer_app  # noqa: E402
from centre.config import Config  # noqa: E402
from centre.service import Centre  # noqa: E402
from centre.verrou import Verrou  # noqa: E402

NIP, SECRET = "123456", "motsecret-de-test"


class FauxReseau:
    """Remplace centre.reseau.Reseau : réponses écrites d'avance, aucune vraie connexion."""

    def __init__(self):
        self.routes = {}          # url -> fonction(corps, entetes) -> (code, lignes)
        self.appels = []          # (methode, url, corps, entetes)
        self.modeles = {}         # url -> liste d'identifiants

    def repondre(self, url, gestionnaire):
        self.routes[url] = gestionnaire

    def flux_post(self, url, entetes, corps, delai=600, annulation=None):
        self.appels.append(("POST", url, corps, dict(entetes)))
        g = self.routes.get(url)
        if g is None:
            return None, "connexion refusée"
        return g(corps, entetes)

    def requete(self, methode, url, entetes=None, corps=None, delai=30, octets=False, max_octets=0):
        self.appels.append((methode, url, corps, dict(entetes or {})))
        if url in self.modeles:
            return 200, json.dumps({"data": [{"id": m} for m in self.modeles[url]]})
        g = self.routes.get(url)
        if g is None:
            return None, "connexion refusée"
        code, contenu = g(corps, entetes or {})
        return code, contenu if isinstance(contenu, (str, bytes)) else "\n".join(contenu)


def sse(*morceaux, usage=None, erreur=None):
    """Lignes d'un flux « compatible OpenAI »."""
    lignes = []
    for m in morceaux:
        lignes += ["data: " + json.dumps({"choices": [{"delta": {"content": m}}]}), ""]
    if usage:
        lignes += ["data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}), ""]
    lignes += ["data: [DONE]", ""]
    return 200, iter(lignes)


LIBELLES_TR = {"claude": "Claude", "codex": "ChatGPT / Codex", "gemini": "Gemini", "grok": "Grok", "deepseek": "DeepSeek",
               "gemma": "gemma (local)", "synthese": "Synthèse de Crew"}


def debut(participant, tour=1):
    """Morceau « debut » du vrai Crew (jamais pour la synthèse)."""
    return {"evenement": "debut", "participant": participant, "tour": tour, "libelle": LIBELLES_TR[participant]}


def reponse(participant, texte, cout=0.0, tour=1, duree=None):
    """Morceau « reponse » du vrai Crew : réponse COMPLÈTE dans choices[0].delta.content, duree_s au niveau du morceau, usage {entree, sortie, cout_usd}."""
    d = {"evenement": "reponse", "participant": participant, "tour": 0 if participant == "synthese" else tour, "libelle": LIBELLES_TR[participant],
         "choices": [{"index": 0, "delta": {"content": texte}, "finish_reason": None}],
         "usage": {"entree": 10, "sortie": 20, "cout_usd": cout}}
    if duree is not None:
        d["duree_s"] = duree
    return d


def exclu(participant, message="contenu confidentiel, traité en local seulement", tour=1):
    return {"evenement": "exclu", "participant": participant, "tour": tour, "libelle": LIBELLES_TR[participant], "message": message}


def erreur_p(participant, message, tour=1):
    return {"evenement": "erreur", "participant": participant, "tour": tour, "libelle": LIBELLES_TR[participant], "message": message}


def fin_tr(cout=0.0, exclus=(), notes=()):
    return {"evenement": "fin", "usage": {"prompt_tokens": 30, "completion_tokens": 40, "total_tokens": 70, "cout_usd": cout},
            "exclus": list(exclus), "notes": list(notes)}


ROLE = {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
PULSATION = {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": None}]}
STOP = {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}


def flux_crew(*evenements, bruit=True):
    """Flux Crew complet : {"role"}, pulsations entre les événements, morceau « stop », ligne « fin » si absente, puis [DONE].
    (Les morceaux sans « evenement » — role, pulsation, stop — font partie du VRAI flux et doivent être ignorés.)"""
    tout = [ROLE] if bruit else []
    for e in evenements:
        tout.append(e)
        if bruit:
            tout.append(PULSATION)
    if bruit:
        tout.append(STOP)
    if not any(e.get("evenement") == "fin" for e in evenements):
        tout.append(fin_tr(sum((e.get("usage") or {}).get("cout_usd") or 0 for e in evenements if e.get("evenement") == "reponse")))
    return sse_table(*tout)


def sse_table(*morceaux):
    lignes = []
    for m in morceaux:
        lignes += ["data: " + json.dumps(m), ""]
    lignes += ["data: [DONE]", ""]
    return 200, iter(lignes)


class FauxProc:
    def __init__(self, lignes, stderr="", code=0, attente=None):
        self._lignes, self._stderr, self.code, self.attente = lignes, stderr, code, attente
        self.termine = False

    def lignes(self):
        for l in self._lignes:
            if self.attente is not None:
                self.attente.wait(5)
                if self.termine:
                    return
            yield l

    def terminer(self):
        self.termine = True
        if self.attente is not None:
            self.attente.set()

    def attendre(self, delai=10):
        return self.code

    def stderr_texte(self):
        return self._stderr


class FauxProcessus:
    def __init__(self):
        self.installes = {"claude": "C:/bin/claude.exe", "codex": "C:/bin/codex.cmd", "gemini": "C:/bin/gemini.cmd"}
        self.scenarios = {}       # nom du programme -> FauxProc ou fonction(args, stdin) -> FauxProc
        self.lances = []          # dicts {args, cwd, env, stdin}

    def trouver(self, nom, candidats=()):
        return self.installes.get(nom)

    def lancer(self, args, cwd=None, env=None, stdin_texte=None):
        self.lances.append({"args": list(args), "cwd": cwd, "env": env, "stdin": stdin_texte})
        nom = os.path.basename(args[0]).split(".")[0]
        sc = self.scenarios[nom]
        return sc(args, stdin_texte) if callable(sc) else sc


class FausseConnexion:
    """Une WebSocket « amont » simulée (fournisseur vocal). Thread-safe : les tests l'alimentent depuis un autre fil."""

    def __init__(self, url, entetes, loop):
        self.url, self.entetes, self.loop = url, dict(entetes), loop
        self.envoyes = []
        self.ferme = False
        self.sur_envoi = None
        self._q = asyncio.Queue()

    async def send(self, message):
        m = json.loads(message)
        self.envoyes.append(m)
        if self.sur_envoi:
            self.sur_envoi(m)

    def emettre(self, evenement):
        self.loop.call_soon_threadsafe(self._q.put_nowait, json.dumps(evenement))

    async def close(self):
        self.ferme = True
        self._q.put_nowait(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        x = await self._q.get()
        if x is None:
            raise StopAsyncIteration
        return x

    def types(self):
        return [m["type"] for m in self.envoyes]


class FauxAmont:
    def __init__(self):
        self.connexions = []
        self.echec = None

    async def ouvrir(self, url, entetes):
        if self.echec:
            raise OSError(self.echec)
        c = FausseConnexion(url, entetes, asyncio.get_running_loop())
        self.connexions.append(c)
        return c


class Horloge:
    def __init__(self):
        self.t = 1_790_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def sans_vraies_cles(monkeypatch):
    """Les tests ne doivent jamais dépendre des vraies clés de la machine."""
    from centre.cles import NOMS
    for nom in NOMS.values():
        monkeypatch.delenv(nom, raising=False)


@pytest.fixture
def horloge():
    return Horloge()


@pytest.fixture
def simulateur():
    return Simulateur()


@pytest.fixture
def reseau():
    return FauxReseau()


@pytest.fixture
def processus():
    return FauxProcessus()


@pytest.fixture
def amont():
    return FauxAmont()


@pytest.fixture
def centre(tmp_path, simulateur, reseau, processus, amont):
    config = Config(dossier_donnees=str(tmp_path / "donnees"), rafraichir_en_fond=False)
    config.gemini_abonnement = True          # les tests de programmes utilisent Gemini CLI comme véhicule ; l'option est testée à part
    c = Centre(config, systeme=simulateur, reseau=reseau, processus=processus, amont=amont)
    c.salles.dormir = lambda s: c.salles.pauses.append(s)          # pas d'attente réelle entre les essais
    c.salles.pauses = []
    return c


@pytest.fixture
def verrou(centre, horloge):
    v = Verrou(centre.config.chemin("verrou.json"), horloge=horloge)
    v.definir(NIP, SECRET)
    return v


@pytest.fixture
def client(centre, verrou):
    """Client déjà connecté."""
    c = TestClient(creer_app(centre, verrou), base_url="http://127.0.0.1:8740")
    c.headers["X-Centre"] = "1"
    r = c.post("/api/connexion", json={"nip": NIP, "secret": SECRET})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def anonyme(centre, verrou):
    """Client sans session."""
    c = TestClient(creer_app(centre, verrou), base_url="http://127.0.0.1:8740", follow_redirects=False)
    c.headers["X-Centre"] = "1"
    return c
