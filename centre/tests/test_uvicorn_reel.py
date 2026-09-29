# -*- coding: utf-8 -*-
"""Vrai serveur uvicorn + vrai client WebSocket (bibliothèque `websockets`), fournisseur vocal simulé."""

import asyncio
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
import websockets

from conftest import NIP, SECRET
from centre.app import creer_app


@pytest.fixture
def serveur(centre, verrou):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    centre.config.port = port
    config = uvicorn.Config(creer_app(centre, verrou), host="127.0.0.1", port=port, log_level="error")
    serveur = uvicorn.Server(config)
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    for _ in range(200):
        if serveur.started:
            break
        time.sleep(0.02)
    yield port
    serveur.should_exit = True
    fil.join(5)


def test_voix_live_avec_un_vrai_serveur(serveur, centre, simulateur, amont):
    port = serveur
    simulateur.cles["OPENAI_API_KEY"] = "sk-openai-secret-000000"
    base = f"http://127.0.0.1:{port}"
    r = httpx.post(base + "/api/connexion", json={"nip": NIP, "secret": SECRET}, headers={"X-Centre": "1"})
    assert r.status_code == 200
    cookie = "centre_session=" + r.cookies["centre_session"]

    async def scenario():
        # sans cookie : refusé
        with pytest.raises(Exception):
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws/voix", origin=base):
                pass
        # mauvaise origine : refusé
        with pytest.raises(Exception):
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws/voix", origin="https://evil.example",
                                          additional_headers={"Cookie": cookie}):
                pass
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws/voix", origin=base, additional_headers={"Cookie": cookie}) as ws:
            await ws.send(json.dumps({"t": "demarrer", "modele": "gpt-realtime-mini"}))
            m = json.loads(await asyncio.wait_for(ws.recv(), 5))
            assert m["t"] == "pret"
            amont.connexions[0].emettre({"type": "response.output_audio.delta", "delta": "QUJD"})
            m = json.loads(await asyncio.wait_for(ws.recv(), 5))
            assert m == {"t": "audio", "pcm": "QUJD"}
            await ws.send(json.dumps({"t": "couper"}))
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), 5))
                if m["t"] == "fin":
                    assert m["raison"] == "arret-utilisateur"
                    break

    asyncio.run(scenario())
