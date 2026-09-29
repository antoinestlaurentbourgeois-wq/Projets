# -*- coding: utf-8 -*-
"""
Mémoire de Crew (bibliothèque de documents) : GET /memoire/etat et POST /memoire/chercher.

Ces adresses ne sont pas encore exposées par le vrai serveur Crew : tant qu'elles répondent 404, la
mémoire est simplement indiquée « pas encore disponible ». Le simulateur du panneau les simule.

RÈGLE ABSOLUE : une IA du nuage ne reçoit JAMAIS un passage de la zone « prive ». Le filtre est appliqué
deux fois : on ne demande que la zone « partageable », ET on jette toute réponse d'une autre zone.
"""

import json

ZONE_PRIVE = "prive"
ZONE_PARTAGEABLE = "partageable"


class Memoire:
    def __init__(self, centre):
        self.centre = centre

    DELAI = 60      # la première recherche charge les modèles sur la carte graphique (~10 s)

    def _appel(self, methode, url, corps=None):
        c = self.centre
        if c.etats["crew"].code != c.L.ACTIF:
            return None, "Crew est éteint : la mémoire n'est pas disponible."
        R = c.L.R
        cle = c.C.analyser_env(c.sys.lire_fichier(R.FICHIER_ENV_CREW), R.NOM_CLE_CREW)
        if not cle:
            return None, f"Clé {R.NOM_CLE_CREW} introuvable."
        try:
            statut, texte = c.sys.http(methode, url, self.DELAI, {"Authorization": "Bearer " + cle}, corps)
        finally:
            del cle
        if statut is None:
            return None, "Crew ne répond pas."
        if statut in (401, 403):
            return None, "Clé Crew refusée."
        if statut == 404:
            return None, "La mémoire n'est pas encore exposée par le serveur Crew."
        if statut != 200:
            return None, f"La mémoire a répondu {statut}."
        try:
            return json.loads(texte), ""
        except ValueError:
            return None, "Réponse de la mémoire illisible."

    def etat(self):
        R = self.centre.L.R
        d, msg = self._appel("GET", R.URL_CREW_MEMOIRE_ETAT)
        if d is None or not isinstance(d, dict):
            return {"disponible": False, "message": msg or "Réponse inattendue."}
        return {"disponible": True, "fichiers": d.get("fichiers"), "morceaux": d.get("morceaux"),
                "par_zone": d.get("par_zone") or {}, "derniere_indexation": d.get("derniere_indexation")}

    def chercher(self, question, nombre=5, nuage=False):
        """Renvoie (passages, message). `nuage=True` : jamais de zone privée, quoi que renvoie le serveur."""
        question = str(question or "").strip()[:2000]
        if not question:
            return [], "Question vide."
        R = self.centre.L.R
        corps = {"question": question, "nombre": max(1, min(int(nombre), 10))}
        if nuage:
            corps["zones"] = [ZONE_PARTAGEABLE]
        d, msg = self._appel("POST", R.URL_CREW_MEMOIRE_CHERCHER, corps)
        if d is None:
            return [], msg
        passages = []
        for p in (d.get("passages") if isinstance(d, dict) else None) or []:
            if not isinstance(p, dict) or not p.get("texte"):
                continue
            zone = str(p.get("zone", ""))
            if nuage and zone != ZONE_PARTAGEABLE:      # deuxième verrou : zone inconnue = privée
                continue
            passages.append({"chemin": str(p.get("chemin", "?")), "zone": zone,
                             "texte": str(p["texte"])[:4000], "score": p.get("score"), "voies": p.get("voies")})
        return passages, ""
