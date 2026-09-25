# -*- coding: utf-8 -*-
"""
Simulateur de votre installation (Docker, LM Studio, Crew...).

Il imite les réponses des vraies commandes. Il sert :
  - aux tests automatiques (temps « virtuel » : les attentes sont instantanées) ;
  - au mode démo du panneau (`panneau.pyw --demo`), pour voir l'interface
    sans toucher à rien.
Il ne lance AUCUNE vraie commande.
"""

import json
import re
import threading
import time

import reglages as R
from panneau_logique import Resultat


def _programme(chemin):
    """« C:\\...\\lms.exe » -> « lms » (fonctionne avec \\ et /)."""
    nom = re.split(r"[\\/]", chemin)[-1].lower()
    return nom[:-4] if nom.endswith(".exe") else nom


class Simulateur:
    def __init__(self, temps_reel=False):
        self.temps_reel = temps_reel
        self._t = 0.0
        self._verrou = threading.RLock()
        self.commandes = []                   # historique, pour les tests

        # État simulé de la machine
        self.docker_ouvert = False            # Docker Desktop.exe tourne
        self.docker_pret_a = None             # instant où le moteur répond
        self.conteneurs = {R.CONTENEUR_WEBUI: False, R.CONTENEUR_KOKORO: False}
        self.webui_pret_a = 0.0
        self.lms_serveur = False
        self.modeles = {R.MODELE_GEMMA: 0, R.MODELE_EMBEDDINGS: 0}  # nb de copies
        self.crew_pids = []
        self.crew_pret_a = 0.0
        self.cles = {"DEEPSEEK_API_KEY": "sk-secret-ne-pas-afficher"}

        # Options de scénario
        self.delai_docker = 20
        self.delai_webui = 10
        self.delai_crew = 4
        self.desktop_stop_existe = True       # « docker desktop stop » disponible ?
        self.docker_desktop_installe = True
        self.api_v0_existe = True             # anciennes versions de LM Studio : 404
        self.lms_ps_json = True               # `lms ps --json` accepté ?
        self.crew_plante = False              # le serveur Crew s'arrête aussitôt lancé
        self.webui_existe = True
        self._pid = 4000

    # ----- temps -----------------------------------------------------------

    def maintenant(self):
        return time.monotonic() if self.temps_reel else self._t

    def dormir(self, secondes):
        if self.temps_reel:
            time.sleep(secondes)
        else:
            self._t += secondes

    # ----- état pratique ---------------------------------------------------

    def docker_pret(self):
        return self.docker_ouvert and self.maintenant() >= self.docker_pret_a

    def tout_allumer(self):
        """Met la machine simulée dans l'état « tout fonctionne »."""
        self.docker_ouvert, self.docker_pret_a = True, self.maintenant()
        self.conteneurs = {k: True for k in self.conteneurs}
        self.webui_pret_a = self.maintenant()
        self.lms_serveur = True
        self.modeles = {k: 1 for k in self.modeles}
        self.crew_pids = [101, 102]
        self.crew_pret_a = self.maintenant()

    # ----- interface « système » identique à SystemeWindows -----------------

    def chemin_programme(self, nom_court, candidats):
        return nom_court or candidats[0]

    def fichier_existe(self, chemin):
        if chemin in R.DOCKER_DESKTOP_CANDIDATS:
            return self.docker_desktop_installe and chemin == R.DOCKER_DESKTOP_CANDIDATS[0]
        return True

    def ouvrir_programme(self, chemin):
        with self._verrou:
            self.commandes.append(["ouvrir", chemin])
            if not self.docker_ouvert:
                self.docker_ouvert = True
                self.docker_pret_a = self.maintenant() + self.delai_docker

    def variable_utilisateur_presente(self, nom_var):
        return bool(self.cles.get(nom_var))

    def powershell(self, script, delai):
        return self.executer(["powershell.exe", "-Command", script], delai)

    def executer(self, args, delai):
        with self._verrou:
            self.commandes.append(list(args))
            prog = _programme(args[0])
            if prog == "docker":
                return self._docker(args[1:])
            if prog == "lms":
                return self._lms(args[1:])
            if prog == "tasklist":
                if self.docker_ouvert:
                    return Resultat(0, '"Docker Desktop.exe","5120","Console","1","150 000 Ko"\r\n')
                return Resultat(0, "INFORMATIONS : aucune tâche en service ne correspond aux critères.\r\n")
            if prog == "taskkill":
                return self._taskkill(args[1:])
            if prog == "powershell":
                return self._powershell(args[-1])
            return Resultat(None, "", f"programme introuvable : {args[0]}")

    def http_get(self, url, delai):
        with self._verrou:
            maintenant = self.maintenant()
            if url == R.URL_WEBUI:
                if self.docker_pret() and self.conteneurs.get(R.CONTENEUR_WEBUI) \
                        and maintenant >= self.webui_pret_a:
                    return 200, '{"version": "0.6.5"}'
                return None, "connexion refusée"
            if url == R.URL_LMSTUDIO:
                return (200, '{"data": []}') if self.lms_serveur else (None, "connexion refusée")
            if url == R.URL_LMSTUDIO_MODELES:
                if not self.lms_serveur:
                    return None, "connexion refusée"
                if not self.api_v0_existe:
                    return 404, "Not Found"
                return 200, json.dumps({"object": "list", "data": self._liste_api()})
            if url == R.URL_CREW_SANTE:
                if self.crew_pids and maintenant >= self.crew_pret_a:
                    return 200, '{"ok": true}'
                return None, "connexion refusée"
            return None, "adresse inconnue du simulateur"

    # ----- détails de la simulation -----------------------------------------

    def _liste_api(self):
        donnees = [{"id": "qwen2.5-7b-instruct", "state": "not-loaded", "type": "llm"}]
        for cle, copies in self.modeles.items():
            if copies == 0:
                donnees.append({"id": cle, "state": "not-loaded"})
            for n in range(copies):
                donnees.append({"id": cle if n == 0 else f"{cle}:{n + 1}", "state": "loaded"})
        return donnees

    def _identifiants_charges(self):
        return [e["id"] for e in self._liste_api() if e["state"] == "loaded"]

    def _docker(self, args):
        erreur_moteur = Resultat(1, "", "error during connect: open //./pipe/dockerDesktopLinuxEngine: "
                                        "Le fichier spécifié est introuvable.")
        if args[:2] == ["desktop", "stop"]:
            if not self.desktop_stop_existe:
                return Resultat(1, "", "docker: 'desktop' is not a docker command.\nSee 'docker --help'")
            self._fermer_docker()
            return Resultat(0, "Docker Desktop stopped")
        if not self.docker_pret():
            return erreur_moteur
        if args[0] == "info":
            return Resultat(0, "Server:\n Containers: 2\n")
        nom_c = args[-1]
        if nom_c not in self.conteneurs or (nom_c == R.CONTENEUR_WEBUI and not self.webui_existe):
            return Resultat(1, "", f"Error: No such object: {nom_c}")
        if args[0] == "inspect":
            return Resultat(0, "true\n" if self.conteneurs[nom_c] else "false\n")
        if args[0] == "start":
            self.conteneurs[nom_c] = True
            if nom_c == R.CONTENEUR_WEBUI:
                self.webui_pret_a = self.maintenant() + self.delai_webui
            return Resultat(0, nom_c + "\n")
        if args[0] == "stop":
            self.conteneurs[nom_c] = False
            return Resultat(0, nom_c + "\n")
        return Resultat(1, "", "commande docker non simulée")

    def _fermer_docker(self):
        self.docker_ouvert = False
        self.conteneurs = {k: False for k in self.conteneurs}

    def _taskkill(self, args):
        if "/IM" in args:
            image = args[args.index("/IM") + 1].lower()
            if image == "docker desktop.exe" and self.docker_ouvert:
                self._fermer_docker()
                return Resultat(0, "Opération réussie.")
            return Resultat(128, "", "Erreur : processus introuvable.")
        pids = [int(args[i + 1]) for i, a in enumerate(args) if a == "/PID"]
        self.crew_pids = [p for p in self.crew_pids if p not in pids]
        return Resultat(0, "Opération réussie.")

    def _lms(self, args):
        if args == ["server", "start"]:
            self.lms_serveur = True
            return Resultat(0, "Success! Server is now running on port 1234")
        if args == ["server", "stop"]:
            self.lms_serveur = False   # comme le vrai : les modèles restent chargés
            return Resultat(0, "Stopped the server on port 1234.")
        if args and args[0] == "load":
            cle = args[1]
            if cle not in self.modeles:
                return Resultat(1, "", f"Error: model not found: {cle}")
            self.modeles[cle] += 1     # comme le vrai : charge une copie de plus
            return Resultat(0, "\x1b[32mModel loaded successfully\x1b[0m")
        if args and args[0] == "unload":
            ident = args[1]
            cle = re.sub(r":\d+$", "", ident)
            if self.modeles.get(cle, 0) == 0:
                return Resultat(1, "", f"Error: no loaded model with identifier {ident}")
            self.modeles[cle] -= 1
            return Resultat(0, f"Model \"{ident}\" unloaded.")
        if args and args[0] == "ps":
            ids = self._identifiants_charges()
            if "--json" in args:
                if not self.lms_ps_json:
                    return Resultat(1, "", "error: unknown option '--json'")
                return Resultat(0, json.dumps([{"identifier": i, "modelKey": re.sub(r":\d+$", "", i),
                                                "type": "llm"} for i in ids]))
            if not ids:
                return Resultat(0, "\nNo models are currently loaded\n")
            lignes = ["", "LOADED MODELS", ""]
            for i in ids:
                lignes += [f"Identifier: {i}", "  • Type:  LLM", ""]
            return Resultat(0, "\n".join(lignes))
        return Resultat(1, "", "commande lms non simulée")

    def _powershell(self, script):
        if "Invoke-CimMethod" in script:
            if not self.crew_plante and self.modeles[R.MODELE_GEMMA] > 0:
                self._pid += 2
                self.crew_pids = [self._pid, self._pid + 1]  # lanceur du venv + interpréteur
                self.crew_pret_a = self.maintenant() + self.delai_crew
            return Resultat(0, "RETOUR=0\r\n")
        if "Get-CimInstance" in script:
            return Resultat(0, "".join(f"{p}\r\n" for p in self.crew_pids))
        return Resultat(1, "", "script PowerShell non simulé")
