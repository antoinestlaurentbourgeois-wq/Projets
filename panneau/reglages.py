# -*- coding: utf-8 -*-
"""
Réglages du panneau de contrôle.

C'est le SEUL fichier à modifier si un chemin ou un nom change sur votre PC.
Modifiez-le avec le Bloc-notes, enregistrez, puis relancez le panneau.
"""

import os

# ---------------------------------------------------------------------------
# Docker Desktop
# ---------------------------------------------------------------------------

# Emplacements possibles de Docker Desktop.exe : le premier qui existe est utilisé.
DOCKER_DESKTOP_CANDIDATS = [
    r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
    os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Docker\Docker Desktop.exe"),
]

# Emplacements possibles de la commande « docker », si elle n'est pas dans le PATH.
DOCKER_CLI_CANDIDATS = [
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
]

# Noms des conteneurs Docker.
CONTENEUR_WEBUI = "open-webui"
CONTENEUR_KOKORO = "kokoro"

# ---------------------------------------------------------------------------
# LM Studio
# ---------------------------------------------------------------------------

# Emplacements possibles de l'outil en ligne de commande lms.exe.
LMS_CANDIDATS = [
    r"C:\Users\boliv\.lmstudio\bin\lms.exe",
    os.path.join(os.path.expanduser("~"), ".lmstudio", "bin", "lms.exe"),
]

MODELE_GEMMA = "google/gemma-4-12b-qat"
CONTEXTE_GEMMA = 32000
MODELE_EMBEDDINGS = "text-embedding-nomic-embed-text-v1.5"

# ---------------------------------------------------------------------------
# Serveur Crew
# ---------------------------------------------------------------------------

DOSSIER_CREW = r"I:\Python\crewai-routage"
PYTHONW_CREW = DOSSIER_CREW + r"\.venv\Scripts\pythonw.exe"
SCRIPT_CREW = DOSSIER_CREW + r"\serveur_crew.py"

# ---------------------------------------------------------------------------
# Adresses (uniquement ce PC : rien ne sort du PC).
# 127.0.0.1 et NON localhost pour tout appel fait par un programme : sous Windows,
# « localhost » essaie IPv6 d'abord et perd environ 2 secondes par appel.
# « localhost » reste seulement dans les liens ouverts dans le navigateur.
# ---------------------------------------------------------------------------

URL_WEBUI = "http://127.0.0.1:3000/api/version"
URL_LMSTUDIO = "http://127.0.0.1:1234/v1/models"
URL_LMSTUDIO_MODELES = "http://127.0.0.1:1234/api/v0/models"
URL_CREW_SANTE = "http://127.0.0.1:8765/sante"

# ---------------------------------------------------------------------------
# Clés API (on affiche seulement « présente » / « absente », jamais la valeur)
# ---------------------------------------------------------------------------

CLES_API = ["DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENWEBUI_API_KEY"]

# ---------------------------------------------------------------------------
# Délais (en secondes)
# ---------------------------------------------------------------------------

INTERVALLE_VERIFICATION = 5       # vérification automatique des voyants

DELAI_HTTP = 3                    # une requête vers localhost
DELAI_COMMANDE_COURTE = 15        # docker info, docker inspect, tasklist...
DELAI_POWERSHELL = 20             # PowerShell est lent à démarrer

DELAI_DEMARRAGE_DOCKER = 150      # Docker Desktop peut mettre ~2 minutes
DELAI_ARRET_DOCKER = 120
DELAI_DEMARRAGE_WEBUI = 120       # Open WebUI est lent au premier démarrage
DELAI_DEMARRAGE_KOKORO = 45
DELAI_ARRET_CONTENEUR = 60
DELAI_DEMARRAGE_LMSTUDIO = 90
DELAI_ARRET_LMSTUDIO = 30
DELAI_CHARGEMENT_GEMMA = 300      # 7 Go à charger en mémoire vidéo
DELAI_CHARGEMENT_EMBEDDINGS = 120
DELAI_DECHARGEMENT = 60
DELAI_DEMARRAGE_CREW = 90
DELAI_ARRET_CREW = 20

# ---------------------------------------------------------------------------
# Version 2 : sélecteur de mode Crew, liste des IA, ouverture des applications
# ---------------------------------------------------------------------------

# Serveur Crew : adresses protégées par la clé CREW_API_KEY (lue dans le .env).
URL_CREW_MODE = "http://127.0.0.1:8765/mode"
URL_CREW_MOTEURS = "http://127.0.0.1:8765/moteurs"
# Mémoire de Crew (adresses prévues, pas encore exposées par le serveur : simulées en attendant).
URL_CREW_MEMOIRE_ETAT = "http://127.0.0.1:8765/memoire/etat"
URL_CREW_MEMOIRE_CHERCHER = "http://127.0.0.1:8765/memoire/chercher"
URL_CREW_CHAT = "http://127.0.0.1:8765/v1/chat/completions"
URL_CREW_TABLE_ESTIMATION = "http://127.0.0.1:8765/table-ronde/estimation"     # contrat PROVISOIRE (à confirmer par la session locale)
URL_LMSTUDIO_CHAT = "http://127.0.0.1:1234/v1/chat/completions"
FICHIER_ENV_CREW = DOSSIER_CREW + r"\.env"
NOM_CLE_CREW = "CREW_API_KEY"
# Fichier du mode, utilisé seulement quand le serveur Crew est éteint.
FICHIER_MODE_CREW = DOSSIER_CREW + r"\mode_crew.json"
# Copie locale des libellés/explications reçus du serveur (pour les afficher
# même quand le serveur est éteint). Rangée dans le dossier du panneau.
FICHIER_CACHE_MODES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modes_crew_cache.json")

# Open WebUI
URL_WEBUI_BASE = "http://127.0.0.1:3000"            # appels du programme
URL_WEBUI_NAVIGATEUR = "http://localhost:3000"       # liens ouverts dans le navigateur
URL_WEBUI_CONVERSATIONS = URL_WEBUI_BASE + "/api/v1/chats/?page=1"
URL_WEBUI_CONVERSATION = URL_WEBUI_BASE + "/api/v1/chats/{id}"
URL_WEBUI_CONVERSATION_OUVRIR = URL_WEBUI_NAVIGATEUR + "/c/{id}"
URL_WEBUI_NOUVELLE_CREW = URL_WEBUI_NAVIGATEUR + "/?model=crew-normal"
NOM_CLE_WEBUI = "OPENWEBUI_API_KEY"
PREFIXE_MODELE_CREW = "crew-"
CONVERSATIONS_EXAMINEES = 20      # on regarde au plus les 20 plus récentes
DELAI_RECHERCHE_CONVERSATION = 10 # secondes au total, ensuite : nouvelle conversation

# LM Studio (l'application)
LMSTUDIO_EXE_CANDIDATS = [
    r"C:\Users\boliv\AppData\Local\Programs\LM Studio\LM Studio.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\LM Studio\LM Studio.exe"),
]
