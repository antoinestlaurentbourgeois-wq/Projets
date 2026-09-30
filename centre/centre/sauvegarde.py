# -*- coding: utf-8 -*-
"""
Sauvegarde de nuit : une archive ZIP de `donnees/` SANS AUCUN SECRET, dans `sauvegardes/` (les 7 dernières sont gardées).

Sont exclus, quoi qu'il arrive : `verrou.json` (empreintes du NIP et du mot secret), les journaux volumineux, les fichiers
temporaires et le dossier des sauvegardes lui-même. De plus, tout fichier texte qui contient quelque chose qui ressemble à
une clé (« sk-… », « Bearer … », « api_key=… ») est écarté et signalé dans le manifeste : la sauvegarde ne peut pas emporter une clé.
Les conversations et le tiroir sont inclus (ils restent sur VOTRE disque I:).
"""

import json
import os
import re
import time
import zipfile

from .journal import masquer

GARDER = 7
EXCLUS_NOMS = {"verrou.json", "verrou.json.tmp", "gardien.lock"}
EXCLUS_DOSSIERS = {"sauvegardes", "atelier", "__pycache__"}
MAX_TEXTE_SCAN = 8_000_000
EXT_TEXTE = (".json", ".jsonl", ".txt", ".log", ".md", ".csv")
NOM_SAUVEGARDE = re.compile(r"^centre-\d{8}-\d{6}\.zip$")


def contient_secret(texte):
    """Vrai si le texte ressemble à contenir une clé ou un secret."""
    return masquer(texte) != texte


def dossier_sauvegardes(config):
    return os.path.join(os.path.dirname(os.path.abspath(config.dossier_donnees)), "sauvegardes")


def lister(config):
    d = dossier_sauvegardes(config)
    try:
        noms = sorted(n for n in os.listdir(d) if NOM_SAUVEGARDE.match(n))
    except OSError:
        return []
    sortie = []
    for n in reversed(noms):
        chemin = os.path.join(d, n)
        sortie.append({"nom": n, "taille": os.path.getsize(chemin), "date": os.path.getmtime(chemin)})
    return sortie


def sauvegarder(config, maintenant=None):
    """Crée l'archive, la vérifie, fait tourner les anciennes. Renvoie un dictionnaire de résultat."""
    source = os.path.abspath(config.dossier_donnees)
    if not os.path.isdir(source):
        return {"ok": False, "message": "Dossier des données introuvable."}
    dest = dossier_sauvegardes(config)
    os.makedirs(dest, exist_ok=True)
    t = maintenant if maintenant is not None else time.time()
    nom = "centre-" + time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + ".zip"
    chemin = os.path.join(dest, nom)
    temporaire = chemin + ".tmp"
    ecartes, inclus = [], 0
    with zipfile.ZipFile(temporaire, "w", zipfile.ZIP_DEFLATED) as z:
        for racine, dossiers, fichiers in os.walk(source):
            dossiers[:] = [d for d in dossiers if d not in EXCLUS_DOSSIERS]
            for f in fichiers:
                complet = os.path.join(racine, f)
                rel = os.path.relpath(complet, source).replace("\\", "/")
                if f in EXCLUS_NOMS or f.endswith(".tmp") or os.path.islink(complet):
                    ecartes.append({"fichier": rel, "raison": "exclu (secret ou temporaire)"})
                    continue
                if f.lower().endswith(EXT_TEXTE):
                    try:
                        if os.path.getsize(complet) <= MAX_TEXTE_SCAN:
                            with open(complet, encoding="utf-8", errors="replace") as h:
                                if contient_secret(h.read()):
                                    ecartes.append({"fichier": rel, "raison": "contient ce qui ressemble à une clé"})
                                    continue
                        else:
                            ecartes.append({"fichier": rel, "raison": "trop gros pour être vérifié"})
                            continue
                    except OSError:
                        ecartes.append({"fichier": rel, "raison": "illisible"})
                        continue
                z.write(complet, rel)
                inclus += 1
        manifeste = {"cree": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)), "fichiers": inclus, "ecartes": ecartes,
                     "note": "Aucun secret : verrou.json (empreintes) et tout fichier ressemblant à une clé sont exclus."}
        z.writestr("MANIFESTE.json", json.dumps(manifeste, ensure_ascii=False, indent=1))
    with zipfile.ZipFile(temporaire) as z:
        mauvais = z.testzip()
    if mauvais:
        os.remove(temporaire)
        return {"ok": False, "message": f"Archive corrompue ({mauvais}) : supprimée."}
    os.replace(temporaire, chemin)
    supprimees = []
    for ancienne in lister(config)[GARDER:]:
        try:
            os.remove(os.path.join(dest, ancienne["nom"]))
            supprimees.append(ancienne["nom"])
        except OSError:
            pass
    return {"ok": True, "nom": nom, "taille": os.path.getsize(chemin), "fichiers": inclus, "ecartes": ecartes,
            "supprimees": supprimees, "message": f"Sauvegarde {nom} : {inclus} fichiers."}


def restaurer(config, nom, dossier_cible):
    """Extrait une sauvegarde dans un dossier NEUF (jamais par-dessus les données actuelles). Renvoie le dossier."""
    if not NOM_SAUVEGARDE.match(nom or ""):
        raise ValueError("Nom de sauvegarde invalide.")
    archive = os.path.join(dossier_sauvegardes(config), nom)
    if not os.path.isfile(archive):
        raise ValueError("Sauvegarde introuvable.")
    cible = os.path.abspath(dossier_cible)
    if os.path.exists(cible) and os.listdir(cible):
        raise ValueError("Le dossier de restauration doit être vide ou nouveau : rien n'est écrasé.")
    os.makedirs(cible, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            destination = os.path.abspath(os.path.join(cible, info.filename))
            if not destination.startswith(cible + os.sep):          # protection contre les chemins piégés (« ../ »)
                raise ValueError("Archive suspecte : chemin hors du dossier.")
        z.extractall(cible)
    return cible
