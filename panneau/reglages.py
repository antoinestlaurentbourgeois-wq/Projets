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
# Adresses (uniquement localhost / 127.0.0.1 : rien ne sort du PC)
# ---------------------------------------------------------------------------

URL_WEBUI = "http://localhost:3000/api/version"
URL_LMSTUDIO = "http://localhost:1234/v1/models"
URL_LMSTUDIO_MODELES = "http://localhost:1234/api/v0/models"
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
