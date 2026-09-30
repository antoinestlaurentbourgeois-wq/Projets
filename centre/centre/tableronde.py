# -*- coding: utf-8 -*-
"""
Table ronde : UNE question posée à plusieurs IA dans la même conversation, TOUJOURS par Crew.

Le Centre ne crée aucun mécanisme parallèle : il envoie la liste cochée à Crew (`model: crew-tableronde`, champ `table_ronde`), et Crew
applique ses paliers de confidentialité, compte les coûts réels et gère le plan B. Le Centre :
  - affiche l'estimation de coût AVANT l'envoi (elle vient de Crew : POST /table-ronde/estimation ; GET /table-ronde/participants dit qui est disponible) ;
  - refuse d'appeler quoi que ce soit si l'estimation dépasse le seuil (`seuil_table_ronde_usd`, réglages.json) sans confirmation ;
  - affiche les réponses de chaque IA, leur coût réel et leur durée, ou la raison d'une exclusion décidée par Crew.

Contrat avec Crew : celui du vrai Crew (voir RETOUR-table-ronde-suite.md).
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

    def libelle(self, ident):
        """« gemma » du contrat désigne le CHEF ACTUEL : affiché « Chef local (<modèle>) » (l'identifiant du contrat ne change pas)."""
        if ident == "gemma":
            return f"Chef local ({self.centre.nom_chef()})"
        return LIBELLE.get(ident, ident)

    def options(self):
        c = self.centre
        c.assurer_etats()
        crew_actif = c.etats["crew"].code == c.L.ACTIF
        return {"crew_actif": crew_actif,
                "raison": "" if crew_actif else "Crew est arrêté (ou en Mode jeu) : la table ronde est indisponible. Les salles individuelles fonctionnent toujours.",
                "seuil_usd": c.config.seuil_table_ronde_usd, "defaut": list(DEFAUT),
                "participants": [{"id": i, "libelle": self.libelle(i), "defaut": i in DEFAUT} for i, l, _ in PARTICIPANTS]}

    def corps(self, messages, participants, critique, synthese, stream=False):
        return {"model": MODELE, "messages": messages, "stream": stream,
                "table_ronde": {"participants": list(participants), "critique": bool(critique), "synthese": bool(synthese), "format": "brut"}}

    # ----- disponibilité des IA (Crew : GET /table-ronde/participants) ---------------------------------------------

    def _cle_crew(self):
        c = self.centre
        R = c.L.R
        return c.C.analyser_env(c.sys.lire_fichier(R.FICHIER_ENV_CREW), R.NOM_CLE_CREW)

    @staticmethod
    def _message_crew(statut, texte, defaut):
        try:
            m = json.loads(texte)
            m = (m.get("error") or {}).get("message") if isinstance(m.get("error"), dict) else m.get("detail")
            if isinstance(m, str) and m:
                return f"{defaut} ({m[:200]})"
        except (ValueError, AttributeError, TypeError):
            pass
        return defaut

    def disponibilites(self):
        """(dict id -> {disponible, raison}, message d'erreur). Ne compte jamais une IA qu'on ne connaît pas."""
        c = self.centre
        R = c.L.R
        cle = self._cle_crew()
        if not cle:
            return None, f"Clé {R.NOM_CLE_CREW} introuvable."
        try:
            statut, texte = c.sys.http("GET", R.URL_CREW_TABLE_PARTICIPANTS, 15, {"Authorization": "Bearer " + cle})
        finally:
            del cle
        if statut is None:
            return None, "Crew ne répond pas."
        if statut in (401, 403):
            return None, "Clé Crew refusée."
        if statut != 200:
            return None, f"La liste des IA de Crew a répondu {statut}."
        try:
            d = json.loads(texte)
            lignes = d["participants"] if isinstance(d, dict) else d
            if not isinstance(lignes, list):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return None, "Liste des IA de Crew illisible."
        sortie = {}
        for x in lignes:
            if isinstance(x, dict) and x.get("id") in IDS:
                sortie[x["id"]] = {"disponible": x.get("disponible") is not False, "raison": str(x.get("raison") or "")[:300]}
        return sortie, ""

    # ----- estimation (Crew) --------------------------------------------------------------------------------------

    def estimer(self, messages, participants, critique=False, synthese=True):
        """Renvoie {ok, participants:[{id,libelle,disponible,raison,cout_estime_usd}], total_usd, total_incomplet, seuil_usd, depasse, message}.
        `participants` contient les six IA (grisage) ; le coût n'est demandé à Crew que pour les IA cochées ET disponibles, et
        `total_usd` est celui de Crew tel quel (2e tour inclus). Un coût inconnu reste None (jamais 0) et met `total_incomplet` à vrai."""
        c = self.centre
        seuil = c.config.seuil_table_ronde_usd
        base = {"ok": False, "participants": [], "total_usd": 0.0, "total_incomplet": False, "seuil_usd": seuil, "depasse": False, "message": ""}
        if c.etats["crew"].code != c.L.ACTIF:
            base["message"] = self.options()["raison"]
            return base
        dispo, erreur = self.disponibilites()
        if dispo is None:
            base["message"] = erreur
            return base
        sortie = {i: {"id": i, "libelle": self.libelle(i), "cout_estime_usd": None,
                      "disponible": dispo.get(i, {}).get("disponible", False),
                      "raison": dispo.get(i, {}).get("raison") or ("" if i in dispo else "Crew ne connaît pas cette IA")}
                  for i in IDS}
        a_estimer = [i for i in participants if sortie[i]["disponible"]]
        total, incomplet = 0.0, False
        if a_estimer:
            R = c.L.R
            cle = self._cle_crew()
            if not cle:
                base["message"] = f"Clé {R.NOM_CLE_CREW} introuvable."
                return base
            try:
                statut, texte = c.sys.http("POST", R.URL_CREW_TABLE_ESTIMATION, 30, {"Authorization": "Bearer " + cle},
                                           self.corps(messages, a_estimer, critique, synthese))
            finally:
                del cle
            if statut is None:
                base["message"] = "Crew ne répond pas."
                return base
            if statut in (401, 403):
                base["message"] = "Clé Crew refusée."
                return base
            if statut != 200:
                base["message"] = self._message_crew(statut, texte, f"L'estimation de Crew a répondu {statut}.")
                return base
            try:
                d = json.loads(texte)
                lignes = d["participants"]
                if not isinstance(lignes, list):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                base["message"] = "Réponse d'estimation de Crew illisible."
                return base
            for x in lignes:
                if not isinstance(x, dict) or x.get("id") not in sortie:
                    continue
                cout = x.get("cout_estime_usd")
                if isinstance(cout, (int, float)) and not isinstance(cout, bool) and cout >= 0:
                    sortie[x["id"]]["cout_estime_usd"] = round(float(cout), 6)
                if x.get("disponible") is False:
                    sortie[x["id"]].update(disponible=False, raison=str(x.get("raison") or "")[:300])
            annonce = d.get("total_usd")
            if isinstance(annonce, (int, float)) and not isinstance(annonce, bool) and annonce >= 0:
                total = round(float(annonce), 6)
                incomplet = d.get("total_incomplet") is True
            else:                                                  # total absent : somme des coûts connus, marquée incomplète
                total = round(sum(sortie[i]["cout_estime_usd"] or 0.0 for i in a_estimer), 6)
                incomplet = True
            if any(sortie[i]["cout_estime_usd"] is None and sortie[i]["disponible"] for i in a_estimer):
                incomplet = True
        base.update(ok=True, participants=[sortie[i] for i in IDS], total_usd=total, total_incomplet=incomplet, depasse=total > seuil)
        if base["depasse"]:
            base["message"] = f"Coût estimé {'au moins ' if incomplet else ''}{total:.3f} $ : au-dessus du seuil de {seuil:.2f} $ par message."
        return base
