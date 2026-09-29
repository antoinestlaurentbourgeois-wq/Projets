# -*- coding: utf-8 -*-
"""
Gardien : vérifications toutes les 10 minutes (Planificateur de tâches Windows -> `scripts\\gardien.ps1`).

`scripts\\gardien.ps1` s'assure que le serveur répond (et le relance sinon) puis lance `python -m centre gardien`, qui fait les
vérifications plus fines ci-dessous et écrit `gardien.json`. La page Journal affiche le dernier rapport, et alerte si le gardien se tait.
"""

import json
import os
import shutil
import time
import urllib.error
import urllib.request

from .sauvegarde import lister as lister_sauvegardes

ESPACE_MIN_GO = 5.0
AGE_MAX_SAUVEGARDE_H = 36
SILENCE_GARDIEN_S = 30 * 60


def _repond(url, delai=4):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=delai) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def verifier(config, maintenant=None, repond=_repond, espace_libre=None, cles_presentes=None, tailscale_funnel=None):
    """Renvoie {ts, ok, alertes:[...], details:{...}}. Toutes les dépendances externes sont injectables (tests)."""
    t = maintenant if maintenant is not None else time.time()
    alertes, details = [], {}

    ok_serveur = repond(f"http://127.0.0.1:{config.port}/api/verrou")
    details["serveur"] = ok_serveur
    if not ok_serveur:
        alertes.append("Le serveur du Centre ne répond pas.")

    try:
        libre = espace_libre() if espace_libre else shutil.disk_usage(config.dossier_donnees).free / 1e9
    except OSError:
        libre = None
    details["espace_libre_go"] = None if libre is None else round(libre, 1)
    if libre is not None and libre < ESPACE_MIN_GO:
        alertes.append(f"Il reste seulement {libre:.1f} Go sur le disque des données (minimum conseillé : {ESPACE_MIN_GO:g} Go).")

    verrou = os.path.join(config.dossier_donnees, "verrou.json")
    details["verrou_defini"] = os.path.isfile(verrou)
    if not details["verrou_defini"]:
        alertes.append("Le verrou (NIP et mot secret) n'est pas défini.")

    sauvegardes = lister_sauvegardes(config)
    details["derniere_sauvegarde"] = sauvegardes[0]["nom"] if sauvegardes else None
    if not sauvegardes:
        alertes.append("Aucune sauvegarde n'existe encore.")
    elif t - sauvegardes[0]["date"] > AGE_MAX_SAUVEGARDE_H * 3600:
        alertes.append(f"La dernière sauvegarde date de plus de {AGE_MAX_SAUVEGARDE_H} h.")

    if cles_presentes is not None:
        manquantes = [n for n, ok in cles_presentes.items() if not ok]
        details["cles_absentes"] = manquantes
        if manquantes:
            alertes.append("Clés absentes (les salles correspondantes seront grisées) : " + ", ".join(manquantes))

    if tailscale_funnel:
        alertes.append("DANGER : un « funnel » Tailscale est actif : le Centre pourrait être exposé sur Internet. Coupez-le : tailscale funnel reset")
    details["funnel"] = bool(tailscale_funnel)

    rapport = {"ts": t, "ok": not [a for a in alertes if a.startswith(("Le serveur", "DANGER", "Le verrou"))], "alertes": alertes, "details": details}
    return rapport


def ecrire(config, rapport):
    chemin = os.path.join(config.dossier_donnees, "gardien.json")
    os.makedirs(config.dossier_donnees, exist_ok=True)
    temporaire = chemin + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False)
    os.replace(temporaire, chemin)


def lire(config, maintenant=None):
    """Dernier rapport, complété d'une alerte si le gardien est resté silencieux trop longtemps."""
    t = maintenant if maintenant is not None else time.time()
    try:
        with open(os.path.join(config.dossier_donnees, "gardien.json"), encoding="utf-8") as f:
            r = json.load(f)
    except (OSError, ValueError):
        return {"ts": None, "ok": None, "alertes": ["Le gardien n'a encore jamais tourné (voir scripts\\installer_taches.bat)."],
                "details": {}, "silencieux": True}
    r["silencieux"] = t - float(r.get("ts") or 0) > SILENCE_GARDIEN_S
    if r["silencieux"]:
        r["alertes"] = list(r.get("alertes", [])) + ["Le gardien ne s'est pas exécuté depuis plus de 30 minutes."]
    return r
