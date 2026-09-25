# -*- coding: utf-8 -*-
"""
Ouvrir une application quand on clique sur le nom d'un composant.

  - Open WebUI : la conversation la plus récente qui utilise un modèle
    « crew-… », sinon une nouvelle conversation avec crew-normal ;
  - Serveur LM Studio : l'application LM Studio, avec le nom du modèle chargé
    le plus puissant (copié dans le presse-papiers) ;
  - Docker Desktop : l'application.

Ce fichier ne charge et ne décharge JAMAIS de modèle.
"""

import json
import logging
import re
from dataclasses import dataclass

import reglages as R
from panneau_logique import ErreurAction

journal = logging.getLogger("panneau")

OUVRABLES = ("openwebui", "lmstudio", "docker")


@dataclass
class Ouverture:
    genre: str                     # « url » ou « programme »
    cible: str
    message: str = ""              # à afficher (vide = rien à dire)
    presse_papiers: object = None  # texte à copier, ou None


# ---------------------------------------------------------------------------
# Analyse des réponses
# ---------------------------------------------------------------------------

_ID_SUR = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def id_conversation_valide(ident):
    """Un identifiant de conversation ne contient que lettres, chiffres, - et _."""
    return bool(_ID_SUR.match(str(ident or "")))


def analyser_liste_conversations(corps):
    """GET /api/v1/chats/ -> identifiants, du plus récent au plus ancien.

    Format attendu : [{"id": "...", "title": "...", "updated_at": 1726..., ...}]
    (certaines versions renvoient {"items": [...]}). Lève ValueError si illisible.
    """
    try:
        donnees = json.loads(corps)
    except (TypeError, ValueError) as e:
        raise ValueError(f"liste des conversations illisible : {e}")
    if isinstance(donnees, dict):
        donnees = donnees.get("items") or donnees.get("data") or donnees.get("chats")
    if not isinstance(donnees, list):
        raise ValueError("liste des conversations inattendue")
    lignes = [(i, c) for i, c in enumerate(donnees) if isinstance(c, dict) and id_conversation_valide(c.get("id"))]

    def date(c):
        v = c.get("updated_at") or c.get("created_at") or 0
        return v if isinstance(v, (int, float)) else 0
    # Tri du plus récent au plus ancien ; à date égale, on garde l'ordre reçu.
    lignes.sort(key=lambda ic: (-date(ic[1]), ic[0]))
    return [str(c["id"]) for _, c in lignes]


def modeles_de_conversation(corps):
    """GET /api/v1/chats/<id> -> ensemble des modèles utilisés dans la conversation.

    On regarde chat.models, puis le modèle de chaque message (liste
    « messages » et historique « history.messages »).
    """
    try:
        donnees = json.loads(corps)
    except (TypeError, ValueError):
        return set()
    if not isinstance(donnees, dict):
        return set()
    chat = donnees.get("chat") if isinstance(donnees.get("chat"), dict) else donnees
    trouves = set()

    def ajouter(valeur):
        if isinstance(valeur, str) and valeur:
            trouves.add(valeur)
        elif isinstance(valeur, list):
            for v in valeur:
                ajouter(v)

    ajouter(chat.get("models"))
    ajouter(donnees.get("models"))
    messages = list(chat.get("messages") or []) if isinstance(chat.get("messages"), list) else []
    historique = chat.get("history")
    if isinstance(historique, dict) and isinstance(historique.get("messages"), dict):
        messages += list(historique["messages"].values())
    for m in messages:
        if isinstance(m, dict):
            ajouter(m.get("model"))
            ajouter(m.get("models"))
    return trouves


def utilise_crew(modeles):
    return any(m.startswith(R.PREFIXE_MODELE_CREW) for m in modeles)


def _sans_copie(ident):
    """« google/gemma:2 » -> « google/gemma »."""
    return re.sub(r":\d+$", "", ident)


def choisir_modele_puissant(corps_api, sortie_lms_ps):
    """Le plus gros modèle de conversation chargé (type llm ou vlm), ou None.

    - corps_api : réponse de GET /api/v0/models (peut être None) ;
    - sortie_lms_ps : sortie de `lms ps --json`, qui donne la taille (sizeBytes).
    Sans taille connue, on garde le premier modèle chargé.
    """
    tailles, types_ps = {}, {}
    try:
        for m in json.loads(sortie_lms_ps or "[]"):
            if not isinstance(m, dict):
                continue
            taille = m.get("sizeBytes")
            for cle in (m.get("identifier"), m.get("modelKey")):
                if cle:
                    if isinstance(taille, (int, float)):
                        tailles[str(cle)] = taille
                    types_ps[str(cle)] = str(m.get("type") or "")
    except (TypeError, ValueError):
        pass

    candidats = []
    try:
        donnees = json.loads(corps_api) if corps_api else None
        entrees = donnees.get("data") if isinstance(donnees, dict) else None
    except (TypeError, ValueError):
        entrees = None
    if isinstance(entrees, list):
        for m in entrees:
            if isinstance(m, dict) and m.get("state") == "loaded" and m.get("id") \
                    and str(m.get("type") or "llm") in ("llm", "vlm"):
                candidats.append(str(m["id"]))
    else:
        # Pas d'API : on se contente de `lms ps`.
        candidats = [k for k, t in types_ps.items() if t in ("llm", "vlm", "")]

    meilleur, taille_max = None, -1
    for ident in candidats:
        taille = tailles.get(ident, tailles.get(_sans_copie(ident), -1))
        if meilleur is None or taille > taille_max:
            meilleur, taille_max = ident, taille
    return _sans_copie(meilleur) if meilleur else None


# ---------------------------------------------------------------------------
# Préparer puis exécuter l'ouverture
# ---------------------------------------------------------------------------

class Ouvreur:
    def __init__(self, systeme, controleur):
        self.sys = systeme
        self.ctrl = controleur

    def preparer(self, ident):
        """Calcule quoi ouvrir (peut prendre quelques secondes : à appeler hors de la fenêtre)."""
        return {"openwebui": self._openwebui, "lmstudio": self._lmstudio,
                "docker": self._docker}[ident]()

    def executer(self, ouverture):
        journal.info("Ouverture : %s", ouverture.cible if ouverture.genre == "url" else "programme")
        if ouverture.genre == "url":
            self.sys.ouvrir_url(ouverture.cible)
        else:
            self.sys.ouvrir_programme(ouverture.cible)

    # ----- Open WebUI --------------------------------------------------------

    def _openwebui(self):
        nouvelle = R.URL_WEBUI_NOUVELLE_CREW
        cle = self.sys.valeur_variable_utilisateur(R.NOM_CLE_WEBUI)
        if not cle:
            return Ouverture("url", nouvelle, f"Clé {R.NOM_CLE_WEBUI} absente : "
                                              "ouverture d'une nouvelle conversation avec Crew.")
        entetes = {"Authorization": "Bearer " + cle}
        del cle
        debut = self.sys.maintenant()
        statut, corps = self.sys.http("GET", R.URL_WEBUI_CONVERSATIONS, R.DELAI_HTTP, entetes)
        if statut != 200:
            raison = "clé refusée" if statut in (401, 403) else f"code {statut}" if statut else "pas de réponse"
            return Ouverture("url", nouvelle, f"Conversations Open WebUI inaccessibles ({raison}) : "
                                              "nouvelle conversation avec Crew.")
        try:
            ids = analyser_liste_conversations(corps)
        except ValueError as e:
            journal.warning("Open WebUI : %s", e)
            return Ouverture("url", nouvelle, "Liste des conversations illisible : "
                                              "nouvelle conversation avec Crew.")
        for ident in ids[:R.CONVERSATIONS_EXAMINEES]:
            if self.sys.maintenant() - debut > R.DELAI_RECHERCHE_CONVERSATION:
                journal.info("Recherche de conversation Crew interrompue (trop longue)")
                break
            statut, detail = self.sys.http("GET", R.URL_WEBUI_CONVERSATION.format(id=ident),
                                           R.DELAI_HTTP, entetes)
            if statut == 200 and utilise_crew(modeles_de_conversation(detail)):
                return Ouverture("url", R.URL_WEBUI_CONVERSATION_OUVRIR.format(id=ident))
        return Ouverture("url", nouvelle, "Aucune conversation récente avec Crew : "
                                          "nouvelle conversation avec Crew.")

    # ----- LM Studio -----------------------------------------------------------

    def _lmstudio(self):
        exe = next((c for c in R.LMSTUDIO_EXE_CANDIDATS if self.sys.fichier_existe(c)), None)
        if exe is None:
            raise ErreurAction("LM Studio.exe introuvable (chemin à corriger dans reglages.py)")
        statut, corps = self.sys.http("GET", R.URL_LMSTUDIO_MODELES, R.DELAI_HTTP)
        ps = self.sys.executer([self.ctrl.lms, "ps", "--json"], R.DELAI_COMMANDE_COURTE)
        modele = choisir_modele_puissant(corps if statut == 200 else None,
                                         ps.sortie if ps.ok else None)
        if not modele:
            return Ouverture("programme", exe, "Aucun modèle de conversation n'est chargé : "
                                               "LM Studio s'ouvre sans modèle choisi.")
        return Ouverture("programme", exe,
                         f"Dans LM Studio, créez une nouvelle conversation, puis choisissez « {modele} » "
                         "dans la liste des modèles en haut de la fenêtre.\n\n"
                         "Le nom du modèle est copié : collez-le (Ctrl+V) dans la recherche.",
                         presse_papiers=modele)

    # ----- Docker Desktop ----------------------------------------------------

    def _docker(self):
        exe = next((c for c in R.DOCKER_DESKTOP_CANDIDATS if self.sys.fichier_existe(c)), None)
        if exe is None:
            raise ErreurAction("Docker Desktop.exe introuvable (chemin à corriger dans reglages.py)")
        return Ouverture("programme", exe)
