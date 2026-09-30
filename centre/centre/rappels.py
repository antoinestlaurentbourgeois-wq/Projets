# -*- coding: utf-8 -*-
"""
Rappels : un texte, une échéance, une récurrence facultative.

Notifications : la page (ouverte, sur le PC ou le téléphone) interroge `/api/rappels/dus` toutes les 30 s et affiche une alerte
(et une notification du navigateur si vous l'avez autorisée). Il n'y a PAS de « push » quand l'application est fermée : cela
demanderait un service extérieur (Google/Apple), donc de sortir des données du PC.
Chaque rappel a une ZONE : « prive » (par défaut : son texte n'est jamais lu par une voix du nuage) ou « partageable ».
"""

import calendar
import json
import os
import re
import secrets
import threading
import time

RECURRENCES = ("aucune", "quotidien", "hebdomadaire", "mensuel")
ZONES = ("prive", "partageable")
MAX_RAPPELS = 500
MAX_TEXTE = 500
MIN_TS, MAX_TS = 946684800, 4102444800        # 2000 -> 2100


class ErreurRappel(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def suivante(echeance, recurrence, apres):
    """Prochaine échéance strictement après `apres`, selon la récurrence."""
    if recurrence == "quotidien":
        pas = 86400
    elif recurrence == "hebdomadaire":
        pas = 7 * 86400
    elif recurrence == "mensuel":
        t = time.localtime(echeance)
        n = 0
        while echeance <= apres or n == 0:
            n += 1
            mois0 = t.tm_mon - 1 + n
            annee, mois = t.tm_year + mois0 // 12, mois0 % 12 + 1
            jour = min(t.tm_mday, calendar.monthrange(annee, mois)[1])
            echeance = time.mktime((annee, mois, jour, t.tm_hour, t.tm_min, t.tm_sec, 0, 0, -1))
            if n > 1200:
                break
        return echeance
    else:
        return echeance
    n = int((apres - echeance) // pas) + 1
    return echeance + max(1, n) * pas


class Rappels:
    def __init__(self, chemin, horloge=time.time):
        self.chemin = chemin
        self.horloge = horloge
        self._verrou = threading.RLock()

    def _charger(self):
        try:
            with open(self.chemin, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, list) else []
        except (OSError, ValueError):
            return []

    def _sauver(self, liste):
        os.makedirs(os.path.dirname(self.chemin) or ".", exist_ok=True)
        temporaire = self.chemin + ".tmp"
        with open(temporaire, "w", encoding="utf-8") as f:
            json.dump(liste, f, ensure_ascii=False)
        os.replace(temporaire, self.chemin)

    def lister(self, avec_faits=False):
        with self._verrou:
            liste = self._charger()
        if not avec_faits:
            liste = [r for r in liste if not r.get("fait")]
        return sorted(liste, key=lambda r: r["echeance"])

    def ajouter(self, texte, echeance, recurrence="aucune", zone="prive"):
        texte = str(texte or "").strip()
        if not texte:
            raise ErreurRappel("Texte vide.")
        if len(texte) > MAX_TEXTE:
            raise ErreurRappel(f"Texte trop long (maximum {MAX_TEXTE} caractères).")
        try:
            echeance = float(echeance)
        except (TypeError, ValueError):
            raise ErreurRappel("Échéance invalide.")
        if not (MIN_TS <= echeance <= MAX_TS) or echeance != echeance:
            raise ErreurRappel("Échéance hors limites.")
        if recurrence not in RECURRENCES:
            raise ErreurRappel("Récurrence inconnue.")
        if zone not in ZONES:
            raise ErreurRappel("Zone inconnue.")
        with self._verrou:
            liste = self._charger()
            if len(liste) >= MAX_RAPPELS:
                raise ErreurRappel("Trop de rappels : supprimez les anciens.")
            r = {"id": secrets.token_hex(6), "texte": texte, "echeance": echeance, "recurrence": recurrence, "zone": zone,
                 "fait": False, "cree": self.horloge()}
            liste.append(r)
            self._sauver(liste)
        return r

    def _modifier(self, ident, fonction):
        with self._verrou:
            liste = self._charger()
            for r in liste:
                if r["id"] == ident:
                    fonction(r)
                    self._sauver(liste)
                    return r
        raise ErreurRappel("Rappel introuvable.", 404)

    def terminer(self, ident):
        """Marque fait ; un rappel récurrent passe à sa prochaine échéance au lieu d'être terminé."""
        def f(r):
            if r["recurrence"] != "aucune":
                r["echeance"] = suivante(r["echeance"], r["recurrence"], self.horloge())
                r["fait"] = False
            else:
                r["fait"] = True
                r["fait_le"] = self.horloge()
        return self._modifier(ident, f)

    def reporter(self, ident, minutes):
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            raise ErreurRappel("Durée invalide.")
        if not 1 <= minutes <= 60 * 24 * 30:
            raise ErreurRappel("Durée hors limites.")
        return self._modifier(ident, lambda r: r.update(echeance=self.horloge() + minutes * 60, fait=False))

    def supprimer(self, ident):
        with self._verrou:
            liste = self._charger()
            reste = [r for r in liste if r["id"] != ident]
            if len(reste) == len(liste):
                raise ErreurRappel("Rappel introuvable.", 404)
            self._sauver(reste)

    def dus(self):
        t = self.horloge()
        return [r for r in self.lister() if r["echeance"] <= t]

    def du_jour(self):
        """Rappels en retard ou prévus aujourd'hui (jusqu'à minuit)."""
        t = time.localtime(self.horloge())
        minuit = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 23, 59, 59, 0, 0, -1))
        return [r for r in self.lister() if r["echeance"] <= minuit]
