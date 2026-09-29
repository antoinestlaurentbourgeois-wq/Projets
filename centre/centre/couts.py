# -*- coding: utf-8 -*-
"""
Coûts : dépenses estimées par IA, plafonds, solde DeepSeek.

- Les dépenses sont des ESTIMATIONS calculées par le Centre (compteurs locaux) : une ligne par
  dépense dans `depenses.jsonl`, en dollars US. Les phases 2 et 3 y ajouteront leurs coûts.
- Deux plafonds, réglés par vous : par jour et par mois (dollars US, vide = pas de plafond).
  Quand un plafond est atteint, les IA payantes sont refusées avec un message clair.
- Le solde DeepSeek vient de l'API officielle (GET /user/balance). La clé ne quitte jamais le PC.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Les IA connues du Centre. `payante` : sort du PC et coûte de l'argent (ou un abonnement).
IA = {
    "crew":     {"libelle": "Crew",          "payante": True},    # peut appeler des IA payantes (sauf modes locaux)
    "claude":   {"libelle": "Claude",        "payante": True},
    "chatgpt":  {"libelle": "ChatGPT/Codex", "payante": True},
    "gemini":   {"libelle": "Gemini",        "payante": True},
    "grok":     {"libelle": "Grok",          "payante": True},
    "deepseek": {"libelle": "DeepSeek",      "payante": True},
    "voix":     {"libelle": "Voix (nuage)",  "payante": True},
    "gemma":    {"libelle": "gemma (local)", "payante": False},
}
MODES_CREW_LOCAUX = ("confidentiel", "ultra")

# Tarifs de référence vérifiés le 29 septembre 2026 (à revérifier), en dollars US.
TARIFS_REFERENCE = {
    "verifie_le": "2026-09-29",
    "grok_voice_par_minute": 0.08,
    "gpt_realtime_mini_par_million_jetons_audio": {"entrant": 10.0, "sortant": 20.0},
    "gpt_realtime_2_par_million_jetons_audio": {"entrant": 32.0, "sortant": 64.0},
    "transcription_xai_par_heure": 0.10,
    "synthese_xai_par_million_caracteres": 15.0,
}

PLAFOND_MAX = 100000.0


class ErreurCouts(Exception):
    pass


def libelle_ia(ident):
    return IA.get(ident, {}).get("libelle", ident)


class Couts:
    def __init__(self, chemin_depenses, chemin_plafonds, horloge=time.time):
        self.chemin_depenses = chemin_depenses
        self.chemin_plafonds = chemin_plafonds
        self.horloge = horloge
        self._verrou = threading.Lock()
        os.makedirs(os.path.dirname(chemin_depenses) or ".", exist_ok=True)

    # ----- dates ------------------------------------------------------------------

    def _jour(self, t=None):
        return time.strftime("%Y-%m-%d", time.localtime(self.horloge() if t is None else t))

    # ----- dépenses ---------------------------------------------------------------

    def enregistrer(self, ia, usd, detail="", estime=True):
        """Ajoute une dépense (dollars US, positive). Lève ErreurCouts si le montant est absurde."""
        try:
            usd = float(usd)
        except (TypeError, ValueError):
            raise ErreurCouts("Montant illisible.")
        if not (0 <= usd < 100000) or usd != usd:
            raise ErreurCouts("Montant hors limites.")
        ligne = {"ts": self._jour() + time.strftime("T%H:%M:%S", time.localtime(self.horloge())),
                 "ia": str(ia), "usd": round(usd, 6), "detail": str(detail)[:200], "estime": bool(estime)}
        with self._verrou:
            with open(self.chemin_depenses, "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        return ligne

    def _lignes(self):
        try:
            with open(self.chemin_depenses, encoding="utf-8") as f:
                brut = f.readlines()
        except OSError:
            return []
        lignes = []
        for l in brut:
            try:
                d = json.loads(l)
                if isinstance(d, dict) and isinstance(d.get("ts"), str) and isinstance(d.get("usd"), (int, float)):
                    lignes.append(d)
            except ValueError:
                continue
        return lignes

    def totaux(self):
        """Dépenses d'aujourd'hui et du mois en cours : {total, par_ia}."""
        jour = self._jour()
        mois = jour[:7]
        sortie = {"aujourdhui": {"total": 0.0, "par_ia": {}}, "mois": {"total": 0.0, "par_ia": {}}}
        with self._verrou:
            lignes = self._lignes()
        for d in lignes:
            ts = d["ts"]
            for cle, actif in (("aujourdhui", ts[:10] == jour), ("mois", ts[:7] == mois)):
                if actif:
                    bloc = sortie[cle]
                    bloc["total"] += d["usd"]
                    ia = str(d.get("ia", "?"))
                    bloc["par_ia"][ia] = bloc["par_ia"].get(ia, 0.0) + d["usd"]
        for bloc in sortie.values():
            bloc["total"] = round(bloc["total"], 4)
            bloc["par_ia"] = {k: round(v, 4) for k, v in sorted(bloc["par_ia"].items())}
        return sortie

    # ----- plafonds ---------------------------------------------------------------

    def plafonds(self):
        try:
            with open(self.chemin_plafonds, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        return {"jour": self._nombre_ou_none(d.get("jour")), "mois": self._nombre_ou_none(d.get("mois"))}

    @staticmethod
    def _nombre_ou_none(v):
        if isinstance(v, bool) or v is None or v == "":
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v if 0 <= v <= PLAFOND_MAX and v == v else None

    def definir_plafonds(self, jour, mois):
        """Vide ou None = pas de plafond. Lève ErreurCouts si une valeur est invalide."""
        nouveau = {}
        for nom, v in (("jour", jour), ("mois", mois)):
            if v is None or (isinstance(v, str) and not v.strip()):
                nouveau[nom] = None
                continue
            if isinstance(v, bool):
                raise ErreurCouts(f"Plafond « {nom} » invalide.")
            try:
                n = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
            except ValueError:
                raise ErreurCouts(f"Plafond « {nom} » invalide : entrez un nombre en dollars.")
            if not (0 <= n <= PLAFOND_MAX) or n != n:
                raise ErreurCouts(f"Plafond « {nom} » hors limites (0 à {PLAFOND_MAX:g} $).")
            nouveau[nom] = round(n, 2)
        if nouveau["jour"] is not None and nouveau["mois"] is not None and nouveau["jour"] > nouveau["mois"]:
            raise ErreurCouts("Le plafond par jour ne peut pas dépasser le plafond par mois.")
        temporaire = self.chemin_plafonds + ".tmp"
        with self._verrou:
            with open(temporaire, "w", encoding="utf-8") as f:
                json.dump(nouveau, f)
            os.replace(temporaire, self.chemin_plafonds)
        return nouveau

    def statut(self):
        """Dépenses, plafonds, et blocage éventuel des IA payantes."""
        t = self.totaux()
        p = self.plafonds()
        depasses = []
        blocs = {}
        for cle, nom_t, mot in (("jour", "aujourdhui", "du jour"), ("mois", "mois", "du mois")):
            depense = t[nom_t]["total"]
            plafond = p[cle]
            atteint = plafond is not None and depense >= plafond
            blocs[cle] = {"plafond": plafond, "depense": depense, "atteint": atteint}
            if atteint:
                depasses.append(f"plafond {mot} atteint ({depense:.2f} $ sur {plafond:.2f} $)")
        message = ""
        if depasses:
            message = ("IA payantes bloquées : " + " et ".join(depasses) +
                       ". Relevez le plafond dans la page Coûts, ou attendez la période suivante.")
        return {"totaux": t, "plafonds": blocs, "bloque": bool(depasses), "message": message}

    def peut_utiliser(self, ia, mode_crew=None):
        """(autorisé, message). Les IA locales ne sont jamais bloquées."""
        if not IA.get(ia, {"payante": True})["payante"]:
            return True, ""
        if ia == "crew" and mode_crew in MODES_CREW_LOCAUX:
            return True, ""
        st = self.statut()
        return (not st["bloque"]), st["message"]


# ---------------------------------------------------------------------------------------
# Solde DeepSeek
# ---------------------------------------------------------------------------------------

URL_SOLDE_DEEPSEEK = "https://api.deepseek.com/user/balance"
HOTES_SORTANTS = ("api.deepseek.com",)


def http_sortant(methode, url, entetes, delai):
    """Requête HTTPS vers une liste très courte de serveurs connus. Renvoie (code, texte) ; code None si échec."""
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or p.hostname not in HOTES_SORTANTS:
        raise ValueError("adresse sortante refusée")
    requete = urllib.request.Request(url, headers=dict(entetes), method=methode)
    try:
        with urllib.request.urlopen(requete, timeout=delai) as rep:
            return rep.status, rep.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, str(getattr(e, "reason", e))


def analyser_solde_deepseek(corps):
    """Réponse de /user/balance -> {disponible, soldes:[{devise,total,accorde,recharge}]}. Lève ValueError."""
    try:
        d = json.loads(corps)
    except (TypeError, ValueError) as e:
        raise ValueError(f"réponse illisible : {e}")
    if not isinstance(d, dict) or not isinstance(d.get("balance_infos"), list):
        raise ValueError("réponse inattendue (pas de « balance_infos »)")
    soldes = []
    for b in d["balance_infos"]:
        if not isinstance(b, dict):
            continue
        soldes.append({"devise": str(b.get("currency", "?")),
                       "total": str(b.get("total_balance", "?")),
                       "accorde": str(b.get("granted_balance", "?")),
                       "recharge": str(b.get("topped_up_balance", "?"))})
    dispo = d.get("is_available")
    return {"disponible": dispo if isinstance(dispo, bool) else None, "soldes": soldes}


class SoldeDeepSeek:
    def __init__(self, lire_cle, http=http_sortant, horloge=time.time, duree_cache=60):
        self.lire_cle = lire_cle
        self.http = http
        self.horloge = horloge
        self.duree_cache = duree_cache
        self._cache = None
        self._verrou = threading.Lock()

    def lire(self, forcer=False):
        with self._verrou:
            if not forcer and self._cache and self.horloge() - self._cache[0] < self.duree_cache:
                return self._cache[1]
        resultat = self._interroger()
        with self._verrou:
            if resultat.get("ok"):
                self._cache = (self.horloge(), resultat)
        return resultat

    def _interroger(self):
        cle = self.lire_cle()
        if not cle:
            return {"ok": False, "message": "Clé DEEPSEEK_API_KEY absente des variables d'environnement Windows."}
        try:
            statut, corps = self.http("GET", URL_SOLDE_DEEPSEEK,
                                      {"Authorization": "Bearer " + cle, "Accept": "application/json"}, 10)
        except ValueError as e:
            return {"ok": False, "message": str(e)}
        finally:
            del cle
        if statut is None:
            return {"ok": False, "message": "DeepSeek injoignable (pas de connexion Internet ?)."}
        if statut in (401, 403):
            return {"ok": False, "message": "Clé DeepSeek refusée."}
        if statut != 200:
            return {"ok": False, "message": f"DeepSeek a répondu {statut}."}
        try:
            return dict(ok=True, **analyser_solde_deepseek(corps))
        except ValueError as e:
            return {"ok": False, "message": str(e)}
