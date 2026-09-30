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

        # Version 2 : fichiers, serveur Crew, conversations Open WebUI, LM Studio
        self.fichiers = {
            R.FICHIER_ENV_CREW: "# réglages\nCREW_API_KEY=cle-crew-secrete\nAUTRE=1\n",
            R.FICHIER_MODE_CREW: '{"mode": "econome"}',
        }
        self.modes_crew = [
            {"id": "econome", "libelle": "Économe", "niveau": "normal", "performance": "econome",
             "explication": "Par défaut. gemma (local, gratuit) analyse chaque demande et la confie "
                            "à l'IA la moins chère capable de la traiter."},
            {"id": "maxperf", "libelle": "MaxPerf", "niveau": "normal", "performance": "maxperf",
             "explication": "Confie chaque demande à l'IA la plus capable, sans regarder le coût."},
            {"id": "confidentiel", "libelle": "Confidentiel", "niveau": "confidentiel",
             "performance": "econome", "explication": "Les données sensibles restent sur le PC."},
            {"id": "ultra", "libelle": "Ultra-confidentiel", "niveau": "ultra", "performance": "econome",
             "explication": "Rien ne sort du PC : seul gemma (local) est utilisé."},
        ]
        self.moteurs_crew_supplementaires = []   # pour tester l'ajout d'une IA
        self.conversations = []   # [{"id", "updated_at", "models": [...]}] pour Open WebUI
        self.webui_liste_format = "liste"        # « liste » ou « items »
        self.autres_modeles_charges = []         # [(id, type, taille)] en plus de gemma/nomic
        self.lmstudio_installe = True
        # Clés attendues par les serveurs simulés (le panneau, lui, lit ses clés ailleurs).
        self.cle_crew_serveur = "cle-crew-secrete"
        self.cle_webui_serveur = "cle-webui-secrete"
        self.table_ronde_couts = {"claude": 0.05, "codex": 0.04, "gemini": 0.0, "grok": 0.06, "deepseek": 0.003, "gemma": 0.0}       # None = tarif inconnu
        self.table_ronde_indispos = {}           # id -> raison (IA grisée)
        self.memoire_disponible = True           # /memoire/* exposé par Crew ?
        self.memoire_docs = [                    # bibliothèque simulée
            {"chemin": "partageable/notes/mecanique.md", "zone": "partageable",
             "texte": "Le couple de serrage des vis M8 est de 25 newton mètres"},
            {"chemin": "prive/clients/contrat.md", "zone": "prive",
             "texte": "Le contrat du client Durand prévoit un prix secret de 12000 euros"},
        ]
        self.ouvertures = []                     # adresses et programmes ouverts
        self.requetes = []                       # (méthode, url, a_une_cle) pour les tests

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
        if chemin in R.LMSTUDIO_EXE_CANDIDATS:
            return self.lmstudio_installe and chemin == R.LMSTUDIO_EXE_CANDIDATS[0]
        return True

    def ouvrir_programme(self, chemin):
        with self._verrou:
            self.commandes.append(["ouvrir", chemin])
            self.ouvertures.append(chemin)
            if chemin in R.DOCKER_DESKTOP_CANDIDATS and not self.docker_ouvert:
                self.docker_ouvert = True
                self.docker_pret_a = self.maintenant() + self.delai_docker

    def ouvrir_url(self, url):
        from panneau_logique import url_est_locale
        if not url_est_locale(url):
            raise ValueError(f"adresse refusée (pas locale) : {url}")
        self.ouvertures.append(url)

    def variable_utilisateur_presente(self, nom_var):
        return bool(self.cles.get(nom_var))

    def valeur_variable_utilisateur(self, nom_var):
        return self.cles.get(nom_var) or None

    def lire_fichier(self, chemin):
        return self.fichiers.get(chemin)

    def ecrire_fichier(self, chemin, texte):
        self.fichiers[chemin] = texte

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
        return self.http("GET", url, delai)

    def http(self, methode, url, delai, entetes=None, corps_json=None):
        from panneau_logique import url_est_locale
        if not url_est_locale(url):
            raise ValueError(f"adresse refusée (pas locale) : {url}")
        with self._verrou:
            auth = (entetes or {}).get("Authorization", "")
            self.requetes.append((methode, url, bool(auth)))
            if url.startswith(R.URL_CREW_MODE) or url.startswith(R.URL_CREW_MOTEURS) \
                    or url.startswith(R.URL_CREW_MEMOIRE_ETAT[:-len("/etat")]) or url in (R.URL_CREW_TABLE_ESTIMATION, R.URL_CREW_TABLE_PARTICIPANTS):
                return self._crew_api(methode, url, auth, corps_json)
            if url.startswith(R.URL_WEBUI_BASE + "/api/v1/chats"):
                return self._webui_api(url, auth)
            return self._http_get(url)

    def _http_get(self, url):
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
            genre = "embeddings" if cle == R.MODELE_EMBEDDINGS else "vlm"
            if copies == 0:
                donnees.append({"id": cle, "state": "not-loaded", "type": genre})
            for n in range(copies):
                donnees.append({"id": cle if n == 0 else f"{cle}:{n + 1}", "state": "loaded",
                                "type": genre})
        for ident, genre, _taille in self.autres_modeles_charges:
            donnees.append({"id": ident, "state": "loaded", "type": genre})
        return donnees

    def _taille(self, ident):
        cle = re.sub(r":\d+$", "", ident)
        if cle == R.MODELE_GEMMA:
            return 7_150_000_000
        if cle == R.MODELE_EMBEDDINGS:
            return 84_000_000
        for i, _g, taille in self.autres_modeles_charges:
            if i == cle:
                return taille
        return 0

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
                genres = {e["id"]: e["type"] for e in self._liste_api()}
                return Resultat(0, json.dumps([{"identifier": i, "modelKey": re.sub(r":\d+$", "", i),
                                                "type": "embedding" if genres.get(i) == "embeddings"
                                                else genres.get(i, "llm"),
                                                "sizeBytes": self._taille(i)} for i in ids]))
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

    # ----- serveur Crew : /mode et /moteurs ----------------------------------

    def _crew_actif(self):
        return bool(self.crew_pids) and self.maintenant() >= self.crew_pret_a

    def _crew_api(self, methode, url, auth, corps_json):
        if not self._crew_actif():
            return None, "connexion refusée"
        if auth != f"Bearer {self.cle_crew_serveur}":
            return 401, '{"detail": "clé invalide"}'
        if url == R.URL_CREW_MOTEURS:
            gemma = self.modeles[R.MODELE_GEMMA] > 0
            moteurs = [
                {"nom": "local", "libelle": "gemma (local, gratuit)", "local": True, "capacite": 1,
                 "cout": 0, "forces": [], "etat": "pret" if gemma else "arrete",
                 "detail": f"{R.MODELE_GEMMA} chargé" if gemma else "gemma n'est pas chargé"},
                {"nom": "gemini", "libelle": "Gemini Flash", "local": False, "capacite": 2, "cout": 1,
                 "forces": ["redacteur"],
                 "etat": "pret" if self.cles.get("GEMINI_API_KEY") else "indisponible",
                 "detail": "Clé GEMINI_API_KEY présente" if self.cles.get("GEMINI_API_KEY")
                 else "Clé GEMINI_API_KEY absente"},
                {"nom": "deepseek", "libelle": "DeepSeek Flash", "local": False, "capacite": 2, "cout": 1,
                 "forces": ["executant", "lecteur"], "etat": "pret",
                 "detail": "Clé DEEPSEEK_API_KEY présente"},
                {"nom": "deepseek-max", "libelle": "DeepSeek V4 Pro", "local": False, "capacite": 3,
                 "cout": 4, "forces": ["executant", "lecteur", "redacteur"], "etat": "pret",
                 "detail": "Clé DEEPSEEK_API_KEY présente"},
            ] + self.moteurs_crew_supplementaires
            return 200, json.dumps({"moteurs": moteurs}, ensure_ascii=False)
        if url == R.URL_CREW_TABLE_PARTICIPANTS:
            return self._crew_table_participants()
        if url == R.URL_CREW_TABLE_ESTIMATION:
            return self._crew_table_estimation(corps_json)
        if url in (R.URL_CREW_MEMOIRE_ETAT, R.URL_CREW_MEMOIRE_CHERCHER):
            return self._crew_memoire(methode, url, corps_json)
        # /mode : comme le vrai serveur, le mode est gardé dans mode_crew.json.
        if methode == "PUT":
            demande = (corps_json or {}).get("mode")
            if demande not in [m["id"] for m in self.modes_crew]:
                return 400, '{"detail": "mode inconnu"}'
            self.fichiers[R.FICHIER_MODE_CREW] = json.dumps({"mode": demande})
        actuel = json.loads(self.fichiers.get(R.FICHIER_MODE_CREW) or "{}").get("mode", "econome")
        return 200, json.dumps({"mode": actuel, "modes": self.modes_crew}, ensure_ascii=False)

    # ----- serveur Crew : /table-ronde/participants et /table-ronde/estimation (comme le vrai Crew) ----

    def _crew_table_participants(self):
        libelles = {"claude": "Claude", "codex": "ChatGPT / Codex", "gemini": "Gemini", "grok": "Grok", "deepseek": "DeepSeek", "gemma": "gemma (local)"}
        return 200, json.dumps({"participants": [
            {"id": i, "libelle": l, "disponible": i not in self.table_ronde_indispos, "raison": self.table_ronde_indispos.get(i, "")}
            for i, l in libelles.items()]}, ensure_ascii=False)

    def _crew_table_estimation(self, corps):
        """Comme le vrai Crew : `tous` est ignoré, un id inconnu donne 400, un tarif inconnu (None) n'est jamais compté comme 0,
        `total_usd` inclut déjà le 2e tour et `total_incomplet` vaut vrai si un tarif manque."""
        tr = (corps or {}).get("table_ronde") if isinstance(corps, dict) else None
        if not isinstance(tr, dict) or not isinstance(tr.get("participants"), list):
            return 422, '{"error": {"message": "table_ronde.participants manquant", "type": "invalid_request"}}'
        if not tr["participants"]:
            return 400, '{"error": {"message": "aucun participant", "type": "invalid_request"}}'
        inconnus = [i for i in tr["participants"] if i not in self.table_ronde_couts]
        if inconnus:
            return 400, json.dumps({"error": {"message": "participant inconnu : " + ", ".join(map(str, inconnus)), "type": "invalid_request"}})
        participants, total, incomplet = [], 0.0, False
        tours = 2 if tr.get("critique") else 1
        for ident in tr["participants"]:
            cout = self.table_ronde_couts[ident]
            raison = self.table_ronde_indispos.get(ident, "")
            c = None if cout is None else round(cout * tours, 6)
            participants.append({"id": ident, "cout_estime_usd": c, "disponible": not raison, "raison": raison})
            if not raison:
                if c is None:
                    incomplet = True
                else:
                    total += c
        return 200, json.dumps({"participants": participants, "total_usd": round(total, 6), "total_incomplet": incomplet})

    # ----- serveur Crew : /memoire/* (adresses prévues) ---------------------------------

    def _crew_memoire(self, methode, url, corps_json):
        if not self.memoire_disponible:
            return 404, '{"detail": "Not Found"}'
        if url == R.URL_CREW_MEMOIRE_ETAT:
            par_zone = {"prive": 0, "partageable": 0}
            for d in self.memoire_docs:
                par_zone[d["zone"]] = par_zone.get(d["zone"], 0) + 1
            return 200, json.dumps({"fichiers": len(self.memoire_docs), "morceaux": len(self.memoire_docs) * 3,
                                    "par_zone": par_zone, "derniere_indexation": "2026-09-29T03:00:00"})
        if methode != "POST" or not isinstance(corps_json, dict) or not corps_json.get("question"):
            return 422, '{"detail": "question manquante"}'
        mots = {m for m in corps_json["question"].lower().split() if len(m) > 2}
        zones = corps_json.get("zones")
        passages = []
        for d in self.memoire_docs:
            if zones and d["zone"] not in zones:
                continue
            communs = mots & set(d["texte"].lower().split())
            if communs:
                passages.append({"chemin": d["chemin"], "zone": d["zone"], "texte": d["texte"],
                                 "score": round(len(communs) / max(1, len(mots)), 3), "voies": ["mots"]})
        passages.sort(key=lambda p: -p["score"])
        return 200, json.dumps({"passages": passages[:int(corps_json.get("nombre") or 5)]}, ensure_ascii=False)

    # ----- Open WebUI : conversations ------------------------------------------

    def _webui_api(self, url, auth):
        if not (self.docker_pret() and self.conteneurs.get(R.CONTENEUR_WEBUI)):
            return None, "connexion refusée"
        if auth != f"Bearer {self.cle_webui_serveur}":
            return 401, '{"detail": "Not authenticated"}'
        if url == R.URL_WEBUI_CONVERSATIONS:
            resume = [{"id": c["id"], "title": c.get("title", "Sans titre"),
                       "updated_at": c["updated_at"], "created_at": c["updated_at"] - 100}
                      for c in sorted(self.conversations, key=lambda c: -c["updated_at"])[:60]]
            if self.webui_liste_format == "items":
                return 200, json.dumps({"items": resume, "total": len(resume)})
            return 200, json.dumps(resume)
        ident = url.rsplit("/", 1)[-1]
        for c in self.conversations:
            if c["id"] == ident:
                messages = {f"m{n}": {"id": f"m{n}", "role": "assistant", "model": m}
                            for n, m in enumerate(c.get("models_messages", []))}
                return 200, json.dumps({"id": ident, "title": c.get("title", ""),
                                        "chat": {"models": c.get("models", []),
                                                 "history": {"messages": messages}},
                                        "updated_at": c["updated_at"]})
        return 404, '{"detail": "Not found"}'
