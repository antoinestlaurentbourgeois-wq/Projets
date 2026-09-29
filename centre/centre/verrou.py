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
        self._meta = {}               # empreinte du jeton -> {debut, distant, agent}
        self._nip_ok = {}             # empreinte du jeton -> instant jusqu'auquel le NIP est « confirmé »
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
            self._meta.clear()
            self._nip_ok.clear()
            self._echecs = 0
            self._bloque_jusqua = 0.0

    # ----- connexion ----------------------------------------------------------

    def attente_restante(self):
        return max(0, int(self._bloque_jusqua - self.horloge() + 0.999))

    def connexion(self, nip, secret, meta=None):
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
            h = self._hacher(jeton)
            self._sessions[h] = self.horloge() + self.duree_session
            m = dict(meta or {})
            self._meta[h] = {"debut": self.horloge(), "distant": bool(m.get("distant")), "agent": str(m.get("agent", ""))[:120]}
            return jeton

    @staticmethod
    def _hacher(jeton):
        return hashlib.sha256(jeton.encode("utf-8")).hexdigest()

    def _purger(self):
        maintenant = self.horloge()
        for h in [h for h, fin in self._sessions.items() if fin <= maintenant]:
            self._oublier(h)

    # ----- sessions -----------------------------------------------------------

    def _oublier(self, h):
        self._sessions.pop(h, None)
        self._meta.pop(h, None)
        self._nip_ok.pop(h, None)

    def session_valide(self, jeton):
        if not jeton:
            return False
        with self._verrou:
            fin = self._sessions.get(self._hacher(jeton))
            if fin is None:
                return False
            if fin <= self.horloge():
                self._oublier(self._hacher(jeton))
                return False
            return True

    def identifiant_court(self, jeton):
        """Petit identifiant non secret de la session, pour les reçus."""
        return self._hacher(jeton or "")[:8]

    def deconnexion(self, jeton):
        with self._verrou:
            self._oublier(self._hacher(jeton or ""))

    # ----- confirmation du NIP (actions sensibles depuis un appareil distant) ------------------------------

    DUREE_NIP = 300

    def confirmer_nip(self, jeton, nip):
        """Vérifie le NIP d'une session ouverte ; valable 5 minutes. Un échec compte comme un échec de connexion."""
        if not self.session_valide(jeton):
            raise ErreurVerrou("Session expirée.")
        with self._verrou:
            reste = self.attente_restante()
            if reste:
                raise ErreurVerrou(f"Trop d'essais. Patientez {reste} s avant de réessayer.")
        try:
            with open(self.chemin, encoding="utf-8") as f:
                d = json.load(f)
            ok = hmac.compare_digest(_empreinte(str(nip or ""), bytes.fromhex(d["sel_nip"])).hex(), d["nip"])
        except (OSError, ValueError, KeyError):
            raise ErreurVerrou("Fichier du verrou illisible.")
        with self._verrou:
            if not ok:
                self._echecs += 1
                if self._echecs >= ESSAIS_AVANT_ATTENTE:
                    self._bloque_jusqua = self.horloge() + min(ATTENTE_MAX, ATTENTE_BASE * 2 ** (self._echecs - ESSAIS_AVANT_ATTENTE))
                raise ErreurVerrou("NIP incorrect.")
            self._echecs = 0
            self._nip_ok[self._hacher(jeton)] = self.horloge() + self.DUREE_NIP

    def nip_recent(self, jeton):
        with self._verrou:
            fin = self._nip_ok.get(self._hacher(jeton or ""))
            return bool(fin and fin > self.horloge())

    # ----- appareils connectés ---------------------------------------------------------------------------------

    def sessions(self, jeton_courant=None):
        courant = self._hacher(jeton_courant) if jeton_courant else None
        with self._verrou:
            self._purger()
            return sorted(({"id": h[:8], "debut": m["debut"], "distant": m["distant"], "agent": m["agent"],
                            "courante": h == courant, "expire": self._sessions[h]} for h, m in self._meta.items()
                           if h in self._sessions), key=lambda x: -x["debut"])

    def deconnecter_autres(self, jeton_courant):
        """Ferme toutes les sessions sauf la courante. Renvoie le nombre de sessions fermées."""
        garde = self._hacher(jeton_courant or "")
        with self._verrou:
            autres = [h for h in self._sessions if h != garde]
            for h in autres:
                self._oublier(h)
            return len(autres)
