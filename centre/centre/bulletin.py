# -*- coding: utf-8 -*-
"""
Bulletin du matin : un texte composé À PARTIR DES DONNÉES LOCALES (pas d'IA, donc gratuit, sans nuage, déterministe).
Deux versions :
  - `texte` : pour l'écran, complet ;
  - `texte_voix` : pour la lecture par une voix du nuage. Le texte des rappels PRIVÉS n'y figure pas (« vous avez 2 rappels privés »).
"""

import time

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def date_fr(t):
    d = time.localtime(t)
    jour = "1er" if d.tm_mday == 1 else str(d.tm_mday)
    return f"{JOURS[d.tm_wday]} {jour} {MOIS[d.tm_mon - 1]} {d.tm_year}"


def heure_fr(t):
    d = time.localtime(t)
    return f"{d.tm_hour} h {d.tm_min:02d}"


def composer(centre, maintenant=None):
    t = maintenant if maintenant is not None else time.time()
    L = centre.L
    ecran, voix = [], []          # listes de sections : (titre, [lignes])

    def section(titre, lignes, lignes_voix=None):
        if lignes:
            ecran.append((titre, lignes))
            voix.append((titre, lignes if lignes_voix is None else lignes_voix))

    h = time.localtime(t).tm_hour
    salut = "Bonjour" if h < 18 else "Bonsoir"
    intro = f"{salut} ! Nous sommes le {date_fr(t)}."
    ecran.append(("", [intro]))
    voix.append(("", [intro]))

    # Services
    etats = centre.etats
    actifs = [L.nom(i) for i, e in etats.items() if e.code == L.ACTIF]
    arretes = [L.nom(i) for i, e in etats.items() if e.code != L.ACTIF]
    lignes = []
    if actifs:
        lignes.append("Allumés : " + ", ".join(actifs) + ".")
    if arretes:
        lignes.append("Éteints ou indisponibles : " + ", ".join(arretes) + ".")
    mode, libelle = centre.salles.politique.mode()
    lignes.append(f"Mode de Crew : {libelle}." if mode else "Le mode de Crew est inconnu.")
    section("Votre PC", lignes)

    # Rappels
    rappels = centre.rappels.du_jour()
    if rappels:
        l_ecran = []
        for r in rappels:
            quand = "en retard" if r["echeance"] < t - 60 else "à " + heure_fr(r["echeance"])
            l_ecran.append(f"{r['texte']} ({quand}{', privé' if r['zone'] == 'prive' else ''})")
        publics = [r for r in rappels if r["zone"] == "partageable"]
        prives = len(rappels) - len(publics)
        l_voix = [f"{r['texte']}, {'en retard' if r['echeance'] < t - 60 else 'à ' + heure_fr(r['echeance'])}" for r in publics]
        if prives:
            l_voix.append(f"Et {prives} rappel{'s' if prives > 1 else ''} privé{'s' if prives > 1 else ''}, à voir à l'écran.")
        section(f"Rappels ({len(rappels)})", l_ecran, l_voix)
    else:
        section("Rappels", ["Aucun rappel pour aujourd'hui."])

    # Coûts
    st = centre.couts.statut()
    hier = time.strftime("%Y-%m-%d", time.localtime(t - 86400))
    depense_hier = 0.0
    try:
        import json as _j
        with open(centre.config.chemin("depenses.jsonl"), encoding="utf-8") as f:
            for l in f:
                try:
                    d = _j.loads(l)
                    if str(d["ts"])[:10] == hier:
                        depense_hier += float(d["usd"])
                except (ValueError, KeyError, TypeError):
                    continue
    except OSError:
        pass
    lignes = [f"Dépenses estimées : hier {depense_hier:.2f} $, aujourd'hui {st['totaux']['aujourdhui']['total']:.2f} $, ce mois-ci {st['totaux']['mois']['total']:.2f} $."]
    for cle, nom in (("jour", "du jour"), ("mois", "du mois")):
        p = st["plafonds"][cle]
        if p["plafond"] is not None:
            lignes.append(f"Plafond {nom} : {p['depense']:.2f} $ sur {p['plafond']:.2f} $" + (" — ATTEINT." if p["atteint"] else "."))
    section("Coûts", lignes)

    # Approbations en attente
    try:
        en_attente = [c for c in centre.salles.conversations.lister(limite=500)
                      if centre.salles.conversation(c["id"]).get("en_attente")]
    except Exception:
        en_attente = []
    if en_attente:
        section("À valider", [f"{len(en_attente)} conversation{'s' if len(en_attente) > 1 else ''} avec une action de Claude en attente d'approbation (page Salles)."])

    # Gardien
    from . import gardien
    g = gardien.lire(centre.config, t)
    if g.get("alertes"):
        section("Attention", list(g["alertes"]))

    def assembler(sections):
        morceaux = []
        for titre, lignes in sections:
            morceaux.append((titre + " : " if titre else "") + " ".join(lignes))
        return "\n".join(morceaux)

    return {"date": date_fr(t), "sections": [{"titre": t_, "lignes": l} for t_, l in ecran],
            "texte": assembler(ecran), "texte_voix": assembler(voix)}
