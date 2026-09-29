# -*- coding: utf-8 -*-
"""Phase 3 : voix. Aucun vrai service vocal : le fournisseur est simulé par une fausse WebSocket."""

import json
import threading
import time

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import NIP, SECRET, sse
from centre import voix as V
from centre.app import creer_app

ORIGINE = "http://127.0.0.1:8740"
URL_STT = "https://api.openai.com/v1/audio/transcriptions"
URL_TTS = "https://api.openai.com/v1/audio/speech"


def cles(simulateur):
    simulateur.cles.update({"OPENAI_API_KEY": "sk-openai-secret-000000", "XAI_API_KEY": "xai-secret-0000000000"})


def mode(simulateur, centre, m):
    simulateur.fichiers[centre.L.R.FICHIER_MODE_CREW] = json.dumps({"mode": m})
    centre.salles.politique.oublier()


def recevoir(ws, t, maxi=40):
    """Lit jusqu'à un message du type demandé (renvoie aussi ce qui a été passé)."""
    vus = []
    for _ in range(maxi):
        m = ws.receive_json()
        vus.append(m)
        if m["t"] == t:
            return m, vus
    raise AssertionError(f"pas de message « {t} » ; reçu : {[v['t'] for v in vus]}")


def attendre(condition, delai=5):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.01)
    return False


def entetes_ws(client, **extra):
    """Le client de test n'envoie ni l'hôte ni le cookie tout seul en WebSocket : on les fournit."""
    h = {"Origin": ORIGINE, "Host": "127.0.0.1:8740"}
    jeton = client.cookies.get("centre_session")
    if jeton:
        h["Cookie"] = "centre_session=" + jeton
    h.update(extra)
    return h


def ouvrir(client, **params):
    return client.websocket_connect("/ws/voix", headers=entetes_ws(client))


# ----- calculs de coût -----------------------------------------------------------------------------

def test_cout_usage_mini():
    usage = {"input_tokens": 1000, "output_tokens": 500, "input_token_details": {"audio_tokens": 800, "text_tokens": 200},
             "output_token_details": {"audio_tokens": 400, "text_tokens": 100}}
    assert V.cout_usage("gpt-realtime-mini", usage) == pytest.approx((800 * 10 + 400 * 20 + 200 * 0.6 + 100 * 2.4) / 1e6)
    assert V.cout_usage("gpt-realtime-2", usage) == pytest.approx((800 * 32 + 400 * 64 + 200 * 4 + 100 * 16) / 1e6)


def test_cout_usage_sans_detail_est_prudent():
    assert V.cout_usage("gpt-realtime-mini", {"input_tokens": 1000, "output_tokens": 1000}) == pytest.approx((1000 * 10 + 1000 * 20) / 1e6)
    assert V.cout_usage("gpt-realtime-mini", None) == 0 and V.cout_usage("inconnu", {"input_tokens": 5}) == 0
    assert V.cout_usage("grok-voice-think-fast", {"input_tokens": 5}) == 0        # facturé à la durée


def test_estimation_par_minute():
    assert V.estimation_par_minute("gpt-realtime-mini")[0] == pytest.approx(0.03)
    assert V.estimation_par_minute("gpt-realtime-2")[0] == pytest.approx(0.096)
    assert V.estimation_par_minute("grok-voice-think-fast")[0] == 0.08


def test_multipart():
    corps, type_ = V._multipart({"model": "m", "language": "fr"}, ("file", "a.webm", "audio/webm", b"\x00\x01DATA"))
    frontiere = type_.split("boundary=")[1].encode()
    assert corps.count(b"--" + frontiere) == 4 and b'name="model"\r\n\r\nm' in corps and b"\x00\x01DATA" in corps
    assert b'filename="a.webm"' in corps and corps.endswith(b"--" + frontiere + b"--\r\n")


# ----- options -------------------------------------------------------------------------------------------

def test_options(client, centre, simulateur):
    d = client.get("/api/voix/options").json()
    live = {m["id"]: m for m in d["live"]}
    assert set(live) == {"gpt-realtime-mini", "gpt-realtime-2", "grok-voice-think-fast"}
    assert live["gpt-realtime-mini"]["defaut"] and live["grok-voice-think-fast"]["par_minute_usd"] == 0.08
    assert not live["gpt-realtime-mini"]["disponible"] and "OPENAI_API_KEY" in live["gpt-realtime-mini"]["raison"]
    cles(simulateur)
    d = client.get("/api/voix/options").json()
    assert all(m["disponible"] for m in d["live"]) and d["disponible"] and d["restant_usd"] is None
    centre.couts.definir_plafonds(1, 5)
    centre.couts.enregistrer("deepseek", 0.25)
    assert client.get("/api/voix/options").json()["restant_usd"] == 0.75
    mode(simulateur, centre, "ultra")
    d = client.get("/api/voix/options").json()
    assert not d["disponible"] and "désactivée" in d["raison"] and not any(m["disponible"] for m in d["live"])


# ----- sécurité de la WebSocket ------------------------------------------------------------------------------

def test_websocket_exige_session_origine_et_hote(centre, verrou, simulateur):
    cles(simulateur)
    app = creer_app(centre, verrou)
    anonyme = TestClient(app, base_url=ORIGINE)
    with pytest.raises(WebSocketDisconnect):                       # pas de session
        with anonyme.websocket_connect("/ws/voix", headers=entetes_ws(anonyme)):
            pass
    c = TestClient(app, base_url=ORIGINE)
    c.headers["X-Centre"] = "1"
    assert c.post("/api/connexion", json={"nip": NIP, "secret": SECRET}).status_code == 200
    mauvais = [{"Origin": "https://evil.example"}, {"Origin": "http://127.0.0.1:9999"}, {"Origin": "null"},
               {"Origin": ""}, {"Host": "evil.example", "Origin": "http://evil.example"}, {"Host": "127.0.0.1:9999"}]
    for extra in mauvais:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws/voix", headers=entetes_ws(c, **extra)):
                pass
    with c.websocket_connect("/ws/voix", headers=entetes_ws(c)) as ws:       # tout en règle : accepté
        ws.send_json({"t": "couper"})


def test_premier_message_invalide_ferme(client):
    with pytest.raises(WebSocketDisconnect):
        with ouvrir(client) as ws:
            ws.send_json({"t": "audio", "pcm": "AAAA"})
            ws.receive_json()


# ----- session LIVE ----------------------------------------------------------------------------------------------

def demarrer(ws, **p):
    ws.send_json({"t": "demarrer", **p})
    return recevoir(ws, "pret")[0]


def test_live_session_complete(client, centre, simulateur, amont):
    cles(simulateur)
    with ouvrir(client) as ws:
        pret = demarrer(ws, modele="gpt-realtime-mini", voix="cedar")
        assert pret["modele"] == "gpt-realtime-mini" and pret["voix"] == "cedar" and "$" in pret["estimation"]
        conn = amont.connexions[0]
        assert conn.url == "wss://api.openai.com/v1/realtime?model=gpt-realtime-mini"
        assert conn.entetes["Authorization"] == "Bearer sk-openai-secret-000000"
        sess = conn.envoyes[0]
        assert sess["type"] == "session.update" and sess["session"]["audio"]["output"]["voice"] == "cedar"
        assert [t["name"] for t in sess["session"]["tools"]] == ["consulter_salle", "chercher_memoire"]
        assert "sk-openai-secret" not in json.dumps(conn.envoyes)
        # navigateur -> fournisseur
        ws.send_json({"t": "audio", "pcm": "QUJD"})
        assert attendre(lambda: "input_audio_buffer.append" in conn.types())
        assert [m for m in conn.envoyes if m["type"] == "input_audio_buffer.append"][0]["audio"] == "QUJD"
        # fournisseur -> navigateur
        conn.emettre({"type": "input_audio_buffer.speech_started"})
        assert recevoir(ws, "parole_debut")[0]
        conn.emettre({"type": "response.output_audio.delta", "delta": "REVG"})
        assert recevoir(ws, "audio")[0]["pcm"] == "REVG"
        conn.emettre({"type": "conversation.item.input_audio_transcription.completed", "transcript": "bonjour"})
        assert recevoir(ws, "transcription")[0]["texte"] == "bonjour"
        conn.emettre({"type": "response.audio_transcript.delta", "delta": "Salut"})          # ancien nom d'événement aussi
        assert recevoir(ws, "transcription")[0]["role"] == "assistant"
        # coût en direct
        conn.emettre({"type": "response.done", "response": {"usage": {
            "input_tokens": 1000, "output_tokens": 500, "input_token_details": {"audio_tokens": 800, "text_tokens": 200},
            "output_token_details": {"audio_tokens": 400, "text_tokens": 100}}, "output": []}})
        m, _ = recevoir(ws, "cout")
        assert m["usd"] == pytest.approx(0.0164, abs=1e-4)
        ws.send_json({"t": "couper"})
        fin, _ = recevoir(ws, "fin")
        assert fin["raison"] == "arret-utilisateur" and fin["cout_usd"] == pytest.approx(0.0164, abs=1e-4)
    assert conn.ferme
    assert centre.couts.totaux()["aujourdhui"]["par_ia"]["voix"] == pytest.approx(0.0164, abs=1e-4)
    assert any(r["action"] == "voix_live" for r in centre.recus.derniers())


def test_live_refuse_en_mode_confidentiel(client, centre, simulateur, amont):
    cles(simulateur)
    mode(simulateur, centre, "confidentiel")
    with ouvrir(client) as ws:
        ws.send_json({"t": "demarrer"})
        m, _ = recevoir(ws, "erreur")
        assert "désactivée" in m["message"]
        assert recevoir(ws, "fin")[0]["raison"] == "refuse"
    assert amont.connexions == []


def test_live_refuse_sans_cle_et_au_plafond(client, centre, simulateur, amont):
    with ouvrir(client) as ws:
        ws.send_json({"t": "demarrer", "modele": "grok-voice-think-fast"})
        assert "XAI_API_KEY" in recevoir(ws, "erreur")[0]["message"]
    cles(simulateur)
    centre.couts.definir_plafonds(1, None)
    centre.couts.enregistrer("deepseek", 1)
    with ouvrir(client) as ws:
        ws.send_json({"t": "demarrer"})
        assert "plafond" in recevoir(ws, "erreur")[0]["message"].lower()
    assert amont.connexions == []


def test_live_service_injoignable(client, simulateur, amont):
    cles(simulateur)
    amont.echec = "connexion refusée sk-abcdefghijkl1234"
    with ouvrir(client) as ws:
        ws.send_json({"t": "demarrer"})
        m, _ = recevoir(ws, "erreur")
        assert "impossible" in m["message"] and "sk-abcdefghijkl1234" not in m["message"]
        assert recevoir(ws, "fin")[0]["raison"] == "erreur"


def test_live_coupe_au_plafond(client, centre, simulateur, amont):
    cles(simulateur)
    centre.voix.intervalle_tick = 0.05
    centre.couts.definir_plafonds(0.02, None)
    with ouvrir(client) as ws:
        demarrer(ws)
        conn = amont.connexions[0]
        conn.emettre({"type": "response.done", "response": {"usage": {"input_tokens": 1000, "output_tokens": 1000}, "output": []}})   # ≈ 0,03 $
        m, vus = recevoir(ws, "fin")
        assert m["raison"] == "plafond" and any("Plafond" in v.get("message", "") for v in vus)
    assert conn.ferme
    assert centre.couts.statut()["bloque"] is True                       # la dépense a bien été enregistrée


def test_live_duree_max_et_silence(client, centre, simulateur, amont):
    cles(simulateur)
    centre.voix.intervalle_tick = 0.05
    centre.voix.duree_max_minutes = 0.001
    with ouvrir(client) as ws:
        demarrer(ws)
        assert recevoir(ws, "fin")[0]["raison"] == "duree-max"
    centre.voix.duree_max_minutes = 30
    centre.voix.silence_max = 0.1
    with ouvrir(client) as ws:
        demarrer(ws)
        assert recevoir(ws, "fin")[0]["raison"] == "silence"


def test_live_bascule_en_mode_confidentiel_coupe(client, centre, simulateur, amont):
    cles(simulateur)
    centre.voix.intervalle_tick = 0.05
    with ouvrir(client) as ws:
        demarrer(ws)
        mode(simulateur, centre, "ultra")
        m, _ = recevoir(ws, "fin")
        assert m["raison"] == "mode-confidentiel"


def test_grok_facture_a_la_duree(client, centre, simulateur, amont, horloge):
    cles(simulateur)
    centre.voix.horloge = horloge
    centre.voix.intervalle_tick = 0.05
    with ouvrir(client) as ws:
        pret = demarrer(ws, modele="grok-voice-think-fast")
        assert pret["fournisseur"] == "xai" and amont.connexions[0].url.startswith("wss://api.x.ai/v1/realtime")
        assert amont.connexions[0].entetes["Authorization"] == "Bearer xai-secret-0000000000"
        horloge.t += 120                                   # deux minutes « passent »
        m, _ = recevoir(ws, "cout")
        while m["minutes"] < 1.9:
            m, _ = recevoir(ws, "cout")
        assert m["usd"] == pytest.approx(0.16, abs=0.002)
        ws.send_json({"t": "couper"})
        assert recevoir(ws, "fin")[0]["cout_usd"] == pytest.approx(0.16, abs=0.005)
    assert centre.couts.totaux()["aujourdhui"]["par_ia"]["voix"] == pytest.approx(0.16, abs=0.005)


def test_modele_inconnu_retombe_sur_le_defaut(client, simulateur, amont):
    cles(simulateur)
    with ouvrir(client) as ws:
        assert demarrer(ws, modele="../../evil", voix="x;y")["modele"] == "gpt-realtime-mini"
        assert amont.connexions[0].url.endswith("model=gpt-realtime-mini")


# ----- outils de l'agent vocal -----------------------------------------------------------------------------------------

def test_outil_consulter_salle_via_la_voix(client, centre, simulateur, amont, reseau):
    from centre.salles import URLS_API
    cles(simulateur)
    reseau.repondre(URLS_API["deepseek"], lambda c, e: sse("La réponse", " de DeepSeek."))
    with ouvrir(client) as ws:
        demarrer(ws)
        conn = amont.connexions[0]
        conn.emettre({"type": "response.function_call_arguments.done", "call_id": "c1", "name": "consulter_salle",
                      "arguments": json.dumps({"salle": "deepseek", "question": "Quelle heure est-il ?"})})
        assert recevoir(ws, "outil")[0]["etat"] == "appel"
        fini, _ = recevoir(ws, "outil")
        assert fini["etat"] == "fini" and "DeepSeek" in fini["resume"]
        assert attendre(lambda: "response.create" in conn.types()[1:])
        sortie = [m for m in conn.envoyes if m["type"] == "conversation.item.create"][-1]["item"]
        assert sortie["type"] == "function_call_output" and sortie["call_id"] == "c1"
        assert "donnees_non_fiables" in sortie["output"] and "La réponse de DeepSeek." in sortie["output"]
        # doublon ignoré
        conn.emettre({"type": "response.function_call_arguments.done", "call_id": "c1", "name": "consulter_salle", "arguments": "{}"})
        ws.send_json({"t": "couper"})
        recevoir(ws, "fin")
    convs = centre.salles.conversations.lister("deepseek")
    assert convs and convs[0]["titre"].startswith("Vocal")
    assert reseau.appels[-1][2]["messages"][-1]["content"] == "Quelle heure est-il ?"       # ni mémoire ni tiroir ajoutés


def test_outil_dans_response_done_sans_evenement_dedie(client, centre, simulateur, amont):
    cles(simulateur)
    with ouvrir(client) as ws:
        demarrer(ws)
        conn = amont.connexions[0]
        conn.emettre({"type": "response.done", "response": {"usage": {}, "output": [
            {"type": "function_call", "call_id": "z9", "name": "chercher_memoire", "arguments": json.dumps({"question": "couple de serrage"})}]}})
        recevoir(ws, "outil"); recevoir(ws, "outil")
        assert attendre(lambda: any(m.get("item", {}).get("call_id") == "z9" for m in conn.envoyes))
        ws.send_json({"t": "couper"}); recevoir(ws, "fin")


def test_outil_memoire_jamais_de_prive(centre, simulateur):
    simulateur.tout_allumer(); centre.rafraichir()
    r = centre.voix.executer_outil("chercher_memoire", json.dumps({"question": "contrat client Durand prix secret couple serrage vis"}))
    assert "newton" in r and "12000" not in r and "Durand" not in r


def test_outils_arguments_invalides(centre):
    for args in ("pas du json", "[]", '"x"'):
        assert "illisibles" in centre.voix.executer_outil("consulter_salle", args)
    assert "inconnu" in centre.voix.executer_outil("effacer_disque", "{}")
    assert "inconnue" in centre.voix.executer_outil("consulter_salle", json.dumps({"salle": "root", "question": "x"}))
    assert "vide" in centre.voix.executer_outil("consulter_salle", json.dumps({"salle": "gemma", "question": " "}))


def test_outil_consulter_refuse_en_mode_local(centre, simulateur):
    mode(simulateur, centre, "ultra")
    r = centre.voix.executer_outil("consulter_salle", json.dumps({"salle": "gemma", "question": "salut"}))
    assert "impossible" in r.lower() and not centre.salles.conversations.lister()


def test_outil_signale_les_approbations_de_claude(centre, simulateur, processus):
    from test_salles import flux_claude
    processus.scenarios["claude"] = flux_claude("Je dois lancer une commande.", refus=[("t1", "Bash", {"command": "git status"})])
    r = centre.voix.executer_outil("consulter_salle", json.dumps({"salle": "claude", "question": "regarde git"}))
    assert "approbation" in r and "git status" in r


# ----- talkie-walkie -----------------------------------------------------------------------------------------------------------

def test_transcrire(client, centre, simulateur, reseau):
    cles(simulateur)
    vu = {}
    def stt(corps, entetes):
        vu["corps"], vu["entetes"] = corps, entetes
        return 200, json.dumps({"text": " Bonjour le monde "})
    reseau.repondre(URL_STT, stt)
    r = client.post("/api/voix/transcrire?fournisseur=openai&duree=30", content=b"\x1aE\xdf\xa3AUDIO", headers={"Content-Type": "audio/webm;codecs=opus"})
    assert r.status_code == 200 and r.json()["texte"] == "Bonjour le monde"
    assert vu["entetes"]["Authorization"] == "Bearer sk-openai-secret-000000" and vu["entetes"]["Content-Type"].startswith("multipart/form-data")
    assert b'name="model"' in vu["corps"] and b"gpt-4o-mini-transcribe" in vu["corps"] and b'name="language"\r\n\r\nfr' in vu["corps"]
    assert centre.couts.totaux()["aujourdhui"]["par_ia"]["voix"] == pytest.approx(30 / 60 * 0.003, abs=1e-4)
    assert "sk-openai-secret" not in r.text


def test_transcrire_erreurs(client, centre, simulateur, reseau):
    cles(simulateur)
    assert client.post("/api/voix/transcrire", content=b"x", headers={"Content-Type": "text/html"}).status_code == 415
    assert client.post("/api/voix/transcrire", content=b"", headers={"Content-Type": "audio/webm"}).status_code == 413
    assert client.post("/api/voix/transcrire?fournisseur=zzz", content=b"x", headers={"Content-Type": "audio/webm"}).status_code == 400
    assert client.post("/api/voix/transcrire", content=b"x" * 10, headers={"Content-Type": "audio/webm", "Content-Length": "9000000"}).status_code in (400, 413)
    reseau.repondre(URL_STT, lambda c, e: (401, json.dumps({"error": {"message": "bad key sk-abcdefghijkl1234"}})))
    r = client.post("/api/voix/transcrire", content=b"abc", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 502 and "Clé refusée" in r.json()["erreur"] and "sk-abcdefghijkl1234" not in r.text
    mode(simulateur, centre, "confidentiel")
    r = client.post("/api/voix/transcrire", content=b"abc", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 403 and "désactivée" in r.json()["erreur"]
    assert centre.couts.totaux()["aujourdhui"]["total"] == 0


def message_ia(centre, texte, **extra):
    conv = centre.salles.creer_conversation("deepseek")
    centre.salles.conversations.ajouter_message(conv, "assistant", texte, salle="deepseek", **extra)
    centre.salles.conversations.enregistrer(conv)
    return conv, conv["messages"][-1]["id"]


def test_parler(client, centre, simulateur, reseau):
    cles(simulateur)
    vu = {}
    reseau.repondre(URL_TTS, lambda c, e: (vu.update(corps=c, entetes=e) or (200, b"ID3-MP3-DATA")))
    conv, mid = message_ia(centre, "Voici la réponse à lire.")
    r = client.post("/api/voix/parler", json={"conversation": conv["id"], "message_id": mid, "fournisseur": "openai", "voix": "nova"})
    assert r.status_code == 200 and r.content == b"ID3-MP3-DATA" and r.headers["content-type"] == "audio/mpeg" and r.headers["x-tronque"] == "0"
    assert vu["corps"]["input"] == "Voici la réponse à lire." and vu["corps"]["voice"] == "nova" and vu["corps"]["model"] == "gpt-4o-mini-tts"
    assert centre.couts.totaux()["aujourdhui"]["par_ia"]["voix"] == pytest.approx(len("Voici la réponse à lire.") * 12 / 1e6, abs=1e-4)


def test_parler_texte_long_tronque(client, centre, simulateur, reseau):
    cles(simulateur)
    reseau.repondre(URL_TTS, lambda c, e: (200, b"x"))
    conv, mid = message_ia(centre, "a" * 5000)
    r = client.post("/api/voix/parler", json={"conversation": conv["id"], "message_id": mid})
    assert r.headers["x-tronque"] == "1" and len(reseau.appels[-1][2]["input"]) == 3000


def test_parler_refuse_le_prive(client, centre, simulateur, reseau):
    cles(simulateur)
    reseau.repondre(URL_TTS, lambda c, e: (200, b"x"))
    conv, mid = message_ia(centre, "réponse issue d'un document privé", sensible=True)
    r = client.post("/api/voix/parler", json={"conversation": conv["id"], "message_id": mid})
    assert r.status_code == 403 and "privé" in r.json()["erreur"]
    conv2, mid2 = message_ia(centre, "ok")
    c = centre.salles.conversation(conv2["id"]); c["prive"] = True; centre.salles.conversations.enregistrer(c)
    assert client.post("/api/voix/parler", json={"conversation": conv2["id"], "message_id": mid2}).status_code == 403
    assert not [a for a in reseau.appels if a[1] == URL_TTS]


def test_parler_erreurs(client, centre, simulateur, reseau):
    cles(simulateur)
    assert client.post("/api/voix/parler", json={"conversation": "0123456789abcdef", "message_id": "x"}).status_code == 404
    conv, mid = message_ia(centre, "ok")
    assert client.post("/api/voix/parler", json={"conversation": conv["id"], "message_id": "inconnu"}).status_code == 404
    assert client.post("/api/voix/parler", json={"conversation": conv["id"], "message_id": mid, "fournisseur": "x"}).status_code == 400
    mode(simulateur, centre, "ultra")
    assert client.post("/api/voix/parler", json={"conversation": conv["id"], "message_id": mid}).status_code == 403


def test_routes_voix_exigent_session_et_csrf(anonyme, client):
    assert anonyme.get("/api/voix/options").status_code == 401
    assert anonyme.post("/api/voix/parler", json={}).status_code == 401
    assert anonyme.post("/api/voix/transcrire", content=b"x").status_code == 401
    del client.headers["X-Centre"]
    assert client.post("/api/voix/parler", json={}).status_code == 403
    assert client.post("/api/voix/transcrire", content=b"x").status_code == 403
