# -*- coding: utf-8 -*-
"""Salle Crew : menu de modèles à liste fixe (sans rien demander à Crew)."""

from centre.salles import MODELES_CREW, ErreurSalle
import pytest

QUATRE = ["crew-normal", "crew-maxperf", "crew-confidentiel", "crew-ultra"]


def test_liste_fixe_de_quatre_choix_sans_table_ronde(centre):
    assert centre.salles.modeles_disponibles("crew") == QUATRE           # Crew arrêté (rien allumé) : la liste est quand même là
    assert "crew-tableronde" not in dict(MODELES_CREW)                    # la table ronde n'est pas un modèle
    assert MODELES_CREW[0] == ("crew-normal", "Suit le mode choisi dans le panneau (Économe par défaut)")
    assert dict(MODELES_CREW)["crew-ultra"] == "Tout est local, orchestration comprise"
    assert centre.salles.reglage("crew")["modele"] == "crew-normal"        # valeur par défaut


def test_aucune_requete_reseau_pour_construire_la_liste(centre, reseau):
    avant = len(reseau.appels)
    centre.salles.modeles_disponibles("crew")
    assert len(reseau.appels) == avant


def test_api_explications_et_defaut(client):
    r = client.get("/api/salles/crew/modeles").json()
    assert r["modeles"] == QUATRE and r["defaut"] == "crew-normal"
    assert r["explications"]["crew-confidentiel"] == "Tout reste en local (gemma)"
    assert set(r["explications"]) == set(QUATRE)
    autre = client.get("/api/salles/deepseek/modeles").json()
    assert "explications" not in autre                                     # les autres salles : comportement inchangé


def test_valeur_inconnue_conservee_puis_remplacable(centre):
    import json
    with open(centre.salles._chemin_reglages, "w", encoding="utf-8") as f:
        json.dump({"crew": {"modele": "ancien-modele"}}, f)                # ancienne valeur (faute de frappe)
    assert centre.salles.reglage("crew")["modele"] == "ancien-modele"      # jamais supprimée en silence
    assert "ancien-modele" not in centre.salles.modeles_disponibles("crew")
    centre.salles.definir_reglage("crew", modele="ancien-modele")          # la re-enregistrer telle quelle reste permis
    centre.salles.definir_reglage("crew", modele="crew-normal")            # …et on peut la remplacer
    assert centre.salles.reglage("crew")["modele"] == "crew-normal"


def test_nouvelle_valeur_hors_liste_refusee_pour_crew(centre):
    with pytest.raises(ErreurSalle, match="inconnu"):
        centre.salles.definir_reglage("crew", modele="crew-normall")
    with pytest.raises(ErreurSalle):
        centre.salles.definir_reglage("crew", modele="crew-tableronde")


def test_autres_salles_inchangees(centre):
    assert centre.salles.modeles_disponibles("claude") == []
    centre.salles.definir_reglage("deepseek", modele="n-importe-quoi-valide")   # texte libre toujours accepté ailleurs
    assert centre.salles.reglage("deepseek")["modele"] == "n-importe-quoi-valide"


def test_chatgpt_abonnement_sans_modele_inchange(centre):
    centre.salles.definir_reglage("chatgpt", auth="abonnement")
    assert centre.salles.reglage("chatgpt")["modele"] == ""
