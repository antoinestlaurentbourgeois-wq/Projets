# -*- coding: utf-8 -*-
"""Images collées dans une conversation : stockage sûr, envoi aux seules salles qui lisent les images, jamais aux autres."""

import base64
import json
import os
import struct
import zlib

import pytest

from conftest import sse
from test_salles import allumer, envoyer, texte, types
from centre.pieces import Pieces, ErreurPiece, type_reel

URL_GEMMA = "http://127.0.0.1:1234/v1/chat/completions"


def png(n=4, couleur=(200, 30, 30)):
    """Petit PNG valide (n × n pixels)."""
    def bloc(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    brut = b"".join(b"\x00" + bytes(couleur) * n for _ in range(n))
    return b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0)) + bloc(b"IDAT", zlib.compress(brut)) + bloc(b"IEND", b"")


def b64(octets):
    return base64.b64encode(octets).decode()


# ----- stockage -----------------------------------------------------------------------------------------------------

def test_type_reel_d_apres_le_contenu():
    assert type_reel(png()) == "png" and type_reel(b"\xff\xd8\xff\xe0abc") == "jpg" and type_reel(b"RIFF\x00\x00\x00\x00WEBPxx") == "webp"
    assert type_reel(b"GIF89a....") == "gif" and type_reel(b"<svg onload=alert(1)>") is None and type_reel(b"MZ\x90\x00") is None


def test_ajout_lecture_suppression(tmp_path):
    p = Pieces(str(tmp_path / "pieces"))
    e = p.ajouter_base64(b64(png()), "capture d'écran ../../x.png")
    assert len(e["id"]) == 16 and e["type"] == "image/png" and "/" not in e["nom"] and ".." not in e["nom"].replace("...", "")
    octets, mime = p.lire(e["id"])
    assert mime == "image/png" and octets == png() and p.data_url(e["id"]).startswith("data:image/png;base64,")
    assert sorted(os.listdir(tmp_path / "pieces")) == [e["id"] + ".png"]          # nom du fichier = identifiant aléatoire seulement
    assert p.supprimer(e["id"]) and not p.existe(e["id"])


@pytest.mark.parametrize("mauvais,code", [("", 400), ("pas du base64 !!", 400), (b64(b"<svg/>"), 415), (b64(b"MZ" + b"\0" * 50), 415), (b64(png(2) + b"0" * 7_000_000), 413)],
                         ids=["vide", "pas-base64", "svg", "executable", "trop-lourd"])
def test_refus(tmp_path, mauvais, code):
    with pytest.raises(ErreurPiece) as e:
        Pieces(str(tmp_path)).ajouter_base64(mauvais)
    assert e.value.code == code


@pytest.mark.parametrize("ident", ["../etc/passwd", "a" * 16 + "/../x", "ZZZZZZZZZZZZZZZZ", "", None, 5, "abcd"])
def test_identifiant_invalide_jamais_un_chemin(tmp_path, ident):
    p = Pieces(str(tmp_path))
    with pytest.raises(ErreurPiece) as e:
        p.lire(ident)
    assert e.value.code == 404
    assert p.supprimer(ident) is False


def test_nettoyage_des_images_orphelines(tmp_path):
    p = Pieces(str(tmp_path))
    a, b = p.ajouter(png())["id"], p.ajouter(png(3))["id"]
    assert p.nettoyer({a}, age_min=-1) == 1 and p.existe(a) and not p.existe(b)


# ----- routes -------------------------------------------------------------------------------------------------------

def test_api_televerser_lire_supprimer(client):
    r = client.post("/api/pieces", json={"nom": "photo.png", "donnees": b64(png())})
    assert r.status_code == 201
    e = r.json()
    g = client.get(f"/api/pieces/{e['id']}")
    assert g.status_code == 200 and g.headers["content-type"] == "image/png" and g.content == png() and g.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/pieces/0123456789abcdef").status_code == 404
    assert client.get("/api/pieces/..%2f..%2fverrou.json").status_code in (404, 400)
    assert client.post("/api/pieces", json={"donnees": b64(b"<html>")}).status_code == 415
    assert client.delete(f"/api/pieces/{e['id']}").status_code == 200 and client.get(f"/api/pieces/{e['id']}").status_code == 404


def test_api_session_requise(anonyme):
    assert anonyme.post("/api/pieces", json={"donnees": b64(png())}).status_code == 401
    assert anonyme.get("/api/pieces/0123456789abcdef").status_code == 401


# ----- envoi dans une conversation ---------------------------------------------------------------------------------------

def televerser(centre, octets=None):
    return centre.salles.pieces.ajouter(octets or png(), "capture.png")["id"]


def test_salle_locale_recoit_l_image_au_format_openai(centre, simulateur, reseau):
    allumer(centre, simulateur)
    reseau.repondre(URL_GEMMA, lambda c, e: sse("Je vois un carré rouge."))
    pid = televerser(centre)
    evts, conv = envoyer(centre, "gemma", "Que vois-tu ?", images=[pid], noms_images={pid: "capture.png"})
    assert texte(evts) == "Je vois un carré rouge."
    corps = [a for a in reseau.appels if a[1] == URL_GEMMA][-1][2]
    contenu = corps["messages"][-1]["content"]
    assert isinstance(contenu, list) and contenu[0] == {"type": "text", "text": "Que vois-tu ?"}
    assert contenu[1]["type"] == "image_url" and contenu[1]["image_url"]["url"].startswith("data:image/png;base64,")
    m = conv["messages"][0]
    assert m["pieces"] == [{"id": pid, "type": "image/png", "nom": "capture.png"}]                 # l'historique garde une référence, pas les octets
    assert "base64" not in json.dumps(conv)


def test_les_anciennes_images_ne_sont_pas_renvoyees(centre, simulateur, reseau):
    allumer(centre, simulateur)
    reseau.repondre(URL_GEMMA, lambda c, e: sse("ok"))
    pid = televerser(centre)
    _, conv = envoyer(centre, "gemma", "première", images=[pid])
    centre.salles.demarrer_envoi(conv["id"], "suite sans image", {}).attendre()
    corps = [a for a in reseau.appels if a[1] == URL_GEMMA][-1][2]
    assert all(isinstance(m["content"], str) for m in corps["messages"]) and any("[image jointe : image]" in m["content"] for m in corps["messages"])
    assert "base64" not in json.dumps(corps)


@pytest.mark.parametrize("salle", ["deepseek", "crew", "claude"])
def test_salles_qui_ne_lisent_pas_les_images_les_refusent_sans_rien_envoyer(centre, simulateur, reseau, salle):
    allumer(centre, simulateur)
    pid = televerser(centre)
    evts, _ = envoyer(centre, salle, "regarde", images=[pid])
    assert types(evts) == ["erreur"] and "image" in evts[0]["message"].lower()
    assert not [a for a in reseau.appels if a[0] == "POST"]


def test_chatgpt_et_gemini_par_programme_refusent_mais_par_cle_acceptent(centre, simulateur):
    s = centre.salles
    assert s.lit_images("chatgpt")[0] is False and s.lit_images("gemini")[0] is True        # Codex (abonnement) : non ; Gemini par défaut : clé API, oui
    s.definir_reglage("gemini", auth="abonnement")
    assert s.lit_images("gemini")[0] is False
    s.definir_reglage("chatgpt", auth="cle")
    assert s.lit_images("chatgpt")[0] is True and s.lit_images("grok")[0] is True
    cat = {x["id"]: x for x in s.catalogue()}
    assert cat["gemma"]["images"] is True and cat["deepseek"]["images"] is False and "texte" in cat["deepseek"]["raison_images"]


def test_image_refusee_vers_le_nuage_si_conversation_privee(centre, simulateur, reseau):
    allumer(centre, simulateur)
    simulateur.cles["XAI_API_KEY"] = "xai-aaaaaaaaaaaa"
    pid = televerser(centre)
    conv = centre.salles.creer_conversation("grok")
    conv["prive"] = True
    centre.salles.conversations.enregistrer(conv)
    evts = centre.salles.demarrer_envoi(conv["id"], "q", {"images": [pid]}).attendre()
    assert types(evts) == ["erreur"] and not [a for a in reseau.appels if "x.ai" in a[1]]


def test_image_inconnue_et_limite_de_4(centre, simulateur, reseau):
    allumer(centre, simulateur)
    reseau.repondre(URL_GEMMA, lambda c, e: sse("ok"))
    evts, _ = envoyer(centre, "gemma", "q", images=["0123456789abcdef"])
    assert types(evts) == ["erreur"] and "introuvable" in evts[0]["message"]
    ids = [televerser(centre, png(2 + i)) for i in range(6)]
    evts, conv = envoyer(centre, "gemma", "q", images=ids)
    assert len(conv["messages"][0]["pieces"]) == 4


def test_pas_d_image_en_table_ronde(centre, simulateur, reseau):
    allumer(centre, simulateur)
    pid = televerser(centre)
    evts, _ = envoyer(centre, "crew", "q", images=[pid], table_ronde={"participants": ["gemma"], "critique": False, "synthese": True})
    assert types(evts) == ["erreur"] and "table ronde" in evts[0]["message"].lower()


def test_supprimer_la_conversation_supprime_ses_images(centre, simulateur, reseau):
    allumer(centre, simulateur)
    reseau.repondre(URL_GEMMA, lambda c, e: sse("ok"))
    pid = televerser(centre)
    _, conv = envoyer(centre, "gemma", "q", images=[pid])
    assert centre.salles.pieces.existe(pid)
    centre.salles.supprimer_conversation(conv["id"])
    assert not centre.salles.pieces.existe(pid)


def test_api_message_avec_images(client, centre, simulateur, reseau):
    allumer(centre, simulateur)
    reseau.repondre(URL_GEMMA, lambda c, e: sse("vu"))
    pid = client.post("/api/pieces", json={"nom": "a.png", "donnees": b64(png())}).json()["id"]
    c = client.post("/api/conversations", json={"salle": "gemma"}).json()
    r = client.post(f"/api/conversations/{c['id']}/messages", json={"texte": "et ça ?", "images": [pid], "noms_images": {pid: "a.png"}})
    assert '"vu"' in r.text or "vu" in r.text
    m = client.get(f"/api/conversations/{c['id']}").json()["messages"][0]
    assert m["pieces"][0]["id"] == pid
