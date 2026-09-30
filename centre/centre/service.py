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


DUREE_CHEF = 30.0          # un GET /chef plus vieux que cela n'est plus cru : on relit le fichier de secours
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
        if self.config.dossier_comfyui:
            self.ctrl.dossier_comfyui = self.config.dossier_comfyui      # validé (chemin sûr, deux scripts présents) à chaque emploi
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
        self._chef_info = None          # dernier GET /chef réussi (InfoChef) ; périmé après DUREE_CHEF secondes
        self._chef_le = 0.0
        self._chef_ancien = None        # chef avant le dernier changement demandé (pour « Revenir à … »)
        self.maj = None                 # instant de la dernière vérification
        self._derniere_demande = 0.0
        self._job = None
        self._job_compteur = 0
        self._mode_jeu_vigueur = False    # « Mode jeu » lancé et rien n'a été rallumé depuis : on ne recharge ni ne démarre rien derrière lui
        self._rafraichissement = threading.Lock()
        self._arret = threading.Event()
        self._fil = None
        from .salles import Salles          # après tout le reste : Salles s'appuie sur ce Centre
        self.salles = Salles(self, reseau=reseau, processus=processus)
        from .comfyui import ComfyUI
        self.comfyui = ComfyUI(self)
        from .images import Images
        self.images = Images(self)
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
        try:
            self.salles.nettoyer_pieces()               # images téléversées puis jamais envoyées (plus d'un jour)
        except Exception:
            journal.exception("nettoyage des images impossible")
        while not self._arret.is_set():
            if time.monotonic() - self._derniere_demande < INACTIVITE_RAFRAICHISSEMENT:
                try:
                    self.rafraichir()
                except Exception:
                    journal.exception("vérification impossible")
            try:
                self.comfyui.surveiller()                   # ComfyUI lancé par le Centre et inutilisé depuis 10 minutes : arrêt
            except Exception:
                journal.exception("surveillance de ComfyUI impossible")
            self._arret.wait(DELAI_RAFRAICHISSEMENT)

    def rafraichir(self):
        """Vérifie tous les voyants (une seule vérification à la fois ; pas pendant une action)."""
        if self.action_en_cours() or not self._rafraichissement.acquire(blocking=False):
            return
        try:
            self.actualiser_chef()                       # AVANT les voyants : ils vérifient le modèle du chef actuel
            etats = self.ctrl.verifier_tout()
            cles = self.ctrl.verifier_cles()
            if etats["crew"].code == self.L.ACTIF and self._chef_info is None:
                self.actualiser_chef(crew_actif=True)    # Crew vient d'être vu actif : on lit tout de suite son chef
            info = self.crew.lire_mode(crew_actif=etats["crew"].code == self.L.ACTIF)
            with self._verrou:
                if not self.action_en_cours():
                    self.etats = etats
                    if self._mode_jeu_vigueur and (etats["lmstudio"].code == self.L.ACTIF or etats["crew"].code == self.L.ACTIF):
                        self._mode_jeu_vigueur = False       # quelqu'un a rallumé LM Studio ou Crew : ce n'est plus le Mode jeu
                self.cles = cles
                self.info_mode = info
                self.maj = time.time()
        finally:
            self._rafraichissement.release()

    # ----- chef local de Crew (modèle LM Studio) ----------------------------------------------------

    def actualiser_chef(self, crew_actif=None):
        """Interroge Crew (GET /chef, lecture seule) si Crew répond ; sinon on retombe sur le fichier de secours. Jamais d'écriture."""
        if crew_actif is None:
            crew_actif = self.etats["crew"].code == self.L.ACTIF
        info = None
        if crew_actif:
            try:
                info = self.crew.lire_chef(crew_actif=True)
            except self.C.ErreurCrew as e:
                journal.info("GET /chef impossible : %s", e)
        nouveau = self._chef_courant(info)
        with self._verrou:
            ancien = self._chef_courant(self._chef_info) if self._chef_info is not None else None
            self._chef_info = info
            self._chef_le = time.monotonic()
            if ancien is not None and info is not None and ancien.modele != nouveau.modele:
                self.maj = None                          # le chef a changé : les voyants et les salles se revérifient tout de suite
        self.ctrl.definir_chef_connu(nouveau)
        self.salles.synchroniser_lm(info)
        return info

    def _chef_courant(self, info):
        if info is not None and info.chef:
            autres = next((m for m in info.modeles if m["id"] == info.chef), {})
            return self.C.chef_depuis_donnees({"modele": info.chef, "contexte": autres.get("contexte"), "parallele": autres.get("parallele")})
        return self.C.lire_chef_fichier(self.sys.lire_fichier(self.L.R.FICHIER_CHEF))

    def chef_actuel(self):
        """Chef local (Chef : modele, contexte, parallele) : GET /chef récent, sinon chef_crew.json, sinon gemma."""
        with self._verrou:
            info, age = self._chef_info, time.monotonic() - self._chef_le
        return self._chef_courant(info if age < DUREE_CHEF else None)

    def nom_chef(self):
        """Nom lisible du chef (pour les écrans)."""
        ch = self.chef_actuel()
        with self._verrou:
            info = self._chef_info
        m = next((x for x in (info.modeles if info else []) if x["id"] == ch.modele), None)
        return (m or {}).get("libelle") or self.salles.nom_modele(ch.modele)

    def chef(self):
        """Tout ce que la page « Chef d'équipe » affiche. Crew arrêté / Mode jeu / LM Studio arrêté : lecture du fichier, interrupteurs désactivés."""
        self.noter_demande()
        info = self.actualiser_chef()
        crew_actif = self.etats["crew"].code == self.L.ACTIF
        if not crew_actif:
            # L'état peut dater : on revérifie vite avant d'affirmer que Crew est arrêté.
            self.assurer_etats(age_max=5)
            crew_actif = self.etats["crew"].code == self.L.ACTIF
            if crew_actif and info is None:
                info = self.actualiser_chef()
        courant = self.chef_actuel()
        raison, source = "", "crew"
        if info is None:
            source = "fichier"
            raison = ("Crew est arrêté (ou en Mode jeu) : le chef ci-dessous vient du fichier de secours. Allumez Crew pour en changer."
                      if not crew_actif else "Crew ne répond pas à la demande du chef : allumez-le ou réessayez.")
        elif not info.lmstudio:
            raison = info.message or "LM Studio est arrêté : allumez-le pour changer de chef."
        modeles = []
        if info is not None and info.lmstudio:
            modeles = [dict(m) for m in info.modeles]
        else:                                        # liste mémorisée (salles connues) : on voit au moins les modèles, sans pouvoir les activer
            for m in self.salles.modeles_connus():
                modeles.append({"id": m["modele"], "libelle": m["libelle"], "taille_go": m.get("taille_go"), "params": m.get("params", ""),
                                "architecture": "", "quantification": m.get("quantification", ""), "charge": False, "chef": False,
                                "contexte": None, "parallele": None, "avertissement": None})
            if not any(m["id"] == courant.modele for m in modeles):
                modeles.insert(0, {"id": courant.modele, "libelle": self.salles.nom_modele(courant.modele), "taille_go": None, "params": "",
                                   "architecture": "", "quantification": "", "charge": False, "chef": True, "contexte": courant.contexte,
                                   "parallele": courant.parallele, "avertissement": None})
            for m in modeles:
                m["chef"] = m["id"] == courant.modele
        chargement = info.changement if info is not None else None
        en_cours = bool(chargement and chargement["etat"] == "en_cours")
        return {"source": source, "modifiable": bool(info is not None and info.lmstudio and not en_cours) and not raison, "raison": raison,
                "lmstudio": True if info is None else info.lmstudio, "chef": courant.modele, "chef_nom": self.nom_chef(),
                "chef_charge": bool(info.chef_charge) if info is not None else self.etats["gemma"].code == self.L.ACTIF,
                "changement": chargement, "modeles": modeles, "dernier_test": info.dernier_test if info is not None else None,
                "message": (info.message if info is not None else ""), "ancien_chef": self._chef_ancien,
                "ancien_nom": self.salles.nom_modele(self._chef_ancien) if self._chef_ancien else ""}

    def definir_chef(self, modele, session=""):
        """UNIQUEMENT sur un clic de l'utilisateur. Crew fait tout (décharge, charge, teste, désigne) ; le Centre ne touche ni LM Studio ni le fichier."""
        if not self.C.identifiant_modele_valide(modele):
            self.recus.ajouter("chef_crew", "refuse", session=session, raison="identifiant")
            raise ErreurService("Identifiant de modèle invalide.", 400)
        if self.etats["crew"].code != self.L.ACTIF:
            raise ErreurService("Le serveur Crew est éteint (ou en Mode jeu) : allumez-le pour changer de chef.", 422)
        avant = self.chef_actuel().modele
        try:
            changement = self.crew.definir_chef(modele)
        except self.C.ErreurDemande as e:
            self.recus.ajouter("chef_crew", "refuse", modele=str(modele)[:80], code=e.code, session=session)
            raise ErreurService(str(e), e.code)
        except self.C.ErreurCrew as e:
            self.recus.ajouter("chef_crew", "erreur", modele=str(modele)[:80], session=session)
            raise ErreurService(str(e), 422)
        self._chef_ancien = avant if avant != modele else self._chef_ancien
        self.recus.ajouter("chef_crew", "ok", modele=modele, session=session)
        return {"changement": changement}

    # ----- ComfyUI : état, réconciliation au démarrage, actions à la main ---------------------------------------------

    def comfyui_etat(self):
        """Ce que l'écran affiche : ComfyUI répond-il, la carte graphique est-elle encore libérée ? (rien n'est jamais fait tout seul ici)"""
        self.noter_demande()
        crew_actif = self.etats["crew"].code == self.L.ACTIF
        info = self.actualiser_chef() if crew_actif else None
        repond = self.comfyui.repond()
        if not repond:
            self.comfyui.demarre_par_le_centre = False
        installe, raison = self.comfyui.installe()
        en_cours = self.images.local_en_cours()
        jeu = self.mode_jeu_actif()
        libere = bool(info is not None and info.libere)
        return {"installe": installe, "raison": raison, "repond": repond, "demarre_par_le_centre": bool(repond and self.comfyui.demarre_par_le_centre),
                "creation_en_cours": en_cours, "mode_jeu": jeu, "crew_actif": crew_actif, "chef_libere": libere,
                "bandeau_chef": bool(libere and not en_cours and not jeu and not repond),         # « La carte graphique est encore libérée. Recharger le chef ? »
                "bandeau_comfyui": bool(repond and not en_cours),                                 # « ComfyUI tourne et occupe la carte graphique [Arrêter] »
                "journal": self.comfyui.journal_comfyui()}

    def arreter_comfyui(self, session=""):
        """Bouton « Arrêter » : le même script que le panneau. Jamais pendant une création."""
        if self.images.local_en_cours():
            raise ErreurService("Une création d'image locale est en cours : attendez la fin (ou annulez-la) avant d'arrêter ComfyUI.", 409)
        try:
            ferme = self.comfyui.arreter()
        except Exception as e:
            journal.exception("Arrêt de ComfyUI impossible")
            raise ErreurService(f"Arrêt de ComfyUI impossible : {e}", 500)
        self.recus.ajouter("comfyui", "arret_manuel" if ferme else "arret_echec", session=session)
        if not ferme:
            raise ErreurService("ComfyUI répond encore après la demande d'arrêt.", 502)
        return self.comfyui_etat()

    def reprendre_chef(self, session=""):
        """Bouton « Recharger le chef » : POST /chef/reprendre de Crew (idempotent). Jamais en Mode jeu, ni pendant une création, ni tant que ComfyUI occupe la carte."""
        if self.mode_jeu_actif():
            raise ErreurService("Le Mode jeu est actif : la carte graphique reste libre pour le jeu. Rien n'est rechargé.", 409)
        if self.etats["crew"].code != self.L.ACTIF:
            raise ErreurService("Le serveur Crew est éteint : allumez-le pour recharger le chef.", 422)
        if self.images.local_en_cours():
            raise ErreurService("Une création d'image locale est en cours : le chef sera rechargé à la fin.", 409)
        if self.comfyui.repond():
            raise ErreurService("ComfyUI occupe encore la carte graphique : arrêtez-le d'abord, puis rechargez le chef.", 409)
        try:
            changement = self.crew.reprendre_chef()
        except self.C.ErreurDemande as e:
            self.recus.ajouter("chef_crew", "reprise_refusee", code=e.code, session=session)
            raise ErreurService(str(e), e.code)
        except self.C.ErreurCrew as e:
            self.recus.ajouter("chef_crew", "reprise_erreur", session=session)
            raise ErreurService(str(e), 422)
        self.recus.ajouter("chef_crew", "reprise", session=session)
        return {"changement": changement}

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
        nom_chef = self.nom_chef()
        with self._verrou:
            composants = [{"ident": c.ident, "nom": c.nom,
                           "description": (f"Modèle chef de Crew : {nom_chef} (à changer dans « Chef d'équipe »)" if c.ident == "gemma" else c.description),
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

    def mode_jeu_actif(self):
        """Le Mode jeu est-il en train de libérer la carte graphique, ou en vigueur depuis ? (alors on ne recharge ni ne démarre rien derrière lui)"""
        with self._verrou:
            return bool(self._mode_jeu_vigueur or (self._job and self._job["type"] == "mode_jeu" and self._job["statut"] == "en_cours"))

    def lancer_action(self, sens, ident=None, avec_liees=False, session=""):
        L = self.L
        if sens in SEQUENCES:
            etapes = ([("demarrer", i) for i in L.ordre_tout_demarrer()] if sens == "tout_demarrer"
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
            if sens == "mode_jeu":
                self._mode_jeu_vigueur = True
            elif sens == "tout_demarrer" or (sens == "demarrer" and ident != "comfyui"):
                self._mode_jeu_vigueur = False
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
        comfy_avant = any(i == "comfyui" for s, i in etapes if s == "demarrer") and self.comfyui.repond()
        try:
            resultats = self.ctrl.executer_sequence(etapes, progres)
            if ("demarrer", "comfyui") in etapes and not comfy_avant and resultats.get("comfyui") and resultats["comfyui"].code == self.L.ACTIF:
                self.comfyui.noter_demarrage_manuel()        # lancé par le bouton : le Centre l'arrêtera après 10 minutes d'inactivité
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
                             "voyant": self.C.couleur_moteur(m.etat), "detail": m.detail, "abonnement": m.abonnement}
                            for m in info.moteurs], "message": ""}

    # ----- Claude et Codex (abonnement) dans Crew ------------------------------------------------

    def _json_autorisations(self, liste):
        return {"disponible": True, "message": "", "limite_min": self.C.LIMITE_MIN, "limite_max": self.C.LIMITE_MAX,
                "autorisations": [{"nom": a.nom, "autorise": a.autorise, "limite_jour": a.limite_jour, "utilise_aujourdhui": a.utilise_aujourdhui}
                                  for a in liste]}

    def autorisations(self):
        """Lecture seule. Crew arrêté ou injoignable : pas d'erreur, un message (l'écran l'affiche à la place des réglages)."""
        try:
            return self._json_autorisations(self.crew.lire_autorisations(crew_actif=self.etats["crew"].code == self.L.ACTIF))
        except self.C.ErreurCrew as e:
            return {"disponible": False, "message": str(e), "autorisations": []}

    def definir_autorisation(self, nom, autorise, limite_jour=None, session=""):
        """UNIQUEMENT sur un clic de l'utilisateur (route PUT protégée par la session, le NIP à distance et l'en-tête anti-CSRF)."""
        if self.etats["crew"].code != self.L.ACTIF:
            raise ErreurService("Le serveur Crew est éteint : allumez-le pour régler les autorisations.", 422)
        try:
            liste = self.crew.definir_autorisation(nom, autorise, limite_jour)
        except self.C.ErreurDemande as e:
            self.recus.ajouter("autorisation_crew", "refuse", ia=str(nom)[:20], session=session)
            raise ErreurService(str(e), 400)
        except self.C.ErreurCrew as e:
            self.recus.ajouter("autorisation_crew", "erreur", ia=str(nom)[:20], session=session)
            raise ErreurService(str(e), 422)
        self.recus.ajouter("autorisation_crew", "ok", ia=nom, autorise=autorise, limite_jour=limite_jour, session=session)
        return self._json_autorisations(liste)

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
