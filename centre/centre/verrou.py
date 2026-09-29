# -*- coding: utf-8 -*-
"""
Verrou : NIP + mot secret, sessions de 12 h.

- Le NIP et le mot secret ne sont JAMAIS gardés : seulement leur empreinte scrypt
  (avec un sel différent pour chacun).
- Après 5 échecs de suite, le verrou impose une attente qui double à chaque échec
  (30 s, 1 min, 2 min... jusqu'à 15 min).
- Une session = un jeton aléatoire dans un cookie HttpOnly. Le serveur ne garde que
  l'empreinte SHA-256 du jeton, en mémoire : redémarrer le serveur déconnecte tout le monde.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
LONGUEUR_MIN_NIP = 6
LONGUEUR_MIN_SECRET = 10
ESSAIS_AVANT_ATTENTE = 5
ATTENTE_BASE = 30
ATTENTE_MAX = 900


def _empreinte(texte, sel):
    return hashlib.scrypt(texte.encode("utf-8"), salt=sel, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                          maxmem=64 * 1024 * 1024, dklen=32)


class ErreurVerrou(Exception):
    pass


class Verrou:
    def __init__(self, chemin, duree_session=12 * 3600, horloge=time.time):
        self.chemin = chemin
        self.duree_session = duree_session
        self.horloge = horloge
        self._sessions = {}           # empreinte du jeton -> instant d'expiration
        self._echecs = 0
        self._bloque_jusqua = 0.0
        self._verrou = threading.Lock()

    # ----- configuration ------------------------------------------------------

    def est_defini(self):
        try:
            with open(self.chemin, encoding="utf-8") as f:
                d = json.load(f)
            return all(k in d for k in ("nip", "secret", "sel_nip", "sel_secret"))
        except (OSError, ValueError):
            return False

    def definir(self, nip, secret):
        """Enregistre un nouveau NIP et un nouveau mot secret (les anciens sont remplacés)."""
        if not (nip.isdigit() and len(nip) >= LONGUEUR_MIN_NIP):
            raise ErreurVerrou(f"Le NIP doit contenir au moins {LONGUEUR_MIN_NIP} chiffres.")
        if len(secret) < LONGUEUR_MIN_SECRET:
            raise ErreurVerrou(f"Le mot secret doit contenir au moins {LONGUEUR_MIN_SECRET} caractères.")
        if secret == nip:
            raise ErreurVerrou("Le mot secret doit être différent du NIP.")
        sel_nip, sel_secret = os.urandom(16), os.urandom(16)
        donnees = {"version": 1,
                   "sel_nip": sel_nip.hex(), "nip": _empreinte(nip, sel_nip).hex(),
                   "sel_secret": sel_secret.hex(), "secret": _empreinte(secret, sel_secret).hex()}
        os.makedirs(os.path.dirname(self.chemin) or ".", exist_ok=True)
        temporaire = self.chemin + ".tmp"
        with open(temporaire, "w", encoding="utf-8") as f:
            json.dump(donnees, f)
        try:
            os.chmod(temporaire, 0o600)
        except OSError:
            pass
        os.replace(temporaire, self.chemin)
        with self._verrou:
            self._sessions.clear()    # un changement de secret déconnecte tout le monde
            self._echecs = 0
            self._bloque_jusqua = 0.0

    # ----- connexion ----------------------------------------------------------

    def attente_restante(self):
        return max(0, int(self._bloque_jusqua - self.horloge() + 0.999))

    def connexion(self, nip, secret):
        """Renvoie un jeton de session, ou lève ErreurVerrou (message sans détail sur ce qui est faux)."""
        if not self.est_defini():
            raise ErreurVerrou("Le verrou n'est pas encore défini sur le PC.")
        with self._verrou:
            reste = self.attente_restante()
            if reste:
                raise ErreurVerrou(f"Trop d'essais. Patientez {reste} s avant de réessayer.")
        try:
            with open(self.chemin, encoding="utf-8") as f:
                d = json.load(f)
            ok_nip = hmac.compare_digest(_empreinte(str(nip or ""), bytes.fromhex(d["sel_nip"])).hex(), d["nip"])
            ok_secret = hmac.compare_digest(
                _empreinte(str(secret or ""), bytes.fromhex(d["sel_secret"])).hex(), d["secret"])
        except (OSError, ValueError, KeyError):
            raise ErreurVerrou("Fichier du verrou illisible.")
        with self._verrou:
            if not (ok_nip and ok_secret):
                self._echecs += 1
                if self._echecs >= ESSAIS_AVANT_ATTENTE:
                    pas = self._echecs - ESSAIS_AVANT_ATTENTE
                    self._bloque_jusqua = self.horloge() + min(ATTENTE_MAX, ATTENTE_BASE * 2 ** pas)
                raise ErreurVerrou("NIP ou mot secret incorrect.")
            self._echecs = 0
            self._bloque_jusqua = 0.0
            jeton = secrets.token_urlsafe(32)
            self._purger()
            self._sessions[self._hacher(jeton)] = self.horloge() + self.duree_session
            return jeton

    @staticmethod
    def _hacher(jeton):
        return hashlib.sha256(jeton.encode("utf-8")).hexdigest()

    def _purger(self):
        maintenant = self.horloge()
        for h in [h for h, fin in self._sessions.items() if fin <= maintenant]:
            del self._sessions[h]

    # ----- sessions -----------------------------------------------------------

    def session_valide(self, jeton):
        if not jeton:
            return False
        with self._verrou:
            fin = self._sessions.get(self._hacher(jeton))
            if fin is None:
                return False
            if fin <= self.horloge():
                del self._sessions[self._hacher(jeton)]
                return False
            return True

    def identifiant_court(self, jeton):
        """Petit identifiant non secret de la session, pour les reçus."""
        return self._hacher(jeton or "")[:8]

    def deconnexion(self, jeton):
        with self._verrou:
            self._sessions.pop(self._hacher(jeton or ""), None)
