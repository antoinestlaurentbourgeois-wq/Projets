# -*- coding: utf-8 -*-
"""Page « Chef d'équipe » et salles par modèle LM Studio. Faux Crew (simulateur) : aucun vrai LM Studio, aucun vrai réseau."""

import json

import pytest

from conftest import sse
from test_salles import allumer, envoyer, mode, texte, types

URL_CHEF = "http://127.0.0.1:8765/chef"
AUTRE = "qwen/qwen3-14b"
GROS = "google/gemma-3-27b"
URL_LMSTUDIO = "http://127.0.0.1:1234/v1/chat/completions"


def puts(simulateur):
    return [r for r in simulateur.requetes if r[0] == "PUT" and r[1] == URL_CHEF]


def suivre(client, max_pas=12):
    """Interroge GET /api/crew/chef (comme l'écran, toutes les 2 s) jusqu'à la fin du changement ; renvoie (étapes vues, dernier état)."""
    etapes, d = [], None
    for _ in range(max_pas):
        d = client.get("/api/crew/chef").json()
        ch = d["changement"]
        if ch and ch["etape"] and (not etapes or etapes[-1] != ch["etape"]):
            etapes.append(ch["etape"])
        if ch and ch["etat"] in ("termine", "echec"):
            return etapes, d
    raise AssertionError(f"changement jamais terminé : {etapes}")


def salles(centre):
    return {s["id"]: s for s in centre.salles.catalogue()}


def id_salle(centre, modele):
    return centre.salles.ident_du_modele(modele, centre.L.R.MODELE_GEMMA)


# ----- lecture ----------------------------------------------------------------------------------------------------

def test_liste_sans_embeddings_un_seul_chef(client, centre, simulateur):
    allumer(centre, simulateur)
    d = client.get("/api/crew/chef").json()
    ids = [m["id"] for m in d["modeles"]]
    assert ids == [centre.L.R.MODELE_GEMMA, AUTRE, GROS] and centre.L.R.MODELE_EMBEDDINGS not in ids       # jamais d'embeddings
    assert [m["id"] for m in d["modeles"] if m["chef"]] == [centre.L.R.MODELE_GEMMA]                      # UN seul chef (= un seul interrupteur actif)
    assert d["source"] == "crew" and d["modifiable"] and d["chef"] == centre.L.R.MODELE_GEMMA and d["chef_charge"] is True
    gros = [m for m in d["modeles"] if m["id"] == GROS][0]
    assert "presque aussi gros" in gros["avertissement"] and gros["taille_go"] == 16.5 and gros["charge"] is False


def test_embeddings_filtres_meme_si_crew_en_envoyait(centre, simulateur):
    allumer(centre, simulateur)
    simulateur.chef_modeles_lm.append({"id": centre.L.R.MODELE_EMBEDDINGS, "libelle": "Nomic", "architecture": "nomic-bert"})
    assert centre.L.R.MODELE_EMBEDDINGS not in [m["id"] for m in centre.chef()["modeles"]]


def test_session_requise(anonyme):
    assert anonyme.get("/api/crew/chef").status_code == 401
    assert anonyme.put("/api/crew/chef", json={"modele": AUTRE}).status_code == 401


# ----- changement --------------------------------------------------------------------------------------------------

def test_changement_reussi_avec_etapes(client, centre, simulateur):
    allumer(centre, simulateur)
    r = client.put("/api/crew/chef", json={"modele": AUTRE})
    assert r.status_code == 202 and r.json()["changement"]["etat"] == "en_cours" and r.json()["changement"]["cible"] == AUTRE
    assert puts(simulateur) == [("PUT", URL_CHEF, True)]                                # clé Crew utilisée côté serveur seulement
    d = client.get("/api/crew/chef").json()
    assert d["changement"]["etat"] == "en_cours" and d["modifiable"] is False               # interrupteurs désactivés pendant le changement
    premiere = d["changement"]["etape"]
    etapes, d = suivre(client)
    assert [e.split(" ")[0] for e in [premiere] + etapes] == ["Déchargement", "Chargement", "Test", "Terminé"] and "Déchargement de" in premiere
    assert d["changement"]["etat"] == "termine" and d["chef"] == AUTRE and d["chef_charge"] is True
    assert [m["id"] for m in d["modeles"] if m["chef"]] == [AUTRE]                          # toujours un seul chef actif
    assert d["dernier_test"] == {"modele": AUTRE, "ok": True, "json_valides": 3, "sur": 3, "duree_moy_s": 1.1}
    assert d["ancien_chef"] == centre.L.R.MODELE_GEMMA                                      # pour « Revenir à … »
    assert centre.chef_actuel().modele == AUTRE and centre.ctrl.chef_actuel().modele == AUTRE


def test_echec_retour_automatique_a_l_ancien_chef(client, centre, simulateur):
    allumer(centre, simulateur)
    simulateur.chef_echec = "Mémoire vidéo insuffisante"
    assert client.put("/api/crew/chef", json={"modele": GROS}).status_code == 202
    etapes, d = suivre(client)
    assert d["changement"]["etat"] == "echec" and "insuffisante" in d["changement"]["message"] and "Crew a remis" in d["changement"]["message"]
    assert d["chef"] == centre.L.R.MODELE_GEMMA and [m["id"] for m in d["modeles"] if m["chef"]] == [centre.L.R.MODELE_GEMMA]


def test_travail_en_cours_409(client, centre, simulateur):
    allumer(centre, simulateur)
    simulateur.chef_conflit = True
    r = client.put("/api/crew/chef", json={"modele": AUTRE})
    assert r.status_code == 409 and "travail Crew" in r.json()["erreur"]
    simulateur.chef_conflit = False
    assert client.put("/api/crew/chef", json={"modele": AUTRE}).status_code == 202
    r = client.put("/api/crew/chef", json={"modele": GROS})                                  # un changement est déjà en cours
    assert r.status_code == 409 and "déjà en cours" in r.json()["erreur"]


def test_modele_inconnu_ou_embeddings_400(client, centre, simulateur):
    allumer(centre, simulateur)
    for mauvais in ("pas/un/modele", centre.L.R.MODELE_EMBEDDINGS):
        r = client.put("/api/crew/chef", json={"modele": mauvais})
        assert r.status_code == 400 and "refuse" in r.json()["erreur"]
    assert len(puts(simulateur)) == 2                                                           # Crew a bien été interrogé, et a refusé


def test_identifiant_dangereux_refuse_sans_appeler_crew(client, centre, simulateur):
    allumer(centre, simulateur)
    for mauvais in ("../x", "-rf", "a b", "x;y", "", None, 5, ["a"]):
        assert client.put("/api/crew/chef", json={"modele": mauvais}).status_code == 400
    assert puts(simulateur) == []


def test_lm_studio_arrete_503_et_crew_arrete_422(client, centre, simulateur):
    allumer(centre, simulateur)
    simulateur.lms_serveur = False
    r = client.put("/api/crew/chef", json={"modele": AUTRE})
    assert r.status_code == 503 and "LM Studio" in r.json()["erreur"]
    d = client.get("/api/crew/chef").json()
    assert d["lmstudio"] is False and d["modifiable"] is False and "LM Studio" in d["raison"]
    simulateur.crew_pids = []
    centre.rafraichir()
    n = len(puts(simulateur))
    r = client.put("/api/crew/chef", json={"modele": AUTRE})
    assert r.status_code == 422 and "éteint" in r.json()["erreur"] and len(puts(simulateur)) == n          # rien n'est envoyé à un Crew arrêté


def test_test_mauvais_avertissement_et_retour_possible(client, centre, simulateur):
    allumer(centre, simulateur)
    simulateur.chef_test_mauvais = True
    client.put("/api/crew/chef", json={"modele": AUTRE})
    etapes, d = suivre(client)
    assert d["changement"]["etat"] == "termine" and d["chef"] == AUTRE                      # le changement reste fait
    assert d["dernier_test"]["ok"] is False and d["dernier_test"]["json_valides"] == 1 and d["dernier_test"]["sur"] == 3
    assert d["ancien_chef"] == centre.L.R.MODELE_GEMMA and d["ancien_nom"]                   # de quoi afficher « Revenir à <ancien chef> »
    simulateur.chef_test_mauvais = False
    client.put("/api/crew/chef", json={"modele": d["ancien_chef"]})                         # « Revenir » = un nouveau PUT, sur clic
    _, d2 = suivre(client)
    assert d2["chef"] == centre.L.R.MODELE_GEMMA and d2["dernier_test"]["ok"] is True


def test_le_put_ne_part_jamais_sans_clic(client, centre, simulateur):
    allumer(centre, simulateur)
    for _ in range(3):
        centre.rafraichir()
        client.get("/api/crew/chef")
        client.get("/api/etat")
        client.get("/api/salles")
        client.get("/api/table-ronde/options")
    assert puts(simulateur) == []
    assert simulateur.chef_changement is None


def test_recus_sans_secret(client, centre, simulateur):
    allumer(centre, simulateur)
    client.put("/api/crew/chef", json={"modele": AUTRE})
    client.put("/api/crew/chef", json={"modele": "../x"})
    recus = open(centre.config.chemin("recus.jsonl"), encoding="utf-8").read()
    assert recus.count('"chef_crew"') == 2 and '"ok"' in recus and '"refuse"' in recus
    assert "cle-crew-secrete" not in recus and "Bearer" not in recus


# ----- Crew arrêté : lecture du fichier de secours --------------------------------------------------------------------

def test_crew_arrete_lit_le_fichier_de_secours_sans_rien_ecrire(client, centre, simulateur):
    R = centre.L.R
    simulateur.fichiers[R.FICHIER_CHEF] = json.dumps({"modele": AUTRE, "contexte": 24000, "parallele": 2})
    d = client.get("/api/crew/chef").json()                                                   # rien n'est allumé
    assert d["source"] == "fichier" and d["chef"] == AUTRE and d["modifiable"] is False and "arrêté" in d["raison"]
    assert [m["id"] for m in d["modeles"] if m["chef"]] == [AUTRE]
    assert simulateur.fichiers[R.FICHIER_CHEF] == json.dumps({"modele": AUTRE, "contexte": 24000, "parallele": 2})     # jamais modifié
    assert centre.chef_actuel().contexte == 24000 and centre.chef_actuel().parallele == 2


def test_sans_fichier_ni_crew_le_chef_est_gemma(client, centre, simulateur):
    d = client.get("/api/crew/chef").json()
    assert d["chef"] == centre.L.R.MODELE_GEMMA and d["source"] == "fichier"
    simulateur.fichiers[centre.L.R.FICHIER_CHEF] = "{ pas du json"
    assert client.get("/api/crew/chef").json()["chef"] == centre.L.R.MODELE_GEMMA
    simulateur.fichiers[centre.L.R.FICHIER_CHEF] = json.dumps({"modele": "../../evil"})
    assert client.get("/api/crew/chef").json()["chef"] == centre.L.R.MODELE_GEMMA


# ----- une salle par modèle, une seule « verte » ------------------------------------------------------------------------

def test_une_salle_par_modele_une_seule_verte(client, centre, simulateur):
    allumer(centre, simulateur)
    centre.chef()                                                                             # un chef lu : les salles des modèles apparaissent
    d = salles(centre)
    s_autre, s_gros = id_salle(centre, AUTRE), id_salle(centre, GROS)
    assert s_autre.startswith("lm-qwen3-14b-") and s_gros.startswith("lm-gemma-3-27b-") and "/" not in s_autre and "." not in s_gros     # court nom sûr, jamais le chemin brut
    assert id_salle(centre, centre.L.R.MODELE_GEMMA) == "gemma"                                # la salle « gemma » garde son identifiant
    verts = [i for i in (d["gemma"], d[s_autre], d[s_gros]) if i["disponible"]]
    assert [v["id"] for v in verts] == ["gemma"]
    for sid in (s_autre, s_gros):
        assert d[sid]["disponible"] is False and "n'est pas le chef d'équipe" in d[sid]["raison"] and "Chef d'équipe" in d[sid]["raison"]
        assert d[sid]["lien"] == "chef" and d[sid]["lecture_seule"] is True and d[sid]["locale"] is True


def test_quand_le_chef_change_les_salles_changent_de_couleur(client, centre, simulateur):
    allumer(centre, simulateur)
    centre.chef()
    client.put("/api/crew/chef", json={"modele": AUTRE})
    suivre(client)
    d = salles(centre)
    assert d[id_salle(centre, AUTRE)]["disponible"] is True and d["gemma"]["disponible"] is False
    assert "n'est pas le chef d'équipe" in d["gemma"]["raison"]


def test_salle_grisee_relisible_mais_pas_d_envoi(client, centre, simulateur, reseau):
    allumer(centre, simulateur)
    centre.chef()
    s_autre = id_salle(centre, AUTRE)
    reseau.repondre(URL_LMSTUDIO, lambda c, e: sse("réponse"))
    conv = centre.salles.creer_conversation("gemma")
    centre.salles.conversations.ajouter_message(conv, "user", "ancienne question")
    centre.salles.conversations.enregistrer(conv)
    client.put("/api/crew/chef", json={"modele": AUTRE}); suivre(client)                          # gemma n'est plus le chef
    assert client.get(f"/api/conversations/{conv['id']}").json()["messages"][0]["texte"] == "ancienne question"     # relisible
    evts, _ = envoyer(centre, "gemma", "nouvelle question")
    assert types(evts) == ["erreur"] and "chef d'équipe" in evts[0]["message"]
    assert not [a for a in reseau.appels if a[1] == URL_LMSTUDIO]                                    # rien n'est envoyé


def test_salle_du_chef_envoie_avec_son_modele(centre, simulateur, reseau):
    allumer(centre, simulateur)
    centre.chef()
    centre.salles.conversations  # noqa: B018
    simulateur.chef_id = AUTRE
    simulateur.modeles[AUTRE] = 1; simulateur.modeles[centre.L.R.MODELE_GEMMA] = 0
    centre.rafraichir()
    reseau.repondre(URL_LMSTUDIO, lambda c, e: sse("je suis le chef"))
    s_autre = id_salle(centre, AUTRE)
    evts, conv = envoyer(centre, s_autre, "bonjour")
    assert texte(evts) == "je suis le chef"
    appel = [a for a in reseau.appels if a[1] == URL_LMSTUDIO][-1]
    assert appel[2]["model"] == AUTRE and conv["salle"] == s_autre


def test_salles_de_modeles_locales_meme_en_ultra_confidentiel_et_pour_le_prive(client, centre, simulateur, reseau):
    allumer(centre, simulateur)
    centre.chef()
    simulateur.chef_id = AUTRE
    simulateur.modeles[AUTRE] = 1; simulateur.modeles[centre.L.R.MODELE_GEMMA] = 0
    centre.rafraichir()
    s_autre = id_salle(centre, AUTRE)
    reseau.repondre(URL_LMSTUDIO, lambda c, e: sse("ok local"))
    for m in ("confidentiel", "ultra-confidentiel", "ultra"):
        mode(simulateur, centre, m)
        d = salles(centre)
        assert d[s_autre]["disponible"] is True, m                                              # jamais refusée en mode local
        assert d["deepseek"]["disponible"] is False                                             # alors que le nuage l'est
    assert centre.salles.est_locale(s_autre) and centre.salles.estimer(s_autre, 10, 10)["usd"] == 0.0
    conv = centre.salles.creer_conversation(s_autre)
    conv["prive"] = True
    centre.salles.conversations.enregistrer(conv)
    evts = centre.salles.demarrer_envoi(conv["id"], "donnée privée", {}).attendre()
    assert texte(evts) == "ok local"                                                            # le privé reste accepté : salle locale
    assert not [a for a in reseau.appels if "deepseek" in a[1] or "googleapis" in a[1] or "8765" in a[1]]      # jamais de nuage ni de Crew
    assert centre.couts.totaux()["aujourdhui"]["total"] == 0


def test_modele_disparu_salle_visible_en_lecture_seule(client, centre, simulateur):
    allumer(centre, simulateur)
    centre.chef()
    s_gros = id_salle(centre, GROS)
    simulateur.chef_modeles_lm = [m for m in simulateur.chef_modeles_lm if m["id"] != GROS]     # désinstallé de LM Studio
    centre.chef()
    d = salles(centre)
    assert s_gros in d and d[s_gros]["disponible"] is False and "absent de LM Studio" in d[s_gros]["raison"] and d[s_gros]["lecture_seule"] is True


def test_nouveau_modele_nouvelle_salle_et_memoire_des_salles(centre, simulateur):
    allumer(centre, simulateur)
    centre.chef()
    simulateur.chef_modeles_lm.append({"id": "meta/llama-4-8b", "libelle": "Llama 4 8B", "taille_go": 4.9, "params": "8B", "quantification": "Q4"})
    assert id_salle(centre, "meta/llama-4-8b") not in salles(centre)
    centre.chef()                                                                              # « à la prochaine ouverture »
    assert id_salle(centre, "meta/llama-4-8b") in salles(centre)
    from centre.salles import Salles
    neuve = Salles(centre)                                                                     # redémarrage : les salles sont retrouvées
    assert id_salle(centre, "meta/llama-4-8b") in [s.ident for s in neuve.toutes_les_salles()]


def test_fichier_de_salles_corrompu_ignore(centre):
    with open(centre.config.chemin("salles_lm.json"), "w", encoding="utf-8") as f:
        json.dump({"lm-faux-0000": {"modele": "../evil"}, "gemma": {"modele": "x y"}, "n'importe": 3}, f)
    from centre.salles import Salles
    assert [s.ident for s in Salles(centre).toutes_les_salles()][-1] == "gemma" and len(Salles(centre).toutes_les_salles()) == 7


# ----- table ronde, voyants, « Tout démarrer » ----------------------------------------------------------------------------

def test_table_ronde_gemma_s_affiche_chef_local(client, centre, simulateur):
    allumer(centre, simulateur)
    o = client.get("/api/table-ronde/options").json()
    g = [p for p in o["participants"] if p["id"] == "gemma"][0]
    assert g["libelle"] == "Chef local (Gemma 4 12B (QAT))"
    client.put("/api/crew/chef", json={"modele": AUTRE}); suivre(client)
    o = client.get("/api/table-ronde/options").json()
    assert [p for p in o["participants"] if p["id"] == "gemma"][0]["libelle"] == "Chef local (Qwen3 14B)"     # même identifiant du contrat
    assert [p["id"] for p in o["participants"]] == ["claude", "codex", "gemini", "grok", "deepseek", "gemma"]   # les autres modèles n'y sont pas proposés


def test_tout_demarrer_avec_un_chef_non_gemma_ne_charge_pas_gemma(client, centre, simulateur):
    R = centre.L.R
    simulateur.fichiers[R.FICHIER_CHEF] = json.dumps({"modele": AUTRE, "contexte": 24000, "parallele": 2})
    simulateur.modeles = {R.MODELE_GEMMA: 0, R.MODELE_EMBEDDINGS: 0, AUTRE: 0}
    assert client.post("/api/action", json={"sens": "tout_demarrer"}).status_code == 202
    centre.attendre_action()
    assert simulateur.modeles == {R.MODELE_GEMMA: 0, R.MODELE_EMBEDDINGS: 1, AUTRE: 1}               # gemma n'a PAS été chargé
    charges = [c for c in simulateur.commandes if c[1:2] == ["load"] and c[2] != R.MODELE_EMBEDDINGS]
    assert [c[2] for c in charges] == [AUTRE] and "24000" in charges[0]
    e = client.get("/api/etat").json()
    g = [c for c in e["composants"] if c["ident"] == "gemma"][0]
    assert g["nom"] == "Chef local" and e["composants"][4]["etat"]["code"] == "actif" and "Chef d'équipe" in g["description"]


def test_mode_jeu_libere_le_chef_actuel(client, centre, simulateur):
    R = centre.L.R
    simulateur.fichiers[R.FICHIER_CHEF] = json.dumps({"modele": AUTRE})
    simulateur.tout_allumer()
    simulateur.modeles = {R.MODELE_GEMMA: 0, R.MODELE_EMBEDDINGS: 1, AUTRE: 1}
    assert client.post("/api/action", json={"sens": "mode_jeu"}).status_code == 202
    centre.attendre_action()
    assert simulateur.modeles == {R.MODELE_GEMMA: 0, R.MODELE_EMBEDDINGS: 0, AUTRE: 0}             # la carte graphique est libérée
