# -*- coding: utf-8 -*-
"""
Le « cerveau » du Centre : enveloppe la logique du panneau (Controleur, CrewDistant, Ouvreur)
pour la servir à l'interface web. Aucune interface ici, donc testable avec le simulateur.
"""

import logging
import os
import sys
import threading
import time

from .config import Config
from .cles import Cles
from .couts import Couts, SoldeDeepSeek
from .journal import Recus, preparer_journal

journal = logging.getLogger("centre")


def charger_panneau(dossier_panneau):
    """Rend importables les modules du panneau (reglages, panneau_logique, ...)."""
    if not os.path.isfile(os.path.join(dossier_panneau, "panneau_logique.py")):
        raise RuntimeError(f"Dossier du panneau introuvable : {dossier_panneau} "
                           "(variable CENTRE_PANNEAU pour le changer).")
    if dossier_panneau not in sys.path:
        sys.path.insert(0, dossier_panneau)
    import reglages, panneau_logique, panneau_crew, panneau_ouvrir  # noqa: F401
    return panneau_logique, panneau_crew, panneau_ouvrir


class ErreurService(Exception):
    def __init__(self, message, code=400, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


SENS_SIMPLES = ("demarrer", "arreter")
SEQUENCES = {"tout_demarrer": "Tout démarrer", "mode_jeu": "Mode jeu"}


class Centre:
    def __init__(self, config=None, systeme=None, http_sortant=None, reseau=None, processus=None, amont=None):
        self.config = config or Config()
        os.makedirs(self.config.dossier_donnees, exist_ok=True)
        preparer_journal(self.config.dossier_donnees)
        self.L, self.C, self.O = charger_panneau(self.config.dossier_panneau)
        self.sys = systeme or self.L.SystemeWindows()
        self.ctrl = self.L.Controleur(self.sys)
        self.crew = self.C.CrewDistant(self.sys)
        self.ouvreur = self.O.Ouvreur(self.sys, self.ctrl)
        self.recus = Recus(self.config.chemin("recus.jsonl"))
        self.couts = Couts(self.config.chemin("depenses.jsonl"), self.config.chemin("plafonds.json"))
        kw = {"http": http_sortant} if http_sortant else {}
        self.gestion_cles = Cles(self.sys)
        self.deepseek = SoldeDeepSeek(lambda: self.gestion_cles.lire("deepseek"), **kw)

        self._verrou = threading.RLock()
        self.etats = {c.ident: self.L.Etat(self.L.INCONNU, "Pas encore vérifié") for c in self.L.COMPOSANTS}
        self.cles = {}
        self.info_mode = None
        self.maj = None                 # instant de la dernière vérification
        self._derniere_demande = 0.0
        self._job = None
        self._job_compteur = 0
        self._rafraichissement = threading.Lock()
        self._arret = threading.Event()
        self._fil = None
        from .salles import Salles          # après tout le reste : Salles s'appuie sur ce Centre
        self.salles = Salles(self, reseau=reseau, processus=processus)
        from .rappels import Rappels
        self.rappels = Rappels(self.config.chemin("rappels.json"))
        from .voix import Voix
        self.voix = Voix(self, self.salles.reseau, amont=amont)

    # ----- vérification en arrière-plan ---------------------------------------------------

    def demarrer_fond(self):
        if self._fil or not self.config.rafraichir_en_fond:
            return
        self._fil = threading.Thread(target=self._boucle, name="centre-verif", daemon=True)
        self._fil.start()

    def arreter_fond(self):
        self._arret.set()

    def _boucle(self):
        from .config import DELAI_RAFRAICHISSEMENT, INACTIVITE_RAFRAICHISSEMENT
        while not self._arret.is_set():
            if time.monotonic() - self._derniere_demande < INACTIVITE_RAFRAICHISSEMENT:
                try:
                    self.rafraichir()
                except Exception:
                    journal.exception("vérification impossible")
            self._arret.wait(DELAI_RAFRAICHISSEMENT)

    def rafraichir(self):
        """Vérifie tous les voyants (une seule vérification à la fois ; pas pendant une action)."""
        if self.action_en_cours() or not self._rafraichissement.acquire(blocking=False):
            return
        try:
            etats = self.ctrl.verifier_tout()
            cles = self.ctrl.verifier_cles()
            info = self.crew.lire_mode(crew_actif=etats["crew"].code == self.L.ACTIF)
            with self._verrou:
                if not self.action_en_cours():
                    self.etats = etats
                self.cles = cles
                self.info_mode = info
                self.maj = time.time()
        finally:
            self._rafraichissement.release()

    def noter_demande(self):
        self._derniere_demande = time.monotonic()

    def assurer_etats(self, age_max=10):
        """Garantit des voyants récents pour les pages qui en dépendent (Salles, Voix…), même si la page Centre n'est pas ouverte."""
        self.noter_demande()
        if self.maj is None or time.time() - self.maj > age_max:
            self.rafraichir()

    # ----- état complet pour l'interface ----------------------------------------------------

    def etat(self):
        self.noter_demande()
        if self.maj is None:
            self.rafraichir()
        with self._verrou:
            composants = [{"ident": c.ident, "nom": c.nom, "description": c.description,
                           "dependances": list(c.dependances),
                           "etat": {"code": self.etats[c.ident].code, "message": self.etats[c.ident].message}}
                          for c in self.L.COMPOSANTS]
            return {"composants": composants,
                    "cles": dict(self.cles),
                    "mode": self._mode_json(self.info_mode),
                    "action": self.job_json(),
                    "maj": self.maj}

    @staticmethod
    def _mode_json(info):
        if info is None:
            return None
        return {"actuel": info.actuel,
                "libelle": info.libelle(),
                "modes": [{"id": m.id, "libelle": m.libelle, "explication": m.explication} for m in info.modes],
                "serveur_actif": info.serveur_actif, "modifiable": info.modifiable, "message": info.message}

    # ----- plans (dépendances à confirmer) -------------------------------------------------

    def plan(self, sens, ident):
        if ident not in self.L.PAR_ID:
            raise ErreurService("Composant inconnu.", 404)
        with self._verrou:
            etats = dict(self.etats)
        if sens == "demarrer":
            liste = self.L.dependances_a_demarrer(ident, etats)
        elif sens == "arreter":
            liste = self.L.dependants_a_arreter(ident, etats)
        else:
            raise ErreurService("Sens inconnu.")
        return [{"ident": i, "nom": self.L.nom(i)} for i in liste]

    # ----- actions (une à la fois, en arrière-plan) ----------------------------------------------

    def action_en_cours(self):
        with self._verrou:
            return bool(self._job and self._job["statut"] == "en_cours")

    def job_json(self):
        with self._verrou:
            if not self._job:
                return None
            j = self._job
            return {"id": j["id"], "type": j["type"], "libelle": j["libelle"], "statut": j["statut"],
                    "etapes": list(j["etapes"]), "progres": dict(j["progres"]),
                    "resultats": dict(j["resultats"]), "erreur": j["erreur"]}

    def lancer_action(self, sens, ident=None, avec_liees=False, session=""):
        L = self.L
        if sens in SEQUENCES:
            etapes = ([("demarrer", i) for i in L.ordre_demarrage()] if sens == "tout_demarrer"
                      else [("arreter", i) for i in L.ordre_arret()])
            libelle = SEQUENCES[sens]
        elif sens in SENS_SIMPLES:
            if ident not in L.PAR_ID:
                raise ErreurService("Composant inconnu.", 404)
            liees = self.plan(sens, ident)
            if liees and not avec_liees:
                raise ErreurService("Des composants liés doivent aussi changer d'état.", 409, liees=liees)
            etapes = [(sens, x["ident"]) for x in liees] + [(sens, ident)]
            verbe = "Démarrer" if sens == "demarrer" else "Arrêter"
            libelle = f"{verbe} {L.nom(ident)}"
        else:
            raise ErreurService("Action inconnue.")
        with self._verrou:
            if self._job and self._job["statut"] == "en_cours":
                raise ErreurService("Une autre action est déjà en cours : attendez qu'elle finisse.", 409)
            self._job_compteur += 1
            self._job = {"id": self._job_compteur, "type": sens, "libelle": libelle, "statut": "en_cours",
                         "etapes": [{"sens": s, "ident": i} for s, i in etapes],
                         "progres": {}, "resultats": {}, "erreur": ""}
            job = self._job
        journal.info("Action lancée : %s", libelle)
        self.recus.ajouter("action_lancee", libelle=libelle, sens=sens, ident=ident, session=session)
        threading.Thread(target=self._executer, args=(job, etapes, libelle, session), daemon=True,
                         name="centre-action").start()
        return self.job_json()

    def _executer(self, job, etapes, libelle, session):
        def progres(ident, etat, final):
            with self._verrou:
                job["progres"][ident] = {"code": etat.code, "message": etat.message, "final": bool(final)}
                self.etats[ident] = etat
        try:
            resultats = self.ctrl.executer_sequence(etapes, progres)
            with self._verrou:
                job["resultats"] = {i: {"code": e.code, "message": e.message} for i, e in resultats.items()}
                job["statut"] = "termine"
            echecs = [i for i, e in resultats.items() if e.code not in (self.L.ACTIF, self.L.ARRETE)]
            self.recus.ajouter("action_terminee", "ok" if not echecs else "problemes",
                               libelle=libelle, session=session,
                               etats={i: e.code for i, e in resultats.items()})
        except Exception as e:
            journal.exception("Action %s : erreur inattendue", libelle)
            with self._verrou:
                job["statut"] = "erreur"
                job["erreur"] = f"Erreur inattendue : {e}"
            self.recus.ajouter("action_terminee", "erreur", libelle=libelle, session=session)
        finally:
            try:
                self.rafraichir()
            except Exception:
                journal.exception("vérification après action impossible")

    def attendre_action(self, delai=30):
        """Pour les tests : attend la fin de l'action en cours."""
        fin = time.monotonic() + delai
        while self.action_en_cours() and time.monotonic() < fin:
            time.sleep(0.01)
        return self.job_json()

    # ----- mode Crew -------------------------------------------------------------------------

    def lire_mode(self):
        crew_actif = self.etats["crew"].code == self.L.ACTIF
        info = self.crew.lire_mode(crew_actif=crew_actif)
        with self._verrou:
            self.info_mode = info
        return self._mode_json(info)

    def changer_mode(self, ident, session=""):
        try:
            info = self.crew.changer_mode(ident)
        except self.C.ErreurCrew as e:
            self.recus.ajouter("mode_crew", "refuse", mode=ident, session=session)
            raise ErreurService(str(e), 422)
        with self._verrou:
            self.info_mode = info
        self.recus.ajouter("mode_crew", "ok", mode=info.actuel, session=session)
        return self._mode_json(info)

    def moteurs(self):
        info = self.crew.lire_moteurs(crew_actif=self.etats["crew"].code == self.L.ACTIF)
        if info.moteurs is None:
            return {"moteurs": None, "message": info.message}
        return {"moteurs": [{"nom": m.nom, "libelle": m.libelle, "local": m.local,
                             "capacite": self.C.texte_capacite(m.capacite), "cout": self.C.texte_cout(m.cout),
                             "forces": m.forces, "etat": m.etat, "etat_texte": self.C.TEXTE_ETAT_MOTEUR.get(m.etat, m.etat or "?"),
                             "voyant": self.C.couleur_moteur(m.etat), "detail": m.detail}
                            for m in info.moteurs], "message": ""}

    # ----- ouvrir une application ----------------------------------------------------------------

    def ouvrir(self, ident, session=""):
        if ident not in self.O.OUVRABLES:
            raise ErreurService("Cette application ne peut pas être ouverte ainsi.", 404)
        try:
            ouverture = self.ouvreur.preparer(ident)
            self.ouvreur.executer(ouverture)
        except self.L.ErreurAction as e:
            raise ErreurService(str(e), 422)
        except Exception as e:
            journal.exception("Ouverture de %s impossible", ident)
            raise ErreurService(f"Ouverture impossible : {e}", 500)
        self.recus.ajouter("ouvrir", "ok", ident=ident, session=session)
        return {"message": ouverture.message, "presse_papiers": ouverture.presse_papiers}

    # ----- coûts -----------------------------------------------------------------------------------

    def couts_json(self):
        return self.couts.statut()
