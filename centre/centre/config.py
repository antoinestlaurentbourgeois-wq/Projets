# -*- coding: utf-8 -*-
"""
Réglages du Centre de contrôle.

Les chemins par défaut sont ceux de votre PC (disque I:). Pour les changer,
définissez la variable d'environnement indiquée à côté, sans modifier le code.
"""

import json
import os
import sys
from dataclasses import dataclass, field

DOSSIER_CENTRE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Le serveur n'écoute QUE sur cette adresse. Ce n'est volontairement pas réglable :
# Tailscale Serve (phase 4) vient se brancher dessus, rien d'autre.
HOTE = "127.0.0.1"
PORT = 8740

DUREE_SESSION = 12 * 3600          # session de 12 h (secondes)
DELAI_RAFRAICHISSEMENT = 5         # vérification des voyants (secondes)
INACTIVITE_RAFRAICHISSEMENT = 45   # on cesse de vérifier si personne n'a interrogé depuis N s


def _dossier_panneau_par_defaut():
    voisin = os.path.join(os.path.dirname(DOSSIER_CENTRE), "panneau")   # dépôt : centre/ et panneau/
    if os.path.isfile(os.path.join(voisin, "panneau_logique.py")):
        return voisin
    return r"I:\Python\crewai-routage\panneau"


def _dossier_donnees_par_defaut():
    if sys.platform == "win32":
        return r"I:\IA\CENTRE\donnees"
    return os.path.join(DOSSIER_CENTRE, "donnees")


def dossier_demo():
    """Données du mode démo : sur I: sous Windows (le disque C: manque de place)."""
    if sys.platform == "win32":
        return r"I:\IA\CENTRE\demo"
    import tempfile
    return os.path.join(tempfile.gettempdir(), "centre-demo")


@dataclass
class Config:
    dossier_panneau: str = field(
        default_factory=lambda: os.environ.get("CENTRE_PANNEAU") or _dossier_panneau_par_defaut())
    dossier_donnees: str = field(
        default_factory=lambda: os.environ.get("CENTRE_DONNEES") or _dossier_donnees_par_defaut())
    port: int = PORT
    # Noms d'hôte acceptés en plus de 127.0.0.1 / localhost (ex. le nom Tailscale, phase 4).
    hotes_autorises: tuple = field(
        default_factory=lambda: tuple(h.strip().lower() for h in
                                      os.environ.get("CENTRE_HOTES", "").split(",") if h.strip()))
    duree_session: int = DUREE_SESSION
    rafraichir_en_fond: bool = True
    # Dossier de travail de Claude / Codex / Gemini : ils n'écrivent que là (et seulement après approbation).
    atelier: str = ""
    # Chemins des programmes officiels, si le PATH ne suffit pas (réglages.json, jamais modifiable par le navigateur).
    chemins_programmes: dict = field(default_factory=dict)
    # Accès distant (Tailscale Serve, phase 4) : toute requête venant d'un nom d'hôte distant doit porter l'identité
    # Tailscale (en-tête ajouté par « tailscale serve », jamais par « funnel » ni par Internet).
    exiger_identite_tailscale: bool = True
    utilisateurs_tailscale: tuple = ()

    def __post_init__(self):
        if not self.atelier:
            self.atelier = os.environ.get("CENTRE_ATELIER") or (
                r"I:\IA\ATELIER" if sys.platform == "win32" else os.path.join(self.dossier_donnees, "atelier"))
        # réglages.json : modifiable à la main sur le PC (Bloc-notes), lu au démarrage.
        try:
            with open(os.path.join(self.dossier_donnees, "reglages.json"), encoding="utf-8-sig") as f:
                r = json.load(f)
        except (OSError, ValueError):
            r = {}
        if isinstance(r, dict):
            if isinstance(r.get("hotes_autorises"), list):
                extra = tuple(str(h).strip().lower() for h in r["hotes_autorises"] if str(h).strip())
                self.hotes_autorises = tuple(dict.fromkeys(self.hotes_autorises + extra))
            if isinstance(r.get("utilisateurs_tailscale"), list):
                self.utilisateurs_tailscale = tuple(str(u).strip().lower() for u in r["utilisateurs_tailscale"] if str(u).strip())
            if r.get("exiger_identite_tailscale") is False:
                self.exiger_identite_tailscale = False
            if isinstance(r.get("atelier"), str) and r["atelier"].strip() and not os.environ.get("CENTRE_ATELIER"):
                self.atelier = r["atelier"].strip()
            if isinstance(r.get("chemins_programmes"), dict):
                self.chemins_programmes = {str(k): str(v) for k, v in r["chemins_programmes"].items()}

    def chemin(self, *morceaux):
        return os.path.join(self.dossier_donnees, *morceaux)
