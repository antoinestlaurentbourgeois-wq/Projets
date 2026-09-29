# -*- coding: utf-8 -*-
"""Phase 4 : accès distant (Tailscale Serve). Le « téléphone » est un client dont l'hôte est un nom Tailscale."""

import json

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import NIP, SECRET
from centre.app import creer_app

HOTE = "pc.tail1234.ts.net"
ID = {"Tailscale-User-Login": "moi@example.com"}


@pytest.fixture
def app(centre, verrou):
    centre.config.hotes_autorises = (HOTE,)
    centre.config.utilisateurs_tailscale = ("moi@example.com",)
    return creer_app(centre, verrou)


def telephone(app, **entetes):
    c = TestClient(app, base_url="https://" + HOTE, follow_redirects=False)
    c.headers["X-Centre"] = "1"
    c.headers.update(ID)
    c.headers.update(entetes)
    return c


def connecte(app):
    c = telephone(app)
    r = c.post("/api/connexion", json={"nip": NIP, "secret": SECRET}, headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200
    return c


# ----- identité Tailscale exigée pour tout accès distant -----------------------------------------------------------

def test_sans_identite_tailscale_tout_est_refuse(app):
    """Un « funnel » (Internet public) ou une redirection de port n'apporte pas l'en-tête d'identité : refus, même de la page de connexion."""
    c = TestClient(app, base_url="https://" + HOTE, follow_redirects=False)
    c.headers["X-Centre"] = "1"
    for chemin in ("/connexion", "/api/verrou", "/manifest.webmanifest", "/", "/s/style.css"):
        assert c.get(chemin).status_code == 403, chemin
    assert c.post("/api/connexion", json={"nip": NIP, "secret": SECRET}).status_code == 403


def test_mauvais_utilisateur_tailscale_refuse(app):
    c = telephone(app, **{"Tailscale-User-Login": "intrus@example.com"})
    assert c.get("/connexion").status_code == 403
    assert telephone(app, **{"Tailscale-User-Login": "MOI@Example.com"}).get("/connexion").status_code == 200   # casse ignorée


def test_identite_non_exigee_si_desactive(centre, verrou):
    centre.config.hotes_autorises = (HOTE,)
    centre.config.exiger_identite_tailscale = False
    c = TestClient(creer_app(centre, verrou), base_url="https://" + HOTE)
    assert c.get("/connexion").status_code == 200


def test_acces_local_jamais_concerne_par_l_identite(client):
    assert client.get("/api/etat").status_code == 200


def test_hote_inconnu_reste_refuse(app):
    c = TestClient(app, base_url="https://autre.ts.net")
    c.headers.update(ID)
    assert c.get("/connexion").status_code == 421


def test_websocket_distante_exige_aussi_l_identite(app, simulateur):
    simulateur.cles["OPENAI_API_KEY"] = "sk-openai-secret-000000"
    c = connecte(app)
    jeton = c.cookies.get("centre_session")
    base = {"Origin": "https://" + HOTE, "Host": HOTE, "Cookie": "centre_session=" + jeton}
    sans_identite = TestClient(app, base_url="https://" + HOTE)
    with pytest.raises(WebSocketDisconnect):                       # cookie valide mais sans l'identité Tailscale
        with sans_identite.websocket_connect("/ws/voix", headers=base):
            pass
    with c.websocket_connect("/ws/voix", headers={**base, **ID}) as ws:
        ws.send_json({"t": "couper"})


# ----- HTTPS : cookie, HSTS, en-têtes ----------------------------------------------------------------------------------

def test_cookie_secure_hsts_et_entetes(app):
    c = telephone(app)
    r = c.post("/api/connexion", json={"nip": NIP, "secret": SECRET}, headers={"X-Forwarded-Proto": "https"})
    cookie = r.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert r.headers["strict-transport-security"].startswith("max-age=")
    r2 = c.get("/api/etat")
    assert r2.headers["strict-transport-security"] and "microphone=(self)" in r2.headers["permissions-policy"]
    assert r2.headers["cross-origin-opener-policy"] == "same-origin"


def test_pas_de_hsts_en_local(client):
    assert "strict-transport-security" not in client.get("/api/etat").headers


# ----- NIP confirmé pour les actions sensibles depuis un appareil distant ---------------------------------------------------

SENSIBLES = [("POST", "/api/action", {"sens": "mode_jeu"}), ("PUT", "/api/crew/mode", {"mode": "maxperf"}),
             ("POST", "/api/ouvrir", {"ident": "docker"}), ("PUT", "/api/couts/plafonds", {"jour": 1}),
             ("PUT", "/api/couts/tarifs", {"salle": "deepseek", "entree": 1, "sortie": 1}),
             ("POST", "/api/conversations/0123456789abcdef/approbation", {"decisions": {}}),
             ("PUT", "/api/salles/deepseek/reglage", {"modele": "x"}), ("PUT", "/api/tiroir/abc", {"zone": "partageable"}),
             ("DELETE", "/api/conversations/0123456789abcdef", None), ("POST", "/api/securite/deconnecter-autres", {})]


@pytest.mark.parametrize("methode,chemin,corps", SENSIBLES)
def test_actions_sensibles_exigent_le_nip_a_distance(app, methode, chemin, corps):
    c = connecte(app)
    r = c.request(methode, chemin, json=corps)
    assert r.status_code == 403 and r.json()["nip_requis"] is True


@pytest.mark.parametrize("methode,chemin,corps", SENSIBLES)
def test_les_memes_actions_ne_demandent_pas_de_nip_en_local(client, methode, chemin, corps):
    r = client.request(methode, chemin, json=corps)
    assert not (r.status_code == 403 and r.json().get("nip_requis"))


def test_confirmer_le_nip_puis_agir(app, centre, horloge):
    c = connecte(app)
    assert c.put("/api/couts/plafonds", json={"jour": 1}).status_code == 403
    assert c.post("/api/confirmer-nip", json={"nip": "000000"}).status_code == 401
    assert c.put("/api/couts/plafonds", json={"jour": 1}).status_code == 403
    r = c.post("/api/confirmer-nip", json={"nip": NIP})
    assert r.status_code == 200 and r.json()["duree"] == 300
    assert c.put("/api/couts/plafonds", json={"jour": 1}).status_code == 200
    assert c.get("/api/securite").json()["nip_confirme"] is True
    horloge.t += 301                                               # expire au bout de 5 minutes
    assert c.put("/api/couts/plafonds", json={"jour": 1}).status_code == 403
    actions = [r["action"] for r in centre.recus.derniers()]
    assert "confirmation_nip" in actions and "nip_requis" in actions


def test_nip_confirme_par_session(app):
    a, b = connecte(app), connecte(app)
    assert a.post("/api/confirmer-nip", json={"nip": NIP}).status_code == 200
    assert a.put("/api/couts/plafonds", json={"jour": 1}).status_code == 200
    assert b.put("/api/couts/plafonds", json={"jour": 1}).status_code == 403


def test_les_faux_nip_comptent_pour_le_blocage(app):
    c = connecte(app)
    for _ in range(5):
        assert c.post("/api/confirmer-nip", json={"nip": "111111"}).status_code == 401
    r = c.post("/api/confirmer-nip", json={"nip": NIP})              # même le bon est refusé pendant l'attente
    assert r.status_code == 429 and r.json()["attente"] > 0


def test_confirmer_nip_exige_une_session(app):
    assert telephone(app).post("/api/confirmer-nip", json={"nip": NIP}).status_code == 401


def test_une_session_locale_n_a_pas_besoin_du_nip(client):
    assert client.put("/api/couts/plafonds", json={"jour": 1}).status_code == 200


# ----- appareils connectés ---------------------------------------------------------------------------------------------------------

def test_appareils_connectes_et_deconnexion_des_autres(app, client, centre):
    tel = connecte(app)
    tel.headers["User-Agent"] = "iPhone Safari"
    d = client.get("/api/securite").json()
    assert d["distant"] is False and len(d["sessions"]) == 2
    assert sum(1 for s in d["sessions"] if s["courante"]) == 1 and any(s["distant"] for s in d["sessions"])
    assert d["identite_exigee"] is True and d["hotes_autorises"] == [HOTE]
    n = client.post("/api/securite/deconnecter-autres").json()["fermees"]
    assert n == 1
    assert client.get("/api/etat").status_code == 200          # la session courante reste
    assert tel.get("/api/etat").status_code == 401             # le téléphone est déconnecté
    assert any(r["action"] == "deconnexion_des_autres" for r in centre.recus.derniers())


def test_agent_utilisateur_tronque_et_texte(app, client):
    c = telephone(app, **{"User-Agent": "X" * 500})
    c.post("/api/connexion", json={"nip": NIP, "secret": SECRET})
    assert all(len(s["agent"]) <= 120 for s in client.get("/api/securite").json()["sessions"] if s)


def test_routes_securite_exigent_une_session(anonyme):
    assert anonyme.get("/api/securite").status_code == 401
    assert anonyme.post("/api/securite/deconnecter-autres").status_code == 401


# ----- réglages.json -------------------------------------------------------------------------------------------------------------------

def test_reglages_json_alimente_hotes_et_identite(tmp_path):
    from centre.config import Config
    d = tmp_path / "d"; d.mkdir()
    (d / "reglages.json").write_text(json.dumps({"hotes_autorises": ["PC.tail1234.ts.net"], "utilisateurs_tailscale": ["Moi@Example.com"],
                                                 "exiger_identite_tailscale": True}), encoding="utf-8-sig")
    c = Config(dossier_donnees=str(d))
    assert "pc.tail1234.ts.net" in c.hotes_autorises and c.utilisateurs_tailscale == ("moi@example.com",)
    (d / "reglages.json").write_text("{pas du json", encoding="utf-8")
    assert Config(dossier_donnees=str(d)).utilisateurs_tailscale == ()


def test_csp_nomme_l_hote_pour_les_websockets(app, client):
    csp = telephone(app).get("/connexion").headers["content-security-policy"]
    assert f"connect-src 'self' wss://{HOTE};" in csp and "unsafe" not in csp
    assert "connect-src 'self' ws://127.0.0.1:8740;" in client.get("/api/etat").headers["content-security-policy"]
