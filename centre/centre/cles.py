# -*- coding: utf-8 -*-
"""Lecture des clés API : variables d'environnement UTILISATEUR de Windows (HKCU\\Environment), sinon l'environnement du processus.

Les clés ne sont lues qu'au moment de s'en servir, jamais gardées, jamais journalisées."""

import os

NOMS = {
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openwebui": "OPENWEBUI_API_KEY",
}


class Cles:
    def __init__(self, systeme):
        self.sys = systeme

    def lire(self, fournisseur):
        nom = NOMS[fournisseur]
        try:
            v = self.sys.valeur_variable_utilisateur(nom)
        except Exception:
            v = None
        return v or os.environ.get(nom) or None

    def presente(self, fournisseur):
        return bool(self.lire(fournisseur))

    def nom(self, fournisseur):
        return NOMS[fournisseur]
