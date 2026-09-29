# -*- coding: utf-8 -*-
"""
Le « tiroir » : une bibliothèque de textes partagée entre toutes les salles.

Chaque élément a une ZONE : « prive » (jamais envoyé à une IA du nuage) ou « partageable ».
La zone par défaut est « prive » : dans le doute, rien ne sort.
"""

import json
import os
import re
import secrets
import threading
import time

ZONES = ("prive", "partageable")
MAX_ELEMENTS = 500
MAX_TEXTE = 20000
ID_OK = re.compile(r"^[0-9a-f]{12}$")


class ErreurTiroir(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


class Tiroir:
    def __init__(self, chemin):
        self.chemin = chemin
        self._verrou = threading.RLock()

    def _charger(self):
        try:
            with open(self.chemin, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, list) else []
        except (OSError, ValueError):
            return []

    def _sauver(self, elements):
        os.makedirs(os.path.dirname(self.chemin) or ".", exist_ok=True)
        temporaire = self.chemin + ".tmp"
        with open(temporaire, "w", encoding="utf-8") as f:
            json.dump(elements, f, ensure_ascii=False)
        os.replace(temporaire, self.chemin)

    def lister(self, avec_texte=False):
        with self._verrou:
            elements = self._charger()
        if avec_texte:
            return elements
        return [{k: v for k, v in e.items() if k != "texte"} | {"taille": len(e.get("texte", ""))} for e in elements]

    def obtenir(self, ident):
        with self._verrou:
            for e in self._charger():
                if e["id"] == ident:
                    return e
        raise ErreurTiroir("Élément introuvable.", 404)

    def ajouter(self, titre, texte, zone="prive", origine=""):
        titre, texte = str(titre or "").strip()[:120], str(texte or "").strip()
        if not texte:
            raise ErreurTiroir("Texte vide.")
        if len(texte) > MAX_TEXTE:
            raise ErreurTiroir(f"Texte trop long (maximum {MAX_TEXTE} caractères).")
        if zone not in ZONES:
            raise ErreurTiroir("Zone inconnue.")
        with self._verrou:
            elements = self._charger()
            if len(elements) >= MAX_ELEMENTS:
                raise ErreurTiroir("Tiroir plein : supprimez des éléments.")
            e = {"id": secrets.token_hex(6), "titre": titre or texte[:60], "texte": texte, "zone": zone,
                 "origine": str(origine)[:60], "ts": time.time()}
            elements.append(e)
            self._sauver(elements)
        return e

    def changer_zone(self, ident, zone):
        if zone not in ZONES:
            raise ErreurTiroir("Zone inconnue.")
        with self._verrou:
            elements = self._charger()
            for e in elements:
                if e["id"] == ident:
                    e["zone"] = zone
                    self._sauver(elements)
                    return e
        raise ErreurTiroir("Élément introuvable.", 404)

    def supprimer(self, ident):
        with self._verrou:
            elements = self._charger()
            reste = [e for e in elements if e["id"] != ident]
            if len(reste) == len(elements):
                raise ErreurTiroir("Élément introuvable.", 404)
            self._sauver(reste)
