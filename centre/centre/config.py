# -*- coding: utf-8 -*-
"""
Réglages du Centre de contrôle.

Les chemins par défaut sont ceux de votre PC (disque I:). Pour les changer,
définissez la variable d'environnement indiquée à côté, sans modifier le code.
"""

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

    def chemin(self, *morceaux):
        return os.path.join(self.dossier_donnees, *morceaux)
