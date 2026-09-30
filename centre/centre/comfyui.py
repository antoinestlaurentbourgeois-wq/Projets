# -*- coding: utf-8 -*-
"""
ComfyUI (images locales) : démarré À LA DEMANDE, arrêté ensuite, jamais au démarrage de Windows ni par « Tout démarrer ».

Sécurité (à respecter absolument) :
  - ComfyUI n'est lancé et arrêté QUE par les deux scripts fournis (demarrer_comfyui.ps1, arreter_comfyui.ps1), appelés tels quels
    par le panneau (liste d'arguments, aucun argument, un délai) ; le dossier est fixe (I:\\IA\\ComfyUI) ou la clé « dossier_comfyui »
    de reglages.json, validée (chemin sûr, les deux scripts présents) ; AUCUN texte venant d'un utilisateur, d'une IA ou d'une image
    n'entre jamais dans une commande ;
  - le Centre ne charge ni ne décharge JAMAIS LM Studio : pour la carte graphique partagée avec le chef, il n'appelle que les adresses de Crew
    (POST /chef/liberer, POST /chef/reprendre) ;
  - ComfyUI lancé par le Centre s'arrête tout seul après 10 minutes d'inactivité (sécurité mémoire) ;
  - aucune clé, aucun NIP, aucune description d'image dans les journaux.

Ce module ne fait que le travail sur le processus (démarrer, arrêter, surveiller). L'enchaînement complet d'une création locale
(libérer le chef, démarrer, créer, arrêter, reprendre) est dans images.py, avec un « finally » qui remet tout en ordre.
"""

import json
import logging
import time

from . import ia

journal = logging.getLogger("centre")

URL_COMFY = "http://127.0.0.1:8188"
DELAI_INACTIVITE = 600            # secondes : ComfyUI démarré par le Centre et inutilisé depuis ce temps est arrêté
PAUSE_MEMOIRE = 3.0               # après l'arrêt : le temps que la mémoire vidéo soit rendue avant de recharger le chef
ATTENTE_PORT = 30                 # secondes : le port 8188 doit être fermé (ou ouvert) dans ce délai


class ErreurComfyUI(Exception):
    def __init__(self, message, code=409):
        super().__init__(message)
        self.code = code


class ComfyUI:
    def __init__(self, centre, horloge=time.time, dormir=time.sleep):
        self.centre = centre
        self.horloge, self.dormir = horloge, dormir
        self.demarre_par_le_centre = False       # vrai si C'EST le Centre qui a lancé le ComfyUI qui tourne (alors c'est à lui de l'arrêter)
        self.derniere_activite = 0.0
        self.pause_memoire = PAUSE_MEMOIRE
        self.attente_port = ATTENTE_PORT
        self.pas = 1.0

    # ----- lecture -------------------------------------------------------------------------------------------------------

    def repond(self):
        try:
            code, _ = self.centre.salles.reseau.requete("GET", URL_COMFY + "/system_stats", delai=2)
        except ia.ErreurReseau:
            return False
        return code == 200

    def scripts(self):
        """(script de démarrage, script d'arrêt) ; ErreurComfyUI (message clair) si le dossier n'est pas valide ou si les scripts manquent."""
        try:
            return self.centre.ctrl.scripts_comfyui()
        except self.centre.L.ErreurAction as e:
            raise ErreurComfyUI(str(e), 409)

    def installe(self):
        """(vrai, "") si ComfyUI peut être lancé par le Centre ; sinon (faux, raison)."""
        try:
            self.scripts()
        except ErreurComfyUI as e:
            return False, str(e)
        return True, ""

    def journal_comfyui(self):
        return self.centre.ctrl.journal_comfyui()

    def noter_activite(self):
        self.derniere_activite = self.horloge()

    def _occupe(self):
        """ComfyUI travaille-t-il encore (file de travail non vide) ? False si on ne sait pas."""
        try:
            code, texte = self.centre.salles.reseau.requete("GET", URL_COMFY + "/queue", delai=3)
            d = json.loads(texte) if code == 200 else {}
            return bool(d.get("queue_running") or d.get("queue_pending"))
        except (ia.ErreurReseau, ValueError, AttributeError, TypeError):
            return False

    # ----- démarrer / arrêter ---------------------------------------------------------------------------------------------

    def demarrer(self):
        """Lance demarrer_comfyui.ps1 (délai 120 s) puis vérifie que ComfyUI répond. Renvoie « deja » s'il tournait déjà."""
        if self.repond():
            self.noter_activite()
            return "deja"
        self.scripts()
        self.demarre_par_le_centre = True            # avant le lancement : même en cas d'échec partiel, le « finally » l'arrêtera
        self.noter_activite()
        res = self.centre.ctrl.lancer_script_comfyui("demarrer")
        ok = res.ok
        if ok:
            for _ in range(10):                      # le script a attendu ; on vérifie quand même que le port répond
                if self.repond():
                    break
                self.dormir(self.pas)
            else:
                ok = False
        if not ok:
            journal.warning("ComfyUI n'a pas démarré (code %s)", res.code)
            raise ErreurComfyUI(f"ComfyUI n'a pas démarré. Journal : {self.journal_comfyui()}", 502)
        self.noter_activite()
        return "demarre"

    def arreter(self):
        """Lance arreter_comfyui.ps1, attend que le port 8188 soit fermé, puis patiente 3 s (mémoire rendue). Renvoie vrai si le port est fermé."""
        try:
            self.centre.ctrl.lancer_script_comfyui("arreter")
        except self.centre.L.ErreurAction as e:
            journal.warning("Arrêt de ComfyUI impossible : %s", e)
            return False
        ferme = False
        debut = self.horloge()
        while True:
            if not self.repond():
                ferme = True
                break
            if self.horloge() - debut >= self.attente_port:
                break
            self.dormir(self.pas)
        if ferme:
            self.demarre_par_le_centre = False
            self.dormir(self.pause_memoire)
        else:
            journal.warning("ComfyUI répond encore après la demande d'arrêt")
        self.noter_activite()
        return ferme

    # ----- sécurité mémoire : arrêt après 10 minutes d'inactivité ---------------------------------------------------------------

    def surveiller(self):
        """À appeler régulièrement. Arrête le ComfyUI lancé par le Centre s'il est inutilisé depuis plus de 10 minutes. Renvoie vrai si arrêté."""
        if not self.demarre_par_le_centre:
            return False
        if self.centre.images.local_en_cours():
            self.noter_activite()
            return False
        if not self.repond():
            self.demarre_par_le_centre = False       # il s'est arrêté tout seul (ou par le Mode jeu)
            return False
        if self.horloge() - self.derniere_activite < DELAI_INACTIVITE:
            return False
        if self._occupe():                           # quelqu'un s'en sert directement : on repousse
            self.noter_activite()
            return False
        journal.info("ComfyUI inutilisé depuis plus de 10 minutes : arrêt")
        ferme = self.arreter()
        self.centre.recus.ajouter("comfyui", "arret_inactivite" if ferme else "arret_echec")
        return ferme

    def noter_demarrage_manuel(self):
        """Démarré par le bouton « Démarrer » du Centre (ou du panneau) : c'est au Centre de l'arrêter après 10 minutes d'inactivité."""
        self.demarre_par_le_centre = True
        self.noter_activite()
