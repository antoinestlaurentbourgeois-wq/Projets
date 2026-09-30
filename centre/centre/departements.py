# -*- coding: utf-8 -*-
"""
Départements et démarrages rapides : des « raccourcis de travail ».

Chaque fichier JSON décrit un département : {"id", "nom", "description", "salle" (par défaut), "demarrages": [{"titre", "prompt", "salle"?, "memoire"?}]}.
Les fichiers fournis sont dans `centre/departements/`. Pour ajouter ou modifier : créez un fichier du même format dans
`I:\\IA\\CENTRE\\donnees\\departements\\` (un fichier avec le même « id » remplace celui fourni). Un fichier invalide est ignoré (et signalé).
"""

import json
import os
import re

ID_OK = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
MAX_PROMPT = 4000


def _valider(d):
    if not isinstance(d, dict) or not ID_OK.match(str(d.get("id", ""))):
        raise ValueError("« id » manquant ou invalide (minuscules, chiffres, - et _)")
    from .salles import SALLES
    nom = str(d.get("nom", "")).strip()
    if not nom:
        raise ValueError("« nom » manquant")
    salle = d.get("salle", "crew")
    if salle not in SALLES:
        raise ValueError(f"salle inconnue « {salle} »")
    demarrages = []
    for i, x in enumerate(d.get("demarrages") or []):
        if not isinstance(x, dict) or not str(x.get("titre", "")).strip() or not str(x.get("prompt", "")).strip():
            raise ValueError(f"démarrage n°{i + 1} : « titre » et « prompt » requis")
        s = x.get("salle", salle)
        if s not in SALLES:
            raise ValueError(f"démarrage n°{i + 1} : salle inconnue « {s} »")
        demarrages.append({"titre": str(x["titre"]).strip()[:80], "prompt": str(x["prompt"])[:MAX_PROMPT], "salle": s,
                           "memoire": bool(x.get("memoire"))})
    return {"id": d["id"], "nom": nom[:60], "description": str(d.get("description", ""))[:300], "salle": salle,
            "demarrages": demarrages}


def charger(config):
    """(départements, problèmes). Les fichiers de l'utilisateur remplacent ceux fournis (même id)."""
    dossiers = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "departements"), config.chemin("departements")]
    par_id, problemes = {}, []
    for dossier in dossiers:
        try:
            noms = sorted(n for n in os.listdir(dossier) if n.lower().endswith(".json"))
        except OSError:
            continue
        for n in noms:
            try:
                with open(os.path.join(dossier, n), encoding="utf-8-sig") as f:
                    d = _valider(json.load(f))
                par_id[d["id"]] = d
            except (OSError, ValueError, TypeError) as e:
                problemes.append(f"{n} : {e}")
    return sorted(par_id.values(), key=lambda d: d["nom"].lower()), problemes
