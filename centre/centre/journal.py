# -*- coding: utf-8 -*-
"""
Journal et reçus.

- Le journal (`centre.log`) raconte ce qui se passe. Tout ce qui ressemble à une
  clé y est masqué avant écriture.
- Les reçus (`recus.jsonl`) gardent une ligne par action importante : qui a
  demandé quoi, quand, avec quel résultat. Jamais de secret dedans.
"""

import json
import logging
import logging.handlers
import os
import re
import threading
import time

# Motifs masqués partout : « Bearer xxx », « sk-... », « AIza... », « xai-... ».
_MOTIFS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"), r"\1***"),
    (re.compile(r"\b(sk|xai|ds)-[A-Za-z0-9_\-]{8,}"), "***"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), "***"),
    (re.compile(r"(?i)\b((?:api[_-]?key|secret|token|password|mot_?secret|nip|authorization)"
                r"\s*[=:]\s*[\"']?)[^\s,;&\"']+"), r"\1***"),
]
_CLES_SENSIBLES = re.compile(r"(?i)(key|cle|clé|secret|token|nip|mot|pass|auth|cookie)")


def masquer(texte):
    """Masque les secrets connus dans un texte."""
    texte = str(texte)
    for motif, remplacement in _MOTIFS:
        texte = motif.sub(remplacement, texte)
    return texte


def nettoyer_details(valeur, profondeur=0):
    """Copie d'une structure sans aucune valeur secrète (clés au nom sensible retirées)."""
    if profondeur > 5:
        return "…"
    if isinstance(valeur, dict):
        return {str(k): ("***" if _CLES_SENSIBLES.search(str(k)) else nettoyer_details(v, profondeur + 1))
                for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [nettoyer_details(v, profondeur + 1) for v in valeur[:50]]
    if isinstance(valeur, (int, float, bool)) or valeur is None:
        return valeur
    return masquer(valeur)[:500]


class _FiltreMasque(logging.Filter):
    def filter(self, record):
        try:
            record.msg = masquer(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True


def preparer_journal(dossier):
    """Branche le fichier journal sur les enregistreurs « centre » et « panneau »."""
    os.makedirs(dossier, exist_ok=True)
    gestionnaire = logging.handlers.RotatingFileHandler(
        os.path.join(dossier, "centre.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    gestionnaire.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    gestionnaire.addFilter(_FiltreMasque())
    for nom in ("centre", "panneau"):
        j = logging.getLogger(nom)
        j.setLevel(logging.INFO)
        for h in list(j.handlers):
            if getattr(h, "_centre", False):
                j.removeHandler(h)
        gestionnaire._centre = True
        j.addHandler(gestionnaire)
    return gestionnaire


class Recus:
    """Registre d'actions, une ligne JSON par reçu."""

    def __init__(self, chemin):
        self.chemin = chemin
        self._verrou = threading.Lock()
        os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)

    def ajouter(self, action, resultat="ok", **details):
        ligne = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "action": str(action),
                 "resultat": str(resultat), "details": nettoyer_details(details)}
        with self._verrou:
            with open(self.chemin, "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        return ligne

    def derniers(self, n=50):
        with self._verrou:
            try:
                with open(self.chemin, encoding="utf-8") as f:
                    lignes = f.readlines()[-max(1, min(n, 500)):]
            except OSError:
                return []
        sortie = []
        for l in lignes:
            try:
                sortie.append(json.loads(l))
            except ValueError:
                continue
        return sortie[::-1]


def lire_fin_journal(dossier, n=200):
    try:
        with open(os.path.join(dossier, "centre.log"), encoding="utf-8", errors="replace") as f:
            return [l.rstrip("\n") for l in f.readlines()[-n:]]
    except OSError:
        return []
