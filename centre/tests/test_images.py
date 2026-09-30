# -*- coding: utf-8 -*-
"""Génération d'images : OpenAI, Gemini, xAI, ComfyUI local. Faux réseau : aucun vrai moteur, aucune vraie clé."""

import base64
import json
import os

import pytest

from test_pieces import png
from test_salles import allumer, mode
from centre.images import ErreurImage

URL_OPENAI = "https://api.openai.com/v1/images/generations"
URL_XAI = "https://api.x.ai/v1/images/generations"
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
COMFY = "http://127.0.0.1:8188"
SECRET = "sk-secret-image-ne-pas-afficher"


def b64(o=None):
    return base64.b64encode(o or png()).decode()


class Moteurs:
    """Faux moteurs : enregistre les appels et répond comme les vrais (corps JSON)."""

    def __init__(self, reseau):
        self.appels = []
        self.comfy = True
        self.erreur = {}           # url -> (code, texte)
        self.contenu = {}          # url -> octets à renvoyer à la place du PNG
        reseau.requete = self.requete

    def requete(self, methode, url, entetes=None, corps=None, delai=30, octets=False, max_octets=0):
        self.appels.append((methode, url, corps, dict(entetes or {})))
        if url in self.erreur:
            return self.erreur[url]
        img = self.contenu.get(url, png())
        if url in (URL_OPENAI, URL_XAI):
            return 200, json.dumps({"data": [{"b64_json": b64(img)}]})
        if url == URL_GEMINI:
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}, {"inlineData": {"mimeType": "image/png", "data": b64(img)}}]}}]})
        if url.startswith(COMFY):
            if not self.comfy:
                return None, "connexion refusée"
            if url.endswith("/system_stats"):
                return 200, "{}"
            if url.endswith("/object_info/CheckpointLoaderSimple"):
                return 200, json.dumps({"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["sdxl.safetensors", "sd15.safetensors"]]}}}})
            if url.endswith("/prompt"):
                return 200, json.dumps({"prompt_id": "abc123"})
            if "/history/" in url:
                return 200, json.dumps({"abc123": {"outputs": {"7": {"images": [{"filename": "centre_0001_.png", "subfolder": "", "type": "output"}]}}}})
            if "/view?" in url:
                return 200, (self.contenu.get("view", png()) if octets else "")
        return None, "connexion refusée"


@pytest.fixture
def moteurs(reseau, centre, simulateur):
    m = Moteurs(reseau)
    allumer(centre, simulateur)
    simulateur.cles.update({"OPENAI_API_KEY": SECRET, "GEMINI_API_KEY": SECRET + "g", "XAI_API_KEY": SECRET + "x"})
    return m


def creer(centre, moteur, **kw):
    kw.setdefault("prompt", "un chat astronaute")
    j = centre.images.lancer(moteur, **kw)
    return centre.images.attendre(j["id"])


# ----- options et estimation ---------------------------------------------------------------------------------------------

def test_options_disponibilites(centre, simulateur, reseau):
    m = Moteurs(reseau)
    allumer(centre, simulateur)
    o = {x["id"]: x for x in centre.images.options()["moteurs"]}
    assert set(o) == {"openai", "gemini", "xai", "local"} and o["local"]["disponible"] and not o["local"]["nuage"]
    assert not o["openai"]["disponible"] and "OPENAI_API_KEY" in o["openai"]["raison"]
    simulateur.cles["OPENAI_API_KEY"] = SECRET
    o = centre.images.options()
    assert {x["id"]: x for x in o["moteurs"]}["openai"]["disponible"] and o["checkpoints"] == ["sdxl.safetensors", "sd15.safetensors"]
    m.comfy = False
    assert "ComfyUI ne répond pas" in {x["id"]: x for x in centre.images.options()["moteurs"]}["local"]["raison"]


def test_mode_local_ferme_le_nuage_mais_pas_comfyui(centre, simulateur, reseau, moteurs):
    for mo in ("confidentiel", "ultra-confidentiel", "ultra"):
        mode(simulateur, centre, mo)
        o = {x["id"]: x for x in centre.images.options()["moteurs"]}
        assert o["local"]["disponible"] and not o["openai"]["disponible"] and "rien ne doit quitter le PC" in o["openai"]["raison"]
        with pytest.raises(ErreurImage) as e:
            centre.images.lancer("openai", "un chat")
        assert e.value.code == 403
    assert not [a for a in moteurs.appels if a[1] == URL_OPENAI]


def test_estimation_et_seuil(centre, moteurs):
    e = centre.images.estimer("openai", 3)
    assert e["usd"] == pytest.approx(0.126) and e["depasse"] and e["fiable"] is False and "estimation indicative" in e["texte"]
    assert centre.images.estimer("local", 4)["usd"] == 0 and centre.images.estimer("local", 4)["texte"] == "Gratuit (local)"
    assert centre.images.estimer("gemini", 99)["n"] == 4
    centre.config.seuil_image_usd = 1.0
    assert not centre.images.estimer("openai", 4)["depasse"]
    with pytest.raises(ErreurImage):
        centre.images.estimer("inconnu")


def test_seuil_lu_dans_reglages_json(tmp_path):
    from centre.config import Config
    d = tmp_path / "d"; d.mkdir()
    (d / "reglages.json").write_text('{"seuil_image_usd": 0.5}', encoding="utf-8")
    assert Config(dossier_donnees=str(d)).seuil_image_usd == 0.5
    (d / "reglages.json").write_text('{"seuil_image_usd": -2}', encoding="utf-8")
    assert Config(dossier_donnees=str(d)).seuil_image_usd == 0.10


# ----- génération --------------------------------------------------------------------------------------------------------------

def test_openai(centre, moteurs):
    j = creer(centre, "openai", taille="portrait")
    assert j["etat"] == "termine" and j["fait"] == 1 and len(j["images"]) == 1
    _, url, corps, entetes = [a for a in moteurs.appels if a[1] == URL_OPENAI][0]
    assert corps == {"model": "gpt-image-1", "prompt": "un chat astronaute", "n": 1, "size": "1024x1536"} and entetes["Authorization"] == "Bearer " + SECRET
    octets, mime = centre.images.lire(j["images"][0]["id"])
    assert mime == "image/png" and octets == png()
    g = centre.images.lister()[0]
    assert g["prompt"] == "un chat astronaute" and g["moteur"] == "openai" and g["prive"] is False and g["cout_usd"] == 0.042


def test_gemini_cle_dans_l_en_tete_pas_dans_l_adresse(centre, moteurs):
    j = creer(centre, "gemini")
    assert j["etat"] == "termine"
    _, url, corps, entetes = [a for a in moteurs.appels if a[1].startswith("https://generativelanguage")][0]
    assert "key=" not in url and SECRET not in url and entetes["x-goog-api-key"] == SECRET + "g"
    assert corps["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]


def test_xai(centre, moteurs):
    j = creer(centre, "xai")
    assert j["etat"] == "termine"
    corps = [a for a in moteurs.appels if a[1] == URL_XAI][0][2]
    assert corps == {"model": "grok-2-image", "prompt": "un chat astronaute", "n": 1, "response_format": "b64_json"}


def test_plusieurs_images_un_appel_par_image_et_cout_compte(centre, moteurs):
    j = creer(centre, "openai", n=3, confirme_depassement=True)
    assert j["fait"] == 3 and len([a for a in moteurs.appels if a[1] == URL_OPENAI]) == 3
    t = centre.couts.totaux()["aujourdhui"]
    assert t["par_ia"]["images"] == pytest.approx(0.126, abs=1e-4)
    assert json.loads(open(centre.config.chemin("depenses.jsonl")).read().splitlines()[0])["estime"] is True


def test_local_comfyui(centre, moteurs):
    j = creer(centre, "local", n=2, taille="paysage", checkpoint="sd15.safetensors")
    assert j["etat"] == "termine" and j["fait"] == 2
    graphe = [a for a in moteurs.appels if a[1] == COMFY + "/prompt"][0][2]["prompt"]
    assert graphe["1"]["inputs"]["ckpt_name"] == "sd15.safetensors" and graphe["2"]["inputs"]["text"] == "un chat astronaute"
    assert (graphe["4"]["inputs"]["width"], graphe["4"]["inputs"]["height"]) == (960, 640)
    assert centre.couts.totaux()["aujourdhui"]["total"] == 0                              # gratuit
    assert not [a for a in moteurs.appels if a[1].startswith("https://")]                 # rien n'est sorti du PC


def test_checkpoint_inconnu_remplace_par_le_premier(centre, moteurs):
    creer(centre, "local", checkpoint="../../etc/passwd")
    assert [a for a in moteurs.appels if a[1] == COMFY + "/prompt"][0][2]["prompt"]["1"]["inputs"]["ckpt_name"] == "sdxl.safetensors"


# ----- confidentialité, coûts, erreurs -------------------------------------------------------------------------------------------------

def test_contenu_confidentiel_refuse_le_nuage_accepte_le_local(centre, moteurs):
    for nuage in ("openai", "gemini", "xai"):
        with pytest.raises(ErreurImage) as e:
            centre.images.lancer(nuage, "plan secret du client", prive=True)
        assert e.value.code == 403 and "confidentiel" in str(e.value).lower()
    assert not [a for a in moteurs.appels if a[1].startswith("https://")]
    j = creer(centre, "local", prompt="plan secret du client", prive=True)
    assert j["etat"] == "termine" and centre.images.lister()[0]["prive"] is True


def test_depassement_du_seuil_demande_confirmation(centre, moteurs):
    with pytest.raises(ErreurImage) as e:
        centre.images.lancer("xai", "x", n=4)                                              # 0,28 $ > 0,10 $
    assert e.value.code == 402 and e.value.extra == {"depassement": True} and "seuil" in str(e.value)
    assert not [a for a in moteurs.appels if a[1] == URL_XAI]
    assert creer(centre, "xai", n=4, confirme_depassement=True)["fait"] == 4


def test_plafond_atteint(centre, moteurs):
    centre.couts.definir_plafonds(0.01, None)
    centre.couts.enregistrer("deepseek", 1)
    with pytest.raises(ErreurImage) as e:
        centre.images.lancer("openai", "x")
    assert e.value.code == 403 and "plafond" in str(e.value)


def test_erreur_http_sans_fuite_de_cle(centre, moteurs):
    moteurs.erreur[URL_OPENAI] = (401, json.dumps({"error": {"message": f"Incorrect API key {SECRET}"}}))
    j = creer(centre, "openai")
    assert j["etat"] == "erreur" and "refusée" in j["message"] and SECRET not in j["message"] and j["images"] == []
    assert centre.couts.totaux()["aujourdhui"]["total"] == 0                                # rien de facturé
    assert SECRET not in open(centre.config.chemin("recus.jsonl")).read()


@pytest.mark.parametrize("contenu", [b"<svg onload=alert(1)>", b"MZ\x90\x00", b"GIF89a...."])
def test_contenu_recu_verifie_sur_les_octets(centre, moteurs, contenu):
    moteurs.contenu[URL_OPENAI] = contenu
    j = creer(centre, "openai")
    assert j["etat"] == "erreur" and "image valide" in j["message"] and centre.images.lister() == []


def test_reponse_illisible(centre, moteurs):
    moteurs.erreur[URL_XAI] = (200, "pas du json")
    assert "illisible" in creer(centre, "xai")["message"]
    moteurs.erreur[URL_GEMINI] = (200, json.dumps({"candidates": [{"content": {"parts": [{"text": "désolé, je ne peux pas"}]}}]}))
    assert "illisible" in creer(centre, "gemini")["message"]


def test_une_seule_creation_a_la_fois(centre, moteurs, reseau):
    import threading
    porte = threading.Event()
    vrai = reseau.requete
    def lent(*a, **k):
        porte.wait(5)
        return vrai(*a, **k)
    reseau.requete = lent
    j = centre.images.lancer("openai", "première")
    with pytest.raises(ErreurImage) as e:
        centre.images.lancer("openai", "seconde")
    assert e.value.code == 409
    porte.set()
    assert centre.images.attendre(j["id"])["etat"] == "termine"


@pytest.mark.parametrize("kw", [{"prompt": ""}, {"prompt": "  "}, {"prompt": "x" * 4001}, {"taille": "énorme"}, {"n": 0}, {"n": 5}, {"n": True}, {"n": "2"}])
def test_demandes_invalides(centre, moteurs, kw):
    with pytest.raises(ErreurImage) as e:
        centre.images.lancer("openai", **dict({"prompt": "ok"}, **kw))
    assert e.value.code == 400


def test_le_texte_de_la_demande_n_est_ni_dans_les_recus_ni_dans_le_journal(centre, moteurs, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    creer(centre, "openai", prompt="mot-secret-unique-7777")
    assert "mot-secret-unique-7777" not in open(centre.config.chemin("recus.jsonl")).read() and "mot-secret-unique-7777" not in caplog.text
    assert "mot-secret-unique-7777" in centre.images.lister()[0]["prompt"]                   # seulement dans la galerie, sur le PC


# ----- galerie et API --------------------------------------------------------------------------------------------------------------

def test_api_creer_suivre_voir_telecharger_supprimer(client, centre, moteurs):
    o = client.get("/api/images/options").json()
    assert o["defaut"] and o["tailles"][0]["id"] == "carre" and o["max_images"] == 4
    e = client.post("/api/images/estimation", json={"moteur": "openai", "n": 2}).json()
    assert e["usd"] == pytest.approx(0.084)
    r = client.post("/api/images", json={"moteur": "openai", "prompt": "un phare la nuit", "taille": "carre", "n": 1})
    assert r.status_code == 202
    job = centre.images.attendre(r.json()["id"])
    assert client.get(f"/api/images/jobs/{job['id']}").json()["etat"] == "termine"
    liste = client.get("/api/images").json()["images"]
    assert liste[0]["prompt"] == "un phare la nuit"
    ident = liste[0]["id"]
    f = client.get(f"/api/images/{ident}/fichier")
    assert f.status_code == 200 and f.headers["content-type"] == "image/png" and f.content == png() and f.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in client.get(f"/api/images/{ident}/fichier?telecharger=1").headers["content-disposition"]
    assert client.delete(f"/api/images/{ident}").status_code == 200
    assert client.get(f"/api/images/{ident}/fichier").status_code == 404 and client.get("/api/images").json()["images"] == []


def test_api_erreurs(client, centre, moteurs):
    r = client.post("/api/images", json={"moteur": "xai", "prompt": "x", "n": 4})
    assert r.status_code == 402 and r.json()["depassement"] is True
    r = client.post("/api/images", json={"moteur": "openai", "prompt": "x", "prive": True})
    assert r.status_code == 403
    assert client.get("/api/images/jobs/zzzz").status_code == 404
    for ident in ("../verrou", "0123456789abcdef", "ZZ", "a" * 16 + "%2f.."):
        assert client.get(f"/api/images/{ident}/fichier").status_code in (404, 400)
        assert client.delete(f"/api/images/{ident}").status_code in (404, 400, 405)


def test_api_session_requise(anonyme):
    for methode, chemin in (("GET", "/api/images/options"), ("GET", "/api/images"), ("POST", "/api/images"), ("GET", "/api/images/0123456789abcdef/fichier"),
                            ("DELETE", "/api/images/0123456789abcdef"), ("GET", "/api/images/jobs/abc"), ("POST", "/api/images/estimation")):
        assert anonyme.request(methode, chemin, json={} if methode == "POST" else None).status_code == 401


def test_galerie_pleine_et_fichiers_etrangers_ignores(centre, moteurs, monkeypatch):
    os.makedirs(centre.images.dossier, exist_ok=True)
    open(os.path.join(centre.images.dossier, "intrus.json"), "w").write("{}")
    open(os.path.join(centre.images.dossier, "0123456789abcdef.json"), "w").write('{"id": "autre"}')
    assert centre.images.lister() == []
    monkeypatch.setattr("centre.images.MAX_GALERIE", 1)
    creer(centre, "local")
    j = creer(centre, "local")
    assert j["etat"] == "erreur" and "Galerie pleine" in j["message"]
