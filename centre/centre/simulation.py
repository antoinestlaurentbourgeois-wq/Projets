# -*- coding: utf-8 -*-
"""
Réseau et programmes SIMULÉS pour le mode démo : on peut essayer toutes les salles sans clé, sans compte,
sans rien dépenser. Chaque IA répond par un texte fabriqué.
"""

import json
import time

from .reseau import ProcessusEnCours


def _sse(morceaux, usage=(50, 40)):
    def lignes():
        for m in morceaux:
            time.sleep(0.03)
            yield "data: " + json.dumps({"choices": [{"delta": {"content": m}}]})
            yield ""
        yield "data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}})
        yield ""
        yield "data: [DONE]"
        yield ""
    return lignes()


def _reponse(question, qui):
    return (f"[réponse SIMULÉE de {qui}] Vous avez écrit : « {question[:120]} ». "
            "Ceci est un exemple de réponse avec du **gras**, du `code` et une liste.\n\n"
            "```python\nprint('bonjour')\n```\n\nRien n'a été envoyé à une vraie IA.")


class ReseauDemo:
    def flux_post(self, url, entetes, corps, delai=600, annulation=None):
        question = corps["messages"][-1]["content"] if corps.get("messages") else ""
        qui = corps.get("model") or url.split("/")[2]
        mots = _reponse(question.split("Demande de l'utilisateur :")[-1].strip(), qui).split(" ")
        return 200, _sse([m + " " for m in mots])

    def requete(self, methode, url, entetes=None, corps=None, delai=30, octets=False, max_octets=0):
        if url.endswith("/models"):
            return 200, json.dumps({"data": [{"id": "modele-demo-1"}, {"id": "modele-demo-2"}]})
        if url.endswith("/audio/transcriptions") or url.endswith("/v1/stt"):
            return 200, json.dumps({"text": "Bonjour, ceci est une question posée à voix haute (transcription simulée)."})
        if url.endswith("/audio/speech") or url.endswith("/v1/tts"):
            return 200, (_wav_bip() if octets else "")
        return 404, "{}"


class _Proc:
    def __init__(self, lignes):
        self._l = lignes
        self.termine = False

    def lignes(self):
        for l in self._l:
            if self.termine:
                return
            time.sleep(0.03)
            yield l

    def terminer(self):
        self.termine = True

    def attendre(self, delai=10):
        return 0

    def stderr_texte(self):
        return ""


class ProcessusDemo:
    def trouver(self, nom, candidats=()):
        return f"demo/{nom}"

    def lancer(self, args, cwd=None, env=None, stdin_texte=None):
        nom = args[0].split("/")[-1]
        question = (stdin_texte or "").strip().split("\n")[-1]
        texte = _reponse(question, nom)
        if nom == "claude":
            refus = []
            if "approbation" in question.lower():
                refus = [{"tool_name": "Bash", "tool_use_id": "demo1", "tool_input": {"command": "git status"}},
                         {"tool_name": "Write", "tool_use_id": "demo2", "tool_input": {"file_path": "notes.txt"}}]
            lignes = [json.dumps({"type": "system", "subtype": "init", "session_id": "demo-session-0001"})]
            for m in texte.split(" "):
                lignes.append(json.dumps({"type": "stream_event", "event": {"type": "content_block_delta",
                                                                            "delta": {"type": "text_delta", "text": m + " "}}}))
            lignes.append(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": texte,
                                      "session_id": "demo-session-0001", "total_cost_usd": 0.0,
                                      "usage": {"input_tokens": 50, "output_tokens": 40}, "permission_denials": refus}))
            return _Proc(lignes)
        if nom == "codex":
            return _Proc([json.dumps({"type": "thread.started", "thread_id": "demo"}),
                          json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": texte}}),
                          json.dumps({"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 5}})])
        return _Proc(texte.split("\n"))


# ------------------------------------------------------------------------------------------------
# Voix simulée (mode démo) : un « fournisseur » qui répond par une phrase et un petit bip
# ------------------------------------------------------------------------------------------------

def _bip_pcm16(secondes=0.25, hz=440, rate=24000):
    import math, struct
    n = int(secondes * rate)
    return b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * hz * i / rate))) for i in range(n))


def _wav_bip(secondes=0.6, hz=523, rate=24000):
    import struct
    pcm = _bip_pcm16(secondes, hz, rate)
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


class ConnexionDemo:
    def __init__(self):
        import asyncio
        self._q = asyncio.Queue()
        self.n_audio = 0
        self.repondu = False

    async def send(self, message):
        import asyncio
        m = json.loads(message)
        if m.get("type") == "input_audio_buffer.append":
            self.n_audio += 1
            if self.n_audio == 10 and not self.repondu:
                self.repondu = True
                asyncio.get_running_loop().create_task(self._repondre())

    async def _repondre(self):
        import asyncio
        put = lambda e: self._q.put_nowait(json.dumps(e))
        put({"type": "input_audio_buffer.speech_started"})
        await asyncio.sleep(0.2)
        put({"type": "input_audio_buffer.speech_stopped"})
        put({"type": "conversation.item.input_audio_transcription.completed", "transcript": "Bonjour (voix simulée)"})
        import base64
        for _ in range(4):
            put({"type": "response.output_audio.delta", "delta": base64.b64encode(_bip_pcm16()).decode()})
            await asyncio.sleep(0.1)
        put({"type": "response.output_audio_transcript.done", "transcript": "Bonjour ! Ceci est une réponse vocale SIMULÉE : aucun vrai service n'est utilisé."})
        put({"type": "response.done", "response": {"usage": {"input_tokens": 400, "output_tokens": 300,
             "input_token_details": {"audio_tokens": 300, "text_tokens": 100},
             "output_token_details": {"audio_tokens": 250, "text_tokens": 50}}, "output": []}})

    async def close(self):
        self._q.put_nowait(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        x = await self._q.get()
        if x is None:
            raise StopAsyncIteration
        return x


class AmontDemo:
    async def ouvrir(self, url, entetes):
        return ConnexionDemo()
