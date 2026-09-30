# -*- coding: utf-8 -*-
"""
Pièces jointes des conversations : IMAGES collées ou choisies dans une salle.

Les images sont rangées sur le PC (dossier `pieces/` des données du Centre), jamais dans le navigateur ni dans les journaux. Le type réel est vérifié sur
le contenu (PNG, JPEG, WebP, GIF), jamais d'après le nom de fichier ; identifiants aléatoires, donc aucun chemin fourni par l'utilisateur n'est utilisé.
Un fichier texte, lui, passe par le tiroir (voir tiroir.py).
"""

import base64
import binascii
import os
import re
import secrets
import threading
import time

MAX_OCTETS = 6_000_000            # par image (le navigateur réduit déjà à 1600 px)
MAX_PAR_MESSAGE = 4
ID_OK = re.compile(r"^[0-9a-f]{16}$")
TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}


class ErreurPiece(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def type_reel(octets):
    """Extension d'après le contenu : 'png', 'jpg', 'webp', 'gif' ou None."""
    if octets[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if octets[:3] == b"\xff\xd8\xff":
        return "jpg"
    if octets[:4] == b"RIFF" and octets[8:12] == b"WEBP":
        return "webp"
    if octets[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


class Pieces:
    def __init__(self, dossier):
        self.dossier = dossier
        self._verrou = threading.Lock()

    def _chemin(self, ident, ext):
        return os.path.join(self.dossier, f"{ident}.{ext}")

    def ajouter_base64(self, donnees, nom=""):
        """Enregistre une image reçue en base64 (sans préfixe « data: »). Renvoie {id, type, nom, taille}."""
        if not isinstance(donnees, str) or not donnees:
            raise ErreurPiece("Image vide.")
        if len(donnees) > MAX_OCTETS * 4 // 3 + 16:
            raise ErreurPiece(f"Image trop lourde (maximum {MAX_OCTETS // 1_000_000} Mo).", 413)
        try:
            octets = base64.b64decode(donnees, validate=True)
        except (binascii.Error, ValueError):
            raise ErreurPiece("Image illisible.")
        return self.ajouter(octets, nom)

    def ajouter(self, octets, nom=""):
        if not octets:
            raise ErreurPiece("Image vide.")
        if len(octets) > MAX_OCTETS:
            raise ErreurPiece(f"Image trop lourde (maximum {MAX_OCTETS // 1_000_000} Mo).", 413)
        ext = type_reel(octets)
        if ext is None:
            raise ErreurPiece("Format d'image non pris en charge (PNG, JPEG, WebP ou GIF seulement).", 415)
        os.makedirs(self.dossier, exist_ok=True)
        ident = secrets.token_hex(8)
        chemin = self._chemin(ident, ext)
        temporaire = chemin + ".tmp"
        with self._verrou:
            with open(temporaire, "wb") as f:
                f.write(octets)
            os.replace(temporaire, chemin)
        nom = re.sub(r"\.{2,}", ".", re.sub(r"[^\w .()\-]", "_", str(nom or "image")))[:60] or "image"
        return {"id": ident, "type": TYPES[ext], "nom": nom, "taille": len(octets)}

    def lire(self, ident):
        """(octets, type MIME). Lève ErreurPiece 404 si l'image n'existe pas."""
        if not isinstance(ident, str) or not ID_OK.match(ident):
            raise ErreurPiece("Image introuvable.", 404)
        for ext, mime in TYPES.items():
            try:
                with open(self._chemin(ident, ext), "rb") as f:
                    return f.read(), mime
            except OSError:
                continue
        raise ErreurPiece("Image introuvable.", 404)

    def existe(self, ident):
        try:
            self.lire(ident)
            return True
        except ErreurPiece:
            return False

    def data_url(self, ident):
        octets, mime = self.lire(ident)
        return f"data:{mime};base64," + base64.b64encode(octets).decode("ascii")

    def supprimer(self, ident):
        if not isinstance(ident, str) or not ID_OK.match(ident):
            return False
        trouve = False
        for ext in TYPES:
            try:
                os.remove(self._chemin(ident, ext))
                trouve = True
            except OSError:
                pass
        return trouve

    def nettoyer(self, references, age_min=86400):
        """Supprime les images que plus aucune conversation ne cite et qui datent de plus de `age_min` secondes (téléversées puis jamais envoyées)."""
        try:
            noms = os.listdir(self.dossier)
        except OSError:
            return 0
        n, maintenant = 0, time.time()
        for nom in noms:
            ident = nom.split(".")[0]
            if ID_OK.match(ident) and ident not in references:
                try:
                    if maintenant - os.path.getmtime(os.path.join(self.dossier, nom)) > age_min:
                        os.remove(os.path.join(self.dossier, nom))
                        n += 1
                except OSError:
                    pass
            elif nom.endswith(".tmp"):
                try:
                    os.remove(os.path.join(self.dossier, nom))
                except OSError:
                    pass
        return n
