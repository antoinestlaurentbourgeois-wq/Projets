# -*- coding: utf-8 -*-
"""
Table ronde : UNE question posée à plusieurs IA dans la même conversation, TOUJOURS par Crew.

Le Centre ne crée aucun mécanisme parallèle : il envoie la liste cochée à Crew (`model: crew-tableronde`, champ `table_ronde`), et Crew
applique ses paliers de confidentialité, compte les coûts réels et gère le plan B. Le Centre :
  - affiche l'estimation de coût AVANT l'envoi (elle vient de Crew : POST /table-ronde/estimation) ;
  - refuse d'appeler quoi que ce soit si l'estimation dépasse le seuil (`seuil_table_ronde_usd`, réglages.json) sans confirmation ;
  - affiche les réponses de chaque IA, leur coût réel et leur durée, ou la raison d'une exclusion décidée par Crew.

Contrat avec Crew : PROVISOIRE (voir RETOUR-table-ronde-inconnus.md).
"""

import json

PARTICIPANTS = [            # (id du contrat Crew, libellé, salle correspondante du Centre)
    ("claude", "Claude", "claude"),
    ("codex", "ChatGPT / Codex", "chatgpt"),
    ("gemini", "Gemini", "gemini"),
    ("grok", "Grok", "grok"),
    ("deepseek", "DeepSeek", "deepseek"),
    ("gemma", "gemma (local)", "gemma"),
]
IDS = tuple(p[0] for p in PARTICIPANTS)
DEFAUT = ("gemini", "deepseek", "gemma")        # Claude, Codex et Grok : décochés (abonnements limités / clé pas encore créée)
LIBELLE = {p[0]: p[1] for p in PARTICIPANTS}
LIBELLE["synthese"] = "Synthèse de Crew"
IA_DES_COUTS = {p[0]: p[2] for p in PARTICIPANTS}     # pour ranger les dépenses sous la bonne IA
MODELE = "crew-tableronde"


class ErreurTableRonde(Exception):
    def __init__(self, message, code=400, **extra):
        super().__init__(message)
        self.code, self.extra = code, extra


def nettoyer(participants):
    """Liste sans doublon, dans l'ordre du contrat, limitée aux IA connues. Lève ErreurTableRonde si vide."""
    if not isinstance(participants, (list, tuple)):
        raise ErreurTableRonde("Choisissez au moins une IA pour la table ronde.")
    voulus = {str(p) for p in participants}
    propres = [i for i in IDS if i in voulus]
    if not propres:
        raise ErreurTableRonde("Choisissez au moins une IA pour la table ronde.")
    return propres


class TableRonde:
    def __init__(self, centre):
        self.centre = centre

    # ----- ce que l'écran affiche avant tout choix ---------------------------------------------------------------

    def options(self):
        c = self.centre
        c.assurer_etats()
        crew_actif = c.etats["crew"].code == c.L.ACTIF
        return {"crew_actif": crew_actif,
                "raison": "" if crew_actif else "Crew est arrêté (ou en Mode jeu) : la table ronde est indisponible. Les salles individuelles fonctionnent toujours.",
                "seuil_usd": c.config.seuil_table_ronde_usd, "defaut": list(DEFAUT),
                "participants": [{"id": i, "libelle": l, "defaut": i in DEFAUT} for i, l, _ in PARTICIPANTS]}

    def corps(self, messages, participants, critique, synthese, stream=False):
        return {"model": MODELE, "messages": messages, "stream": stream,
                "table_ronde": {"participants": list(participants), "critique": bool(critique), "synthese": bool(synthese)}}

    # ----- estimation (Crew) --------------------------------------------------------------------------------------

    def estimer(self, messages, participants, critique=False, synthese=True, selection=None):
        """Renvoie {ok, participants:[{id,libelle,cout_estime_usd,disponible,raison}], total_usd, seuil_usd, depasse, message}.
        `total_usd` ne compte que les IA disponibles (et, si `selection` est donnée, seulement celles-là : l'écran interroge Crew sur TOUTES les IA
        pour griser celles qui sont indisponibles, mais n'additionne que les cochées). Si Crew ne répond pas ou n'expose pas la table ronde : ok=False + message."""
        c = self.centre
        seuil = c.config.seuil_table_ronde_usd
        base = {"ok": False, "participants": [], "total_usd": 0.0, "seuil_usd": seuil, "depasse": False, "message": ""}
        if c.etats["crew"].code != c.L.ACTIF:
            base["message"] = self.options()["raison"]
            return base
        R = c.L.R
        cle = c.C.analyser_env(c.sys.lire_fichier(R.FICHIER_ENV_CREW), R.NOM_CLE_CREW)
        if not cle:
            base["message"] = f"Clé {R.NOM_CLE_CREW} introuvable."
            return base
        try:
            statut, texte = c.sys.http("POST", R.URL_CREW_TABLE_ESTIMATION, 30, {"Authorization": "Bearer " + cle},
                                       self.corps(messages, participants, critique, synthese))
        finally:
            del cle
        if statut is None:
            base["message"] = "Crew ne répond pas."
            return base
        if statut in (401, 403):
            base["message"] = "Clé Crew refusée."
            return base
        if statut == 404:
            base["message"] = "Crew n'expose pas encore la table ronde (adresse /table-ronde/estimation introuvable)."
            return base
        if statut != 200:
            base["message"] = f"L'estimation de Crew a répondu {statut}."
            return base
        try:
            d = json.loads(texte)
            lignes = d["participants"]
            if not isinstance(lignes, list):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            base["message"] = "Réponse d'estimation de Crew illisible."
            return base
        sortie = []
        for x in lignes:
            if not isinstance(x, dict) or x.get("id") not in IDS:
                continue
            cout = x.get("cout_estime_usd")
            cout = float(cout) if isinstance(cout, (int, float)) and not isinstance(cout, bool) and cout >= 0 else 0.0
            sortie.append({"id": x["id"], "libelle": LIBELLE[x["id"]], "cout_estime_usd": round(cout, 6),
                           "disponible": x.get("disponible") is not False, "raison": str(x.get("raison") or "")[:300]})
        # le total est recalculé ici (les IA grisées ne comptent pas) ; celui de Crew sert de repère s'il est plus grand
        retenus = [p for p in sortie if p["disponible"] and (selection is None or p["id"] in selection)]
        total = round(sum(p["cout_estime_usd"] for p in retenus), 6)
        annonce = d.get("total_usd")
        if selection is None and isinstance(annonce, (int, float)) and not isinstance(annonce, bool) and annonce > total:
            total = round(float(annonce), 6)
        base.update(ok=True, participants=sortie, total_usd=total, depasse=total > seuil)
        if base["depasse"]:
            base["message"] = f"Coût estimé {total:.3f} $ : au-dessus du seuil de {seuil:.2f} $ par message."
        return base
