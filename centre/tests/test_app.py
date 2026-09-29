# -*- coding: utf-8 -*-
"""Serveur complet + panneau, avec le simulateur : aucune vraie commande, aucun vrai réseau."""

import json
import os
import re

import pytest

from conftest import NIP, SECRET

ROUTES_GET = ["/", "/s/app.js", "/api/etat", "/api/plan?sens=demarrer&ident=crew", "/api/action", "/api/crew/mode",
              "/api/crew/moteurs", "/api/couts", "/api/couts/deepseek", "/api/recus", "/api/journal", "/inconnu", "/s/app.html"]
ROUTES_ECRITURE = [("POST", "/api/action", {"sens": "mode_jeu"}), ("PUT", "/api/crew/mode", {"mode": "maxperf"}),
                   ("POST", "/api/ouvrir", {"ident": "docker"}), ("PUT", "/api/couts/plafonds", {"jour": 1}),
                   ("POST", "/api/deconnexion", {})]


# ----- verrou / sécurité ---------------------------------------------------------------------

@pytest.mark.parametrize("chemin", ROUTES_GET)
def test_tout_exige_une_session(anonyme, chemin):
    r = anonyme.get(chemin)
    assert r.status_code in (303, 401), (chemin, r.status_code)
    if r.status_code == 303:
        assert r.headers["location"] == "/connexion" and not chemin.startswith("/api/")


@pytest.mark.parametrize("methode,chemin,corps", ROUTES_ECRITURE)
def test_ecritures_exigent_une_session(anonyme, methode, chemin, corps):
    assert anonyme.request(methode, chemin, json=corps).status_code == 401


@pytest.mark.parametrize("chemin", ["/connexion", "/manifest.webmanifest", "/sw.js", "/s/style.css", "/s/connexion.js",
                                    "/s/icone-192.png", "/s/icone-512.png", "/s/icone.svg", "/api/verrou"])
def test_fichiers_publics(anonyme, chemin):
    assert anonyme.get(chemin).status_code == 200


def test_les_pages_publiques_ne_donnent_aucune_information_sur_le_pc(anonyme):
    for chemin in ("/connexion", "/api/verrou", "/manifest.webmanifest"):
        brut = anonyme.get(chemin).text.lower()
        assert "docker" not in brut and "gemma" not in brut and "crew_api" not in brut


def test_verifie_la_connexion(anonyme):
    assert anonyme.post("/api/connexion", json={"nip": NIP, "secret": "mauvais-secret-1"}).status_code == 401
    assert anonyme.post("/api/connexion", content=b"pas du json").status_code == 400
    r = anonyme.post("/api/connexion", json={"nip": NIP, "secret": SECRET})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=43200" in cookie
    assert anonyme.get("/api/etat").status_code == 200


def test_cookie_secure_derriere_https(anonyme):
    r = anonyme.post("/api/connexion", json={"nip": NIP, "secret": SECRET}, headers={"X-Forwarded-Proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_blocage_apres_echecs_via_http(anonyme):
    for _ in range(5):
        anonyme.post("/api/connexion", json={"nip": "000000", "secret": "x" * 12})
    r = anonyme.post("/api/connexion", json={"nip": NIP, "secret": SECRET})
    assert r.status_code == 429 and r.json()["attente"] > 0


def test_verrou_non_defini_rien_ne_passe(centre, tmp_path):
    from starlette.testclient import TestClient
    from centre.app import creer_app
    from centre.verrou import Verrou
    v = Verrou(str(tmp_path / "vide.json"))
    c = TestClient(creer_app(centre, v), base_url="http://127.0.0.1:8740", follow_redirects=False)
    c.headers["X-Centre"] = "1"
    assert c.get("/api/verrou").json()["defini"] is False
    assert c.post("/api/connexion", json={"nip": NIP, "secret": SECRET}).status_code == 401
    assert c.get("/api/etat").status_code == 401


def test_deconnexion(client):
    assert client.post("/api/deconnexion").status_code == 200
    client.cookies.clear()
    assert client.get("/api/etat").status_code == 401


@pytest.mark.parametrize("hote", ["evil.example", "127.0.0.1:9999", "localhost.evil.example", ""])
def test_hote_inconnu_refuse(client, hote):
    assert client.get("/api/etat", headers={"Host": hote}).status_code == 421


def test_localhost_accepte(client):
    assert client.get("/api/etat", headers={"Host": "localhost:8740"}).status_code == 200


def test_hote_tailscale_autorise_seulement_si_configure(centre, verrou):
    from starlette.testclient import TestClient
    from centre.app import creer_app
    centre.config.hotes_autorises = ("pc.tail1234.ts.net",)
    c = TestClient(creer_app(centre, verrou), base_url="https://pc.tail1234.ts.net")
    c.headers["X-Centre"] = "1"
    assert c.post("/api/connexion", json={"nip": NIP, "secret": SECRET}).status_code == 200
    assert c.get("/api/etat").status_code == 200


def test_csrf_entete_obligatoire(client):
    del client.headers["X-Centre"]
    assert client.put("/api/couts/plafonds", json={"jour": 1}).status_code == 403
    assert client.get("/api/etat").status_code == 200        # la lecture reste possible


def test_csrf_origine_etrangere_refusee(client):
    r = client.put("/api/couts/plafonds", json={"jour": 1}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.put("/api/couts/plafonds", json={"jour": 1}, headers={"Origin": "http://127.0.0.1:8740"})
    assert r.status_code == 200


def test_entetes_de_securite(client):
    for chemin in ("/", "/api/etat"):
        r = client.get(chemin)
        assert "default-src 'self'" in r.headers["content-security-policy"]
        assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"


def test_interface_sans_script_ni_style_en_ligne():
    dossier = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "centre", "static")
    for nom in ("app.html", "connexion.html"):
        html = open(os.path.join(dossier, nom), encoding="utf-8").read()
        assert not re.search(r"<script(?![^>]*\bsrc=)", html) and "style=" not in html and "<style" not in html
        assert not re.search(r"\son[a-z]+=", html)
    js = open(os.path.join(dossier, "app.js"), encoding="utf-8").read()
    assert "innerHTML" not in js and "eval(" not in js and "document.write" not in js


def test_pas_de_traversee_de_dossier(client):
    for chemin in ("/s/..%2f..%2fapp.py", "/s/%2e%2e/config.py", "/s/..\\config.py"):
        assert client.get(chemin).status_code in (400, 404)


# ----- page Centre ------------------------------------------------------------------------------

def etat(client):
    return {c["ident"]: c["etat"] for c in client.get("/api/etat").json()["composants"]}


def attendre(client, centre):
    job = centre.attendre_action()
    assert job["statut"] in ("termine", "erreur"), job
    return job


def test_etat_initial(client):
    d = client.get("/api/etat").json()
    assert [c["ident"] for c in d["composants"]] == ["docker", "openwebui", "kokoro", "lmstudio", "gemma", "embeddings", "crew"]
    assert all(c["etat"]["code"] in ("arrete", "inconnu") for c in d["composants"])
    assert d["cles"]["DEEPSEEK_API_KEY"] is True and d["cles"]["GEMINI_API_KEY"] is False


def test_demarrer_docker(client, centre):
    r = client.post("/api/action", json={"sens": "demarrer", "ident": "docker"})
    assert r.status_code == 202 and r.json()["statut"] in ("en_cours", "termine")
    attendre(client, centre)
    assert etat(client)["docker"]["code"] == "actif"
    assert client.get("/api/action").json()["action"]["resultats"]["docker"]["code"] == "actif"


def test_dependances_a_confirmer(client, centre):
    plan = client.get("/api/plan?sens=demarrer&ident=crew").json()["liees"]
    assert [x["ident"] for x in plan] == ["lmstudio", "gemma"]
    r = client.post("/api/action", json={"sens": "demarrer", "ident": "crew"})
    assert r.status_code == 409 and [x["ident"] for x in r.json()["liees"]] == ["lmstudio", "gemma"]
    r = client.post("/api/action", json={"sens": "demarrer", "ident": "crew", "avec_liees": True})
    assert r.status_code == 202
    job = attendre(client, centre)
    assert [e["ident"] for e in job["etapes"]] == ["lmstudio", "gemma", "crew"]
    assert {i: etat(client)[i]["code"] for i in ("lmstudio", "gemma", "crew")} == {"lmstudio": "actif", "gemma": "actif", "crew": "actif"}


def test_arret_avec_dependants(client, centre, simulateur):
    simulateur.tout_allumer(); centre.rafraichir()
    plan = client.get("/api/plan?sens=arreter&ident=lmstudio").json()["liees"]
    assert {x["ident"] for x in plan} == {"gemma", "embeddings", "crew"}
    assert client.post("/api/action", json={"sens": "arreter", "ident": "lmstudio"}).status_code == 409
    assert client.post("/api/action", json={"sens": "arreter", "ident": "lmstudio", "avec_liees": True}).status_code == 202
    attendre(client, centre)
    e = etat(client)
    assert e["lmstudio"]["code"] == "arrete" and e["crew"]["code"] == "arrete"


def test_mode_jeu_et_tout_demarrer(client, centre, simulateur):
    assert client.post("/api/action", json={"sens": "tout_demarrer"}).status_code == 202
    attendre(client, centre)
    assert all(v["code"] == "actif" for v in etat(client).values())
    assert client.post("/api/action", json={"sens": "mode_jeu"}).status_code == 202
    attendre(client, centre)
    assert all(v["code"] == "arrete" for v in etat(client).values())


def test_une_seule_action_a_la_fois(client, centre, simulateur):
    import threading
    porte = threading.Event()
    original = simulateur.dormir
    simulateur.dormir = lambda s: (porte.wait(2), original(s))[1]
    try:
        assert client.post("/api/action", json={"sens": "demarrer", "ident": "docker"}).status_code == 202
        r = client.post("/api/action", json={"sens": "demarrer", "ident": "lmstudio"})
        assert r.status_code == 409 and "déjà en cours" in r.json()["erreur"]
    finally:
        porte.set()
        centre.attendre_action()
        simulateur.dormir = original


@pytest.mark.parametrize("corps", [{"sens": "detruire"}, {"sens": "demarrer", "ident": "rm -rf"}, {"sens": "demarrer"}, {}])
def test_actions_invalides(client, corps):
    assert client.post("/api/action", json=corps).status_code in (400, 404)


def test_plan_invalide(client):
    assert client.get("/api/plan?sens=x&ident=docker").status_code == 400
    assert client.get("/api/plan?sens=demarrer&ident=zzz").status_code == 404


def test_mode_crew(client, centre, simulateur):
    simulateur.tout_allumer(); centre.rafraichir()
    m = client.get("/api/crew/mode").json()
    assert m["actuel"] == "econome" and m["serveur_actif"] and len(m["modes"]) == 4 and m["modes"][0]["explication"]
    r = client.put("/api/crew/mode", json={"mode": "confidentiel"})
    assert r.status_code == 200 and r.json()["actuel"] == "confidentiel"
    assert client.get("/api/etat").json()["mode"]["actuel"] == "confidentiel"
    assert client.put("/api/crew/mode", json={"mode": "inconnu"}).status_code == 422
    assert client.put("/api/crew/mode", json={"mode": 3}).status_code == 400
    assert any(x["action"] == "mode_crew" for x in client.get("/api/recus").json()["recus"])


def test_mode_crew_serveur_eteint_passe_par_le_fichier(client, centre):
    client.get("/api/crew/mode")
    r = client.put("/api/crew/mode", json={"mode": "ultra"})
    assert r.status_code == 200 and r.json()["serveur_actif"] is False and r.json()["actuel"] == "ultra"


def test_moteurs(client, centre, simulateur):
    d = client.get("/api/crew/moteurs").json()
    assert d["moteurs"] is None and "éteint" in d["message"]
    simulateur.tout_allumer(); centre.rafraichir()
    d = client.get("/api/crew/moteurs").json()
    assert d["moteurs"] and {"libelle", "capacite", "cout", "voyant", "etat_texte"} <= set(d["moteurs"][0])


def test_ouvrir(client, centre, simulateur):
    r = client.post("/api/ouvrir", json={"ident": "docker"})
    assert r.status_code == 200
    assert client.post("/api/ouvrir", json={"ident": "kokoro"}).status_code == 404
    assert client.post("/api/ouvrir", json={"ident": "../../x"}).status_code == 404
    assert client.post("/api/ouvrir", json={}).status_code == 400


def test_ouvrir_openwebui_ouvre_une_adresse_locale(client, simulateur):
    assert client.post("/api/ouvrir", json={"ident": "openwebui"}).status_code == 200
    assert simulateur.ouvertures and all("127.0.0.1" in str(o) or "localhost" in str(o) for o in simulateur.ouvertures)


# ----- coûts ---------------------------------------------------------------------------------------

def test_page_couts(client, centre):
    d = client.get("/api/couts").json()
    assert d["bloque"] is False and d["totaux"]["mois"]["total"] == 0 and d["tarifs"]["verifie_le"] == "2026-09-29"
    assert d["plafonds"]["jour"] == {"plafond": None, "depense": 0.0, "atteint": False}
    r = client.put("/api/couts/plafonds", json={"jour": "2", "mois": 20})
    assert r.status_code == 200 and r.json()["plafonds"]["jour"]["plafond"] == 2.0
    centre.couts.enregistrer("deepseek", 2.5)
    d = client.get("/api/couts").json()
    assert d["bloque"] and "plafond du jour" in d["message"] and d["totaux"]["aujourdhui"]["par_ia"] == {"deepseek": 2.5}
    assert client.put("/api/couts/plafonds", json={"jour": "abc"}).status_code == 422
    assert client.put("/api/couts/plafonds", json={"jour": 30, "mois": 20}).status_code == 422
    assert client.put("/api/couts/plafonds", json={"jour": None, "mois": None}).json()["bloque"] is False


def test_solde_deepseek_via_api(client, centre):
    centre.deepseek.http = lambda m, u, e, d: (200, json.dumps({"is_available": True, "balance_infos": [
        {"currency": "USD", "total_balance": "9.99", "granted_balance": "0", "topped_up_balance": "9.99"}]}))
    d = client.get("/api/couts/deepseek").json()
    assert d["ok"] and d["soldes"][0]["total"] == "9.99"


# ----- aucun secret ne sort ----------------------------------------------------------------------------

def test_aucun_secret_dans_les_reponses_ni_les_fichiers(client, centre, simulateur):
    secrets = ["sk-secret-ne-pas-afficher", "cle-crew-secrete", "cle-webui-secrete", SECRET, NIP + '"']
    client.post("/api/action", json={"sens": "tout_demarrer"}); attendre(client, centre)
    centre.deepseek.http = lambda m, u, e, d: (200, json.dumps({"balance_infos": []}))
    client.put("/api/crew/mode", json={"mode": "maxperf"}); client.post("/api/ouvrir", json={"ident": "openwebui"})
    client.get("/api/couts/deepseek?forcer=1")
    textes = [client.get(c).text for c in ("/", "/api/etat", "/api/crew/mode", "/api/crew/moteurs", "/api/couts",
                                           "/api/couts/deepseek", "/api/recus", "/api/journal", "/api/action")]
    for nom in os.listdir(centre.config.dossier_donnees):
        if nom != "verrou.json":
            textes.append(open(centre.config.chemin(nom), encoding="utf-8", errors="replace").read())
    brut = "\n".join(textes)
    for s in secrets:
        assert s not in brut, s
