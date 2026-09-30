# -*- coding: utf-8 -*-
"""« IA sur abonnement dans Crew » : Claude et Codex, décochés par défaut, autorisés seulement sur un clic. Faux Crew (simulateur)."""

import pytest

from test_salles import allumer

URL_AUT = "http://127.0.0.1:8765/autorisations"


def puts(simulateur):
    return [r for r in simulateur.requetes if r[0] == "PUT" and r[1] == URL_AUT]


def par_nom(rep):
    return {a["nom"]: a for a in rep["autorisations"]}


def test_lecture_decoches_par_defaut(centre, simulateur):
    allumer(centre, simulateur)
    r = centre.autorisations()
    assert r["disponible"] and r["limite_min"] == 1 and r["limite_max"] == 500
    a = par_nom(r)
    assert set(a) == {"claude", "codex"}
    assert a["claude"] == {"nom": "claude", "autorise": False, "limite_jour": 20, "utilise_aujourdhui": 0}
    assert a["codex"]["autorise"] is False


def test_liste_des_ia_montre_claude_et_codex_avec_abonnement_et_la_raison(centre, simulateur):
    allumer(centre, simulateur)
    m = {x["nom"]: x for x in centre.moteurs()["moteurs"]}
    for nom in ("claude", "codex"):
        assert m[nom]["abonnement"] is True and m[nom]["etat"] == "indisponible" and m[nom]["voyant"] != "actif"
        assert "Non autorisée pour Crew" in m[nom]["detail"]
    assert m["local"]["abonnement"] is False
    simulateur.autorisations["claude"].update(autorise=True, limite_jour=5, utilise_aujourdhui=5)
    assert "Limite de 5 appels par jour atteinte" in {x["nom"]: x for x in centre.moteurs()["moteurs"]}["claude"]["detail"]
    simulateur.programmes_abonnement_absents = {"codex"}
    simulateur.autorisations["codex"]["autorise"] = True
    assert "introuvable" in {x["nom"]: x for x in centre.moteurs()["moteurs"]}["codex"]["detail"]
    simulateur.autorisations["claude"]["utilise_aujourdhui"] = 0
    assert {x["nom"]: x for x in centre.moteurs()["moteurs"]}["claude"]["etat"] == "pret"


def test_autoriser_puis_changer_la_limite_puis_desautoriser(centre, simulateur):
    allumer(centre, simulateur)
    r = centre.definir_autorisation("claude", True, 30)
    assert par_nom(r)["claude"]["autorise"] is True and par_nom(r)["claude"]["limite_jour"] == 30 and par_nom(r)["codex"]["autorise"] is False
    assert puts(simulateur) == [("PUT", URL_AUT, True)]                        # clé Crew utilisée côté serveur
    r = centre.definir_autorisation("claude", True)                            # sans limite : la limite reste
    assert par_nom(r)["claude"]["limite_jour"] == 30
    r = centre.definir_autorisation("claude", False, 500)
    assert par_nom(r)["claude"]["autorise"] is False and par_nom(r)["claude"]["limite_jour"] == 500
    assert centre.autorisations()["autorisations"][0]["nom"] == "claude"


@pytest.mark.parametrize("limite", [0, 501, -3, 12.5, "20", True, [20]])
def test_limite_invalide_400_sans_appeler_crew(client, centre, simulateur, limite):
    allumer(centre, simulateur)
    r = client.put("/api/crew/autorisations", json={"nom": "claude", "autorise": True, "limite_jour": limite})
    assert r.status_code == 400 and "1 à 500" in r.json()["erreur"]
    assert puts(simulateur) == []
    assert simulateur.autorisations["claude"]["autorise"] is False


def test_nom_ou_autorise_invalides_400(client, centre, simulateur):
    allumer(centre, simulateur)
    for corps in ({"nom": "gemini", "autorise": True}, {"nom": "claude", "autorise": "oui"}, {"nom": "claude"}, {"autorise": True}):
        assert client.put("/api/crew/autorisations", json=corps).status_code == 400
    assert puts(simulateur) == []


def test_le_400_de_crew_est_relaye(client, centre, simulateur):
    allumer(centre, simulateur)
    vrai = simulateur.http
    simulateur.http = lambda m, u, d, e=None, c=None: (400, '{"error": {"message": "limite_jour hors bornes"}}') if m == "PUT" and u == URL_AUT else vrai(m, u, d, e, c)
    r = client.put("/api/crew/autorisations", json={"nom": "claude", "autorise": True, "limite_jour": 20})
    assert r.status_code == 400 and "limite_jour hors bornes" in r.json()["erreur"]


def test_crew_arrete(client, centre, simulateur):
    r = client.get("/api/crew/autorisations").json()                            # rien n'est allumé
    assert r["disponible"] is False and "éteint" in r["message"] and r["autorisations"] == []
    r = client.put("/api/crew/autorisations", json={"nom": "claude", "autorise": True})
    assert r.status_code == 422 and "éteint" in r.json()["erreur"] and "allumez-le" in r.json()["erreur"]
    assert puts(simulateur) == []


def test_jamais_d_envoi_automatique(client, centre, simulateur):
    """Lire, rafraîchir, afficher les IA ou ouvrir la salle Crew n'envoie JAMAIS de PUT /autorisations."""
    allumer(centre, simulateur)
    for _ in range(3):
        centre.rafraichir()
        client.get("/api/crew/autorisations")
        client.get("/api/crew/moteurs")
        client.get("/api/salles")
        client.get("/api/salles/crew/modeles")
        client.get("/api/table-ronde/options")
    assert puts(simulateur) == []
    assert simulateur.autorisations["claude"]["autorise"] is False and simulateur.autorisations["codex"]["autorise"] is False


def test_api_session_requise_et_aucune_cle_dans_les_reponses(anonyme, client, centre, simulateur):
    assert anonyme.get("/api/crew/autorisations").status_code == 401
    assert anonyme.put("/api/crew/autorisations", json={"nom": "claude", "autorise": True}).status_code == 401
    allumer(centre, simulateur)
    brut = client.get("/api/crew/autorisations").text + client.put("/api/crew/autorisations", json={"nom": "codex", "autorise": True}).text
    assert "cle-crew-secrete" not in brut and "Bearer" not in brut


def test_recu_sans_secret(centre, simulateur):
    allumer(centre, simulateur)
    centre.definir_autorisation("codex", True, 10, session="abc")
    recus = open(centre.config.chemin("recus.jsonl"), encoding="utf-8").read()
    assert "autorisation_crew" in recus and "cle-crew-secrete" not in recus
