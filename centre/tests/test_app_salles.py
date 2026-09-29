# -*- coding: utf-8 -*-
import json

import pytest

from conftest import sse
from centre.salles import URLS_API

URL_GEMMA = "http://127.0.0.1:1234/v1/chat/completions"
CID = "0123456789abcdef"

ROUTES = [("GET", "/api/salles"), ("PUT", "/api/salles/gemma/reglage"), ("GET", "/api/salles/gemma/modeles"),
          ("GET", "/api/salles/gemma/estimation"), ("GET", "/api/conversations"), ("POST", "/api/conversations"),
          ("GET", f"/api/conversations/{CID}"), ("PUT", f"/api/conversations/{CID}"), ("DELETE", f"/api/conversations/{CID}"),
          ("POST", f"/api/conversations/{CID}/messages"), ("GET", f"/api/conversations/{CID}/flux"),
          ("POST", f"/api/conversations/{CID}/arreter"), ("POST", f"/api/conversations/{CID}/approbation"),
          ("POST", f"/api/conversations/{CID}/relais"), ("GET", "/api/tiroir"), ("POST", "/api/tiroir"),
          ("GET", "/api/tiroir/abc"), ("PUT", "/api/tiroir/abc"), ("DELETE", "/api/tiroir/abc"),
          ("POST", "/api/memoire/chercher"), ("PUT", "/api/couts/tarifs")]


@pytest.mark.parametrize("methode,chemin", ROUTES)
def test_routes_des_salles_exigent_une_session(anonyme, methode, chemin):
    assert anonyme.request(methode, chemin, json={}).status_code == 401


@pytest.mark.parametrize("methode,chemin", [r for r in ROUTES if r[0] != "GET"])
def test_routes_des_salles_exigent_l_entete_csrf(client, methode, chemin):
    del client.headers["X-Centre"]
    assert client.request(methode, chemin, json={}).status_code == 403


def evenements(reponse):
    return [json.loads(l[6:]) for l in reponse.text.splitlines() if l.startswith("data: ")]


def preparer(client, centre, simulateur, reseau):
    simulateur.tout_allumer(); centre.rafraichir()
    reseau.repondre(URL_GEMMA, lambda c, e: sse("Bon", "jour"))
    return client.post("/api/conversations", json={"salle": "gemma"}).json()


def test_salles_et_politique(client, centre, simulateur):
    d = client.get("/api/salles").json()
    assert len(d["salles"]) == 7 and d["politique"]["nuage"] is True and d["politique"]["mode"] == "econome"
    assert d["memoire"]["disponible"] is False                         # Crew éteint
    simulateur.fichiers[centre.L.R.FICHIER_MODE_CREW] = json.dumps({"mode": "ultra"})
    centre.salles.politique.oublier()
    d = client.get("/api/salles").json()
    assert d["politique"]["nuage"] is False and "rien ne doit quitter" in d["politique"]["message"]


def test_conversation_complete_en_sse(client, centre, simulateur, reseau):
    c = preparer(client, centre, simulateur, reseau)
    r = client.post(f"/api/conversations/{c['id']}/messages", json={"texte": "Salut"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evts = evenements(r)
    assert [e["t"] for e in evts] == ["debut", "delta", "delta", "cout", "fin"]
    d = client.get(f"/api/conversations/{c['id']}").json()
    assert d["messages"][1]["texte"] == "Bonjour" and d["en_cours"] is False
    assert client.get("/api/conversations?salle=gemma").json()["conversations"][0]["id"] == c["id"]
    # reprise du flux depuis un point
    r2 = client.get(f"/api/conversations/{c['id']}/flux?depuis=3")
    assert [e["t"] for e in evenements(r2)] == ["cout", "fin"]
    assert client.get(f"/api/conversations/{CID}/flux").status_code == 404


def test_message_erreurs(client, centre, simulateur, reseau):
    assert client.post("/api/conversations", json={"salle": "inconnue"}).status_code == 404
    assert client.post(f"/api/conversations/{CID}/messages", json={"texte": "x"}).status_code == 200   # flux d'erreur
    r = client.post(f"/api/conversations/{CID}/messages", content=b"pas du json")
    assert r.status_code == 400
    assert evenements(client.post(f"/api/conversations/{CID}/messages", json={"texte": "x"}))[0]["t"] == "erreur"


def test_renommer_supprimer_arreter(client, centre, simulateur, reseau):
    c = preparer(client, centre, simulateur, reseau)
    assert client.put(f"/api/conversations/{c['id']}", json={"titre": "Mon titre"}).json()["titre"] == "Mon titre"
    assert client.put(f"/api/conversations/{c['id']}", json={"titre": " "}).status_code == 400
    assert client.post(f"/api/conversations/{c['id']}/arreter").json() == {"arrete": False}
    assert client.delete(f"/api/conversations/{c['id']}").status_code == 200
    assert client.get(f"/api/conversations/{c['id']}").status_code == 404
    assert client.delete(f"/api/conversations/{c['id']}").status_code == 404
    assert any(r["action"] == "conversation_supprimee" for r in client.get("/api/recus").json()["recus"])


def test_relais_api(client, centre, simulateur, reseau):
    c = preparer(client, centre, simulateur, reseau)
    client.post(f"/api/conversations/{c['id']}/messages", json={"texte": "Question ?"})
    r = client.post(f"/api/conversations/{c['id']}/relais", json={"vers": "deepseek", "portee": "reponse"})
    assert r.status_code == 201 and "Question ?" in r.json()["brouillon"]
    assert client.post(f"/api/conversations/{c['id']}/relais", json={"vers": "nimporte"}).status_code == 404
    assert client.post(f"/api/conversations/{c['id']}/relais", json={"vers": "deepseek", "portee": "x"}).status_code == 400


def test_tiroir_api_et_zone_journalisee(client):
    r = client.post("/api/tiroir", json={"titre": "Note", "texte": "contenu"})
    assert r.status_code == 201 and r.json()["zone"] == "prive" and "texte" not in r.json()
    ident = r.json()["id"]
    assert client.get("/api/tiroir").json()["elements"][0]["taille"] == 7
    assert client.get(f"/api/tiroir/{ident}").json()["texte"] == "contenu"
    assert client.put(f"/api/tiroir/{ident}", json={"zone": "partageable"}).json()["zone"] == "partageable"
    assert any(x["action"] == "tiroir_zone" for x in client.get("/api/recus").json()["recus"])
    assert client.put(f"/api/tiroir/{ident}", json={"zone": "secrète"}).status_code == 400
    assert client.post("/api/tiroir", json={"texte": ""}).status_code == 400
    assert client.post("/api/tiroir", json={"texte": "x" * 20001}).status_code == 400
    assert client.delete(f"/api/tiroir/{ident}").status_code == 200
    assert client.get(f"/api/tiroir/{ident}").status_code == 404


def test_reglages_estimation_modeles_tarifs(client, centre, reseau):
    assert client.put("/api/salles/deepseek/reglage", json={"modele": "deepseek-reasoner"}).json()["modele"] == "deepseek-reasoner"
    assert client.put("/api/salles/deepseek/reglage", json={"modele": "../x"}).status_code == 400
    assert client.put("/api/salles/nulle/reglage", json={}).status_code == 404
    assert client.get("/api/salles/gemma/estimation?longueur=100").json()["texte"] == "Gratuit (local)"
    assert client.get("/api/salles/gemma/estimation?longueur=abc").status_code == 400
    reseau.modeles["https://api.deepseek.com/models"] = ["a", "b"]
    assert client.get("/api/salles/deepseek/modeles").json()["modeles"] == ["a", "b"]
    r = client.put("/api/couts/tarifs", json={"salle": "deepseek", "entree": 0.5, "sortie": 2})
    assert r.status_code == 200 and r.json()["tarifs_texte"]["deepseek"]["verifie"] is True
    assert client.put("/api/couts/tarifs", json={"salle": "deepseek", "entree": "x", "sortie": 2}).status_code == 400
    assert client.get("/api/couts").json()["tarifs_texte"]["deepseek"]["entree"] == 0.5


def test_memoire_api(client, centre, simulateur):
    r = client.post("/api/memoire/chercher", json={"question": "couple de serrage"}).json()
    assert r["passages"] == [] and "éteint" in r["message"]
    simulateur.tout_allumer(); centre.rafraichir()
    r = client.post("/api/memoire/chercher", json={"question": "couple de serrage vis"}).json()
    assert r["passages"] and r["passages"][0]["zone"] == "partageable"
    simulateur.memoire_disponible = False
    assert "pas encore exposée" in client.post("/api/memoire/chercher", json={"question": "couple"}).json()["message"]
    assert client.get("/api/salles").json()["memoire"]["disponible"] is False


def test_etat_memoire_simule(client, centre, simulateur):
    simulateur.tout_allumer(); centre.rafraichir()
    m = client.get("/api/salles").json()["memoire"]
    assert m["disponible"] and m["par_zone"] == {"prive": 1, "partageable": 1}
