# -*- coding: utf-8 -*-
"""Rapport d'usage : dépenses par jour et par IA, messages par salle, minutes de voix. Lecture seule des fichiers locaux."""

import csv
import io
import json
import os
import time


def _jour(ts):
    return ts[:10]


def construire(config, jours=30, maintenant=None):
    t = maintenant if maintenant is not None else time.time()
    jours = max(1, min(int(jours), 366))
    limite = time.strftime("%Y-%m-%d", time.localtime(t - (jours - 1) * 86400))
    depenses, par_ia, par_jour = [], {}, {}
    try:
        with open(config.chemin("depenses.jsonl"), encoding="utf-8") as f:
            for l in f:
                try:
                    d = json.loads(l)
                    ts, usd = d["ts"], float(d["usd"])
                except (ValueError, KeyError, TypeError):
                    continue
                if _jour(ts) < limite:
                    continue
                ia = str(d.get("ia", "?"))
                par_ia[ia] = par_ia.get(ia, 0.0) + usd
                jour = par_jour.setdefault(_jour(ts), {})
                jour[ia] = jour.get(ia, 0.0) + usd
    except OSError:
        pass
    messages = {}
    dossier = config.chemin("conversations")
    try:
        noms = os.listdir(dossier)
    except OSError:
        noms = []
    nb_conv = 0
    for nom in noms:
        if not nom.endswith(".json"):
            continue
        try:
            with open(os.path.join(dossier, nom), encoding="utf-8") as f:
                c = json.load(f)
        except (OSError, ValueError):
            continue
        actif = False
        for m in c.get("messages", []):
            if m.get("role") == "assistant" and not m.get("erreur") and time.strftime("%Y-%m-%d", time.localtime(m.get("ts", 0))) >= limite:
                messages[c.get("salle", "?")] = messages.get(c.get("salle", "?"), 0) + 1
                actif = True
        nb_conv += 1 if actif else 0
    minutes_voix, sessions_voix = 0.0, 0
    try:
        with open(config.chemin("recus.jsonl"), encoding="utf-8") as f:
            for l in f:
                try:
                    r = json.loads(l)
                except ValueError:
                    continue
                if r.get("action") == "voix_live" and _jour(str(r.get("ts", ""))) >= limite:
                    sessions_voix += 1
                    minutes_voix += float((r.get("details") or {}).get("minutes") or 0)
    except OSError:
        pass
    total = sum(par_ia.values())
    lignes = [{"jour": j, "ia": ia, "usd": round(v, 4)} for j in sorted(par_jour) for ia, v in sorted(par_jour[j].items())]
    return {"jours": jours, "depuis": limite, "total_usd": round(total, 4), "moyenne_par_jour_usd": round(total / jours, 4),
            "par_ia": {k: round(v, 4) for k, v in sorted(par_ia.items(), key=lambda x: -x[1])},
            "par_jour": {j: round(sum(v.values()), 4) for j, v in sorted(par_jour.items())}, "lignes": lignes,
            "messages_par_salle": dict(sorted(messages.items(), key=lambda x: -x[1])), "conversations_actives": nb_conv,
            "voix": {"sessions": sessions_voix, "minutes": round(minutes_voix, 1)}}


def en_csv(rapport):
    """CSV (séparateur « ; », ouvrable dans Excel en français). Aucune formule : les valeurs commençant par = + - @ sont neutralisées."""
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";", lineterminator="\r\n")

    def sur(v):
        v = str(v)
        return "'" + v if v[:1] in ("=", "+", "-", "@") else v
    w.writerow(["jour", "ia", "depense_usd"])
    for l in rapport["lignes"]:
        w.writerow([sur(l["jour"]), sur(l["ia"]), str(l["usd"]).replace(".", ",")])
    w.writerow([])
    w.writerow(["salle", "messages_ia"])
    for k, v in rapport["messages_par_salle"].items():
        w.writerow([sur(k), v])
    return "﻿" + sortie.getvalue()
