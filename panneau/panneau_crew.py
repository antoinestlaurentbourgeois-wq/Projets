# -*- coding: utf-8 -*-
"""
Dialogue avec le serveur Crew : mode en cours (GET/PUT /mode) et liste des IA
(GET /moteurs).

Les libellés, explications et IA viennent TOUJOURS du serveur : rien n'est
écrit en dur ici. Quand le serveur est éteint :
  - le mode est lu et changé dans le fichier mode_crew.json (le serveur le
    relit à chaque demande) ;
  - les libellés affichés sont ceux reçus la dernière fois du serveur,
    gardés dans une petite copie locale (modes_crew_cache.json).

La clé CREW_API_KEY est lue dans le fichier .env à chaque appel. Elle n'est
jamais gardée, affichée, ni écrite dans le journal.
"""

import json
import logging
import re
import threading
from dataclasses import dataclass, field

import reglages as R
from panneau_logique import ACTIF, ARRETE, INCONNU, Chef, chef_depuis_donnees, identifiant_modele_valide, lire_chef_fichier  # noqa: F401

journal = logging.getLogger("panneau")

# Voyant de chaque état d'IA renvoyé par /moteurs (valeur inconnue -> gris).
COULEUR_ETAT_MOTEUR = {"pret": ACTIF, "arrete": ARRETE, "indisponible": INCONNU}
TEXTE_ETAT_MOTEUR = {"pret": "prête", "arrete": "arrêtée", "indisponible": "indisponible"}
TEXTE_CAPACITE = {1: "simple", 2: "bon", 3: "expert"}


@dataclass
class Mode:
    id: str
    libelle: str
    explication: str = ""


@dataclass
class InfoMode:
    actuel: object = None            # identifiant du mode en cours (ou None)
    modes: list = field(default_factory=list)
    serveur_actif: bool = False
    modifiable: bool = True
    message: str = ""

    def libelle(self, ident=None):
        ident = ident or self.actuel
        for m in self.modes:
            if m.id == ident:
                return m.libelle
        return ident or "?"


@dataclass
class Moteur:
    nom: str
    libelle: str
    local: bool = False
    capacite: object = None
    cout: object = None
    forces: list = field(default_factory=list)
    etat: str = ""
    detail: str = ""
    abonnement: bool = False         # IA sur abonnement (Claude, Codex) : limites d'usage, jamais choisie tant qu'elle n'est pas autorisée


NOMS_AUTORISATION = ("claude", "codex")
LIMITE_MIN, LIMITE_MAX = 1, 500


@dataclass
class Autorisation:
    nom: str
    autorise: bool = False
    limite_jour: int = 20
    utilise_aujourdhui: int = 0


@dataclass
class InfoChef:
    """Réponse de GET /chef (Crew)."""
    lmstudio: bool = True
    chef: str = ""
    chef_charge: bool = False
    changement: object = None       # None ou {"etat": en_cours|termine|echec, "cible", "etape", "message", "debut"}
    modeles: list = field(default_factory=list)
    dernier_test: object = None     # None ou {"modele", "ok", "json_valides", "sur", "duree_moy_s"}
    message: str = ""
    libere: bool = False            # la carte graphique a été libérée (le chef est déchargé exprès : POST /chef/liberer, pas encore /chef/reprendre)


@dataclass
class InfoMoteurs:
    moteurs: object = None           # liste de Moteur, ou None si indisponible
    message: str = ""


class ErreurCrew(Exception):
    """Problème avec le serveur Crew ; le message est affiché tel quel."""


class ServeurEteint(ErreurCrew):
    pass


class ErreurDemande(ErreurCrew):
    """La demande elle-même est invalide (mauvais nom, limite hors 1–500…) ou refusée par Crew (409, 503) : pas une panne."""

    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Analyse des réponses (fonctions simples, testées une par une)
# ---------------------------------------------------------------------------

def analyser_env(texte, nom):
    """Valeur de `nom` dans un fichier .env (NOM=valeur), ou None.

    Accepte les espaces, les guillemets, « export » devant, les commentaires.
    """
    for ligne in (texte or "").lstrip("﻿").splitlines():
        m = re.match(r"\s*(?:export\s+)?" + re.escape(nom) + r"\s*=\s*(.*)$", ligne)
        if not m:
            continue
        valeur = m.group(1).strip()
        if valeur[:1] in ("'", '"'):
            fin = valeur.find(valeur[0], 1)
            valeur = valeur[1:fin] if fin > 0 else valeur[1:]
        else:
            valeur = re.split(r"\s+#", valeur, maxsplit=1)[0].strip()
        return valeur or None
    return None


def analyser_mode(corps):
    """Réponse de /mode -> (mode actuel, [Mode]). Lève ValueError si illisible."""
    try:
        donnees = json.loads(corps)
    except (TypeError, ValueError) as e:
        raise ValueError(f"réponse /mode illisible : {e}")
    if not isinstance(donnees, dict) or not isinstance(donnees.get("modes"), list):
        raise ValueError("réponse /mode inattendue (pas de liste « modes »)")
    modes = []
    for m in donnees["modes"]:
        if isinstance(m, dict) and m.get("id"):
            ident = str(m["id"])
            modes.append(Mode(ident, str(m.get("libelle") or ident), str(m.get("explication") or "")))
    actuel = donnees.get("mode")
    return (str(actuel) if actuel else None), modes


def analyser_moteurs(corps):
    """Réponse de /moteurs -> [Moteur]. Lève ValueError si illisible.

    Les champs manquants ou inconnus sont tolérés : une nouvelle IA ajoutée
    à Crew apparaît sans modifier le panneau.
    """
    try:
        donnees = json.loads(corps)
    except (TypeError, ValueError) as e:
        raise ValueError(f"réponse /moteurs illisible : {e}")
    liste = donnees.get("moteurs") if isinstance(donnees, dict) else donnees
    if not isinstance(liste, list):
        raise ValueError("réponse /moteurs inattendue (pas de liste « moteurs »)")
    moteurs = []
    for m in liste:
        if not isinstance(m, dict):
            continue
        nom = str(m.get("nom") or m.get("libelle") or "?")
        forces = m.get("forces") if isinstance(m.get("forces"), list) else []
        moteurs.append(Moteur(
            nom=nom, libelle=str(m.get("libelle") or nom), local=bool(m.get("local")),
            capacite=m.get("capacite"), cout=m.get("cout"),
            forces=[str(f) for f in forces], etat=str(m.get("etat") or ""),
            detail=str(m.get("detail") or ""), abonnement=m.get("abonnement") is True))
    return moteurs


def _texte(v, n=300):
    return str(v)[:n] if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def _nombre(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _est_embeddings(m):
    return "embed" in (str(m.get("id", "")) + " " + str(m.get("architecture", ""))).lower()


def analyser_chef(corps):
    """Réponse de GET /chef -> InfoChef. Lève ValueError si illisible. Tolérant : champs absents = valeurs neutres.
    Les modèles d'embeddings ne sont jamais gardés (par prudence : Crew ne doit déjà pas les lister)."""
    try:
        d = json.loads(corps)
    except (TypeError, ValueError) as e:
        raise ValueError(f"réponse /chef illisible : {e}")
    if not isinstance(d, dict):
        raise ValueError("réponse /chef inattendue")
    modeles = []
    for m in d.get("modeles") if isinstance(d.get("modeles"), list) else []:
        if not isinstance(m, dict) or not identifiant_modele_valide(m.get("id")) or _est_embeddings(m):
            continue
        modeles.append({"id": m["id"], "libelle": _texte(m.get("libelle")) or m["id"], "taille_go": _nombre(m.get("taille_go")),
                        "params": _texte(m.get("params")), "architecture": _texte(m.get("architecture")),
                        "quantification": _texte(m.get("quantification")), "charge": m.get("charge") is True, "chef": m.get("chef") is True,
                        "contexte": m.get("contexte") if isinstance(m.get("contexte"), int) and not isinstance(m.get("contexte"), bool) else None,
                        "parallele": m.get("parallele") if isinstance(m.get("parallele"), int) and not isinstance(m.get("parallele"), bool) else None,
                        "avertissement": _texte(m.get("avertissement")) or None})
    ch = d.get("changement")
    if isinstance(ch, dict) and ch.get("etat") in ("en_cours", "termine", "echec"):
        ch = {"etat": ch["etat"], "cible": _texte(ch.get("cible"), 200), "etape": _texte(ch.get("etape")), "message": _texte(ch.get("message"), 500),
              "debut": _nombre(ch.get("debut"))}
    else:
        ch = None
    t = d.get("dernier_test")
    if isinstance(t, dict):
        t = {"modele": _texte(t.get("modele"), 200), "ok": t.get("ok") is True, "json_valides": _entier(t.get("json_valides")),
             "sur": _entier(t.get("sur")), "duree_moy_s": _nombre(t.get("duree_moy_s"))}
    else:
        t = None
    chef = d.get("chef") if identifiant_modele_valide(d.get("chef")) else ""
    return InfoChef(d.get("lmstudio") is not False, chef, d.get("chef_charge") is True, ch, modeles, t, _texte(d.get("message"), 500),
                    d.get("libere") is True)


def _entier(v, defaut=0):
    return int(v) if isinstance(v, int) and not isinstance(v, bool) else defaut


def analyser_autorisations(corps):
    """Réponse de /autorisations -> [Autorisation]. Lève ValueError si illisible."""
    try:
        donnees = json.loads(corps)
    except (TypeError, ValueError) as e:
        raise ValueError(f"réponse /autorisations illisible : {e}")
    liste = donnees.get("autorisations") if isinstance(donnees, dict) else None
    if not isinstance(liste, list):
        raise ValueError("réponse /autorisations inattendue (pas de liste « autorisations »)")
    sortie = []
    for a in liste:
        if isinstance(a, dict) and a.get("nom") in NOMS_AUTORISATION:
            sortie.append(Autorisation(a["nom"], a.get("autorise") is True, _entier(a.get("limite_jour"), 20), _entier(a.get("utilise_aujourdhui"))))
    return sortie


def texte_capacite(capacite):
    """1 -> « niveau 1 (simple) »."""
    if isinstance(capacite, (int, float)) and not isinstance(capacite, bool):
        n = int(capacite)
        nom = TEXTE_CAPACITE.get(n)
        return f"niveau {n} ({nom})" if nom else f"niveau {n}"
    return "niveau ?"


def texte_cout(cout):
    """0 -> « gratuit », 4 -> « coût relatif 4 »."""
    if isinstance(cout, (int, float)) and not isinstance(cout, bool):
        if cout == 0:
            return "gratuit"
        return f"coût relatif {cout:g}"
    return "coût ?"


def couleur_moteur(etat):
    return COULEUR_ETAT_MOTEUR.get(etat, INCONNU)


# ---------------------------------------------------------------------------
# Le client du serveur Crew
# ---------------------------------------------------------------------------

class CrewDistant:
    def __init__(self, systeme):
        self.sys = systeme
        self._modes_en_cache = None      # dernière liste de modes connue (en mémoire)
        self._verrou = threading.Lock()

    # ----- appels HTTP -----------------------------------------------------

    def _appel(self, methode, url, corps=None):
        cle = analyser_env(self.sys.lire_fichier(R.FICHIER_ENV_CREW), R.NOM_CLE_CREW)
        if not cle:
            raise ErreurCrew(f"Clé {R.NOM_CLE_CREW} introuvable dans {R.FICHIER_ENV_CREW}")
        statut, texte = self.sys.http(methode, url, R.DELAI_HTTP,
                                      {"Authorization": "Bearer " + cle}, corps)
        del cle
        if statut is None:
            raise ServeurEteint("Serveur Crew éteint")
        if statut in (401, 403):
            raise ErreurCrew(f"Clé {R.NOM_CLE_CREW} refusée par le serveur Crew")
        return statut, texte

    # ----- copie locale des modes ------------------------------------------

    def _enregistrer_cache(self, modes):
        donnees = [{"id": m.id, "libelle": m.libelle, "explication": m.explication} for m in modes]
        if donnees == self._modes_en_cache:
            return                       # rien de neuf : on n'écrit pas le disque
        self._modes_en_cache = donnees
        try:
            self.sys.ecrire_fichier(R.FICHIER_CACHE_MODES,
                                    json.dumps({"modes": donnees}, ensure_ascii=False, indent=1))
        except OSError as e:
            journal.warning("copie locale des modes impossible : %s", e)

    def _modes_du_cache(self):
        if self._modes_en_cache is None:
            texte = self.sys.lire_fichier(R.FICHIER_CACHE_MODES)
            try:
                self._modes_en_cache = json.loads(texte)["modes"] if texte else []
            except (ValueError, KeyError, TypeError):
                self._modes_en_cache = []
        return [Mode(str(m.get("id")), str(m.get("libelle") or m.get("id")), str(m.get("explication") or ""))
                for m in self._modes_en_cache if isinstance(m, dict) and m.get("id")]

    # ----- fichier mode_crew.json (serveur éteint) ---------------------------

    def _lire_fichier_mode(self):
        texte = self.sys.lire_fichier(R.FICHIER_MODE_CREW)
        if texte is None:
            return {}
        try:
            donnees = json.loads(texte)
            return donnees if isinstance(donnees, dict) else {}
        except ValueError:
            journal.warning("mode_crew.json illisible")
            return {}

    def _info_depuis_fichier(self, message, modifiable=True):
        actuel = self._lire_fichier_mode().get("mode")
        return InfoMode(actuel=str(actuel) if actuel else None, modes=self._modes_du_cache(),
                        serveur_actif=False, modifiable=modifiable, message=message)

    # ----- ce que le panneau utilise -------------------------------------------

    def lire_mode(self, crew_actif=True):
        """Mode en cours : par l'API si le serveur tourne, sinon par le fichier."""
        if not crew_actif:
            return self._info_depuis_fichier("Serveur Crew éteint")
        try:
            statut, texte = self._appel("GET", R.URL_CREW_MODE)
        except ServeurEteint:
            return self._info_depuis_fichier("Serveur Crew éteint")
        except ErreurCrew as e:
            return self._info_depuis_fichier(str(e), modifiable=False)
        if statut != 200:
            return self._info_depuis_fichier(f"/mode a répondu {statut}", modifiable=False)
        try:
            actuel, modes = analyser_mode(texte)
        except ValueError as e:
            return self._info_depuis_fichier(str(e), modifiable=False)
        self._enregistrer_cache(modes)
        return InfoMode(actuel=actuel, modes=modes, serveur_actif=True)

    def changer_mode(self, ident):
        """Change le mode. Renvoie la nouvelle InfoMode ; lève ErreurCrew en cas d'échec."""
        with self._verrou:
            try:
                statut, texte = self._appel("PUT", R.URL_CREW_MODE, {"mode": ident})
            except ServeurEteint:
                return self._changer_dans_fichier(ident)
            if statut == 400:
                raise ErreurCrew(f"Le serveur Crew ne connaît pas le mode « {ident} »")
            if statut != 200:
                raise ErreurCrew(f"Changement de mode refusé (code {statut})")
            try:
                actuel, modes = analyser_mode(texte)
            except ValueError as e:
                raise ErreurCrew(str(e))
            self._enregistrer_cache(modes)
            journal.info("Mode Crew changé par l'API : %s", actuel)
            return InfoMode(actuel=actuel, modes=modes, serveur_actif=True)

    def _changer_dans_fichier(self, ident):
        connus = [m.id for m in self._modes_du_cache()]
        if connus and ident not in connus:
            raise ErreurCrew(f"Mode inconnu : « {ident} »")
        donnees = self._lire_fichier_mode()
        donnees["mode"] = ident          # les autres réglages du fichier sont gardés
        try:
            self.sys.ecrire_fichier(R.FICHIER_MODE_CREW, json.dumps(donnees, ensure_ascii=False))
        except OSError as e:
            raise ErreurCrew(f"Impossible d'écrire {R.FICHIER_MODE_CREW} : {e}")
        journal.info("Mode Crew changé dans le fichier (serveur éteint) : %s", ident)
        return self._info_depuis_fichier("Serveur Crew éteint")

    def lire_autorisations(self, crew_actif=True):
        """Autorisations de Claude et Codex dans Crew (lecture seule, aucun effet)."""
        if not crew_actif:
            raise ServeurEteint("Serveur Crew éteint")
        statut, texte = self._appel("GET", R.URL_CREW_AUTORISATIONS)
        if statut != 200:
            raise ErreurCrew(f"/autorisations a répondu {statut}")
        try:
            return analyser_autorisations(texte)
        except ValueError as e:
            raise ErreurCrew(str(e))

    def definir_autorisation(self, nom, autorise, limite_jour=None):
        """Change l'autorisation d'UNE IA. À n'appeler que sur un clic de l'utilisateur. Renvoie la liste complète à jour."""
        if nom not in NOMS_AUTORISATION:
            raise ErreurDemande("IA inconnue : seules Claude et Codex se règlent ici.")
        if not isinstance(autorise, bool):
            raise ErreurDemande("« Autoriser » doit être oui ou non.")
        corps = {"nom": nom, "autorise": autorise}
        if limite_jour is not None:
            if not isinstance(limite_jour, int) or isinstance(limite_jour, bool) or not LIMITE_MIN <= limite_jour <= LIMITE_MAX:
                raise ErreurDemande(f"La limite par jour doit être un nombre entier de {LIMITE_MIN} à {LIMITE_MAX}.")
            corps["limite_jour"] = limite_jour
        statut, texte = self._appel("PUT", R.URL_CREW_AUTORISATIONS, corps)
        if statut == 400:
            raise ErreurDemande("Crew a refusé ce réglage" + self._detail_erreur(texte))
        if statut != 200:
            raise ErreurCrew(f"/autorisations a répondu {statut}")
        try:
            return analyser_autorisations(texte)
        except ValueError as e:
            raise ErreurCrew(str(e))

    @staticmethod
    def _detail_erreur(texte):
        try:
            d = json.loads(texte)
            m = (d.get("error") or {}).get("message") if isinstance(d.get("error"), dict) else d.get("detail")
            return f" ({str(m)[:200]})" if m else "."
        except (ValueError, AttributeError, TypeError):
            return "."

    def lire_chef(self, crew_actif=True):
        """GET /chef (lecture seule, aucun effet)."""
        if not crew_actif:
            raise ServeurEteint("Serveur Crew éteint")
        statut, texte = self._appel("GET", R.URL_CREW_CHEF)
        if statut != 200:
            raise ErreurCrew(f"/chef a répondu {statut}")
        try:
            return analyser_chef(texte)
        except ValueError as e:
            raise ErreurCrew(str(e))

    def definir_chef(self, modele):
        """PUT /chef : Crew change le chef en arrière-plan (202). À n'appeler que sur un clic de l'utilisateur. Renvoie le « changement »."""
        if not identifiant_modele_valide(modele):
            raise ErreurDemande("Identifiant de modèle invalide.")
        statut, texte = self._appel("PUT", R.URL_CREW_CHEF, {"modele": modele})
        if statut in (200, 202):
            try:
                ch = analyser_chef('{"changement": ' + json.dumps((json.loads(texte) or {}).get("changement")) + "}").changement
            except (ValueError, AttributeError, TypeError):
                ch = None
            return ch or {"etat": "en_cours", "cible": modele, "etape": "Démarrage du changement…", "message": "", "debut": None}
        detail = self._detail_erreur(texte)
        if statut == 400:
            raise ErreurDemande("Crew refuse ce modèle" + detail, 400)
        if statut == 409:
            raise ErreurDemande("Crew est occupé" + detail, 409)
        if statut == 503:
            raise ErreurDemande("LM Studio est arrêté" + detail, 503)
        raise ErreurCrew(f"/chef a répondu {statut}")

    def _operation_chef(self, suffixe, corps=None):
        """POST /chef/liberer ou /chef/reprendre : décharge ou recharge le chef de LM Studio (Crew le fait, jamais le Centre). Renvoie le « changement »."""
        statut, texte = self._appel("POST", R.URL_CREW_CHEF + suffixe, corps or {})
        if statut in (200, 202):
            try:
                ch = analyser_chef('{"changement": ' + json.dumps((json.loads(texte) or {}).get("changement")) + "}").changement
            except (ValueError, AttributeError, TypeError):
                ch = None
            return ch or {"etat": "en_cours", "cible": "", "etape": "En cours…", "message": "", "debut": None}
        detail = self._detail_erreur(texte)
        if statut == 404:
            raise ErreurDemande("Cette version de Crew ne sait pas libérer la carte graphique (adresse introuvable).", 404)
        if statut == 409:
            raise ErreurDemande("Crew est occupé (un travail ou une table ronde est en cours)" + detail, 409)
        if statut == 503:
            raise ErreurDemande("LM Studio est arrêté" + detail, 503)
        raise ErreurCrew(f"/chef{suffixe} a répondu {statut}")

    def liberer_chef(self):
        return self._operation_chef("/liberer")

    def reprendre_chef(self):
        return self._operation_chef("/reprendre")

    def lire_moteurs(self, crew_actif=True):
        """Liste des IA que Crew peut utiliser (seulement si le serveur tourne)."""
        if not crew_actif:
            return InfoMoteurs(None, "Serveur Crew éteint")
        try:
            statut, texte = self._appel("GET", R.URL_CREW_MOTEURS)
        except ErreurCrew as e:
            return InfoMoteurs(None, str(e))
        if statut != 200:
            return InfoMoteurs(None, f"/moteurs a répondu {statut}")
        try:
            return InfoMoteurs(analyser_moteurs(texte))
        except ValueError as e:
            return InfoMoteurs(None, str(e))
