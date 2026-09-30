# -*- coding: utf-8 -*-
"""
Réseau et programmes SIMULÉS pour le mode démo : on peut essayer toutes les salles sans clé, sans compte,
sans rien dépenser. Chaque IA répond par un texte fabriqué.
"""

import json
import re
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
    comfy = False            # le faux ComfyUI est-il lancé ? (les faux scripts demarrer / arreter le basculent : voir __main__.demo)

    def flux_post(self, url, entetes, corps, delai=600, annulation=None):
        if isinstance(corps.get("table_ronde"), dict):
            return 200, self._table_ronde(corps)
        question = corps["messages"][-1]["content"] if corps.get("messages") else ""
        images = 0
        if isinstance(question, list):                 # message avec images (format OpenAI) : texte + nombre d'images reçues
            images = len([p for p in question if isinstance(p, dict) and p.get("type") == "image_url"])
            question = " ".join(p.get("text", "") for p in question if isinstance(p, dict) and p.get("type") == "text")
        qui = corps.get("model") or url.split("/")[2]
        if "<<<QUESTION>>>" in question:            # vérification (Truth Gate) : réponse au format JSON attendu
            return 200, _sse([json.dumps({"verdict": "a_verifier", "resume": "Vérification SIMULÉE : rien n'a été réellement contrôlé.",
                                          "affirmations": [{"texte": "Première affirmation de la réponse", "statut": "confirmee", "raison": "simulation"},
                                                           {"texte": "Deuxième affirmation", "statut": "douteuse", "raison": "simulation"}]}, ensure_ascii=False)])
        demande = question.split("Demande de l'utilisateur :")[-1].strip()
        if re.search(r"\b(image|dessin|illustration|logo)\b", demande.lower()) and "[[IMAGE]]" not in demande:
            # L'IA de démonstration répond comme le ferait une vraie IA à qui on demande une image : un bloc [[IMAGE]] (le Centre le transforme en carte, sans rien lancer)
            sujet = re.sub(r"^.*?(image|dessin|illustration|logo)( d[e'u] ?| des | de la | d')?", "", demande, flags=re.IGNORECASE).strip(" .?!") or "un paysage de montagne au lever du soleil"
            return 200, _sse(["Avec plaisir ! ", "[[IMAGE]]\ntaille: paysage\ndescription: ", sujet[:200] + ", lumière douce, détails nets, style illustration soignée", "\n[[/IMAGE]]", "\nDites-moi si vous voulez l'ajuster."])
        mots = (_reponse(demande, qui) + (f" (SIMULATION : {images} image(s) reçue(s))" if images else "")).split(" ")
        return 200, _sse([m + " " for m in mots])

    @staticmethod
    def _table_ronde(corps):
        """Faux Crew, calqué sur le VRAI flux : premier morceau {"role"}, pulsation de contenu vide, « debut » puis UNE « reponse » complète par IA
        (texte dans choices[0].delta.content, duree_s au niveau du morceau, usage {entree, sortie, cout_usd}), « exclu » / « erreur » avec « message »,
        synthèse = participant « synthese » (tour 0, sans « debut »), morceau finish_reason « stop », ligne « fin » (usage total, exclus, notes)."""
        tr = corps["table_ronde"]
        question = corps["messages"][-1]["content"][:60] if corps.get("messages") else ""
        noms = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini", "grok": "Grok", "deepseek": "DeepSeek", "gemma": "gemma"}
        couts = {"claude": 0.05, "codex": 0.04, "gemini": 0.0, "grok": 0.06, "deepseek": 0.003, "gemma": 0.0}
        libelles = {"claude": "Claude", "codex": "ChatGPT / Codex", "gemini": "Gemini", "grok": "Grok", "deepseek": "DeepSeek", "gemma": "gemma (local)", "synthese": "Synthèse de Crew"}

        def sse(d):
            return "data: " + json.dumps(d, ensure_ascii=False)

        def lignes():
            yield sse({"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}); yield ""
            yield sse({"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": None}]}); yield ""     # pulsation
            total, exclus = 0.0, []
            for tour in ((1, 2) if tr.get("critique") else (1,)):
                for p in tr["participants"]:
                    if p == "grok" and "exclu" in question.lower():
                        exclus.append(p)
                        yield sse({"evenement": "exclu", "participant": p, "tour": tour, "libelle": libelles[p],
                                   "message": "exclue : contenu confidentiel, traité en local seulement"}); yield ""
                        continue
                    yield sse({"evenement": "debut", "participant": p, "tour": tour, "libelle": libelles[p]}); yield ""
                    time.sleep(0.05)
                    yield sse({"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": None}]}); yield ""     # pulsation
                    if p == "claude" and "echec" in question.lower():
                        yield sse({"evenement": "erreur", "participant": p, "tour": tour, "libelle": libelles[p], "message": "503 surcharge simulée"}); yield ""
                        continue
                    texte = f"[réponse SIMULÉE de {noms.get(p, p)}" + (", tour de critique" if tour == 2 else "") + f"] Sur « {question} » : voici mon avis, avec une réserve importante sur les hypothèses."
                    total += couts.get(p, 0.0)
                    yield sse({"evenement": "reponse", "participant": p, "tour": tour, "libelle": libelles[p], "duree_s": round(1 + 0.4 * len(p), 1),
                               "choices": [{"index": 0, "delta": {"content": texte}, "finish_reason": None}],
                               "usage": {"entree": 40, "sortie": 60, "cout_usd": couts.get(p, 0.0)}}); yield ""
            if tr.get("synthese", True):
                yield sse({"evenement": "reponse", "participant": "synthese", "tour": 0, "libelle": libelles["synthese"], "duree_s": 0.8,
                           "choices": [{"index": 0, "delta": {"content": "[SYNTHÈSE SIMULÉE] Les IA convergent sur l'essentiel ; Crew retient les points communs et signale les désaccords."}, "finish_reason": None}],
                           "usage": {"entree": 200, "sortie": 40, "cout_usd": 0.0}}); yield ""
            yield sse({"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}); yield ""
            yield sse({"evenement": "fin", "usage": {"prompt_tokens": 300, "completion_tokens": 200, "total_tokens": 500, "cout_usd": round(total, 6)},
                       "exclus": exclus, "notes": ["partageable/notes/mecanique.md"] if "note" in question.lower() else []}); yield ""
            yield "data: [DONE]"; yield ""
        return lignes()

    def requete(self, methode, url, entetes=None, corps=None, delai=30, octets=False, max_octets=0):
        if url == "https://api.x.ai/v1/models":
            return 200, json.dumps({"data": [{"id": "grok-4"}, {"id": "grok-imagine-image"}, {"id": "grok-imagine-image-2.0"}, {"id": "grok-imagine-image-quality"}, {"id": "grok-imagine-video"}]})
        if url.endswith("/models"):
            return 200, json.dumps({"data": [{"id": "modele-demo-1"}, {"id": "modele-demo-2"}]})
        if url.endswith("/realtime/client_secrets"):
            return 200, json.dumps({"value": "jeton-de-session-demo", "expires_at": 0})
        if url.endswith("/audio/transcriptions") or url.endswith("/v1/stt"):
            return 200, json.dumps({"text": "Bonjour, ceci est une question posée à voix haute (transcription simulée)."})
        if url.endswith("/audio/speech") or url.endswith("/v1/tts"):
            return 200, (_wav_bip() if octets else "")
        image = self._images(methode, url, corps, octets)
        if image is not None:
            return image
        return 404, "{}"

    def _images(self, methode, url, corps, octets):
        """Faux moteurs d'images (démo) : OpenAI, xAI, Gemini et ComfyUI répondent avec un petit dégradé PNG dont la couleur dépend de la demande."""
        import base64
        graine = len(json.dumps(corps or {}, sort_keys=True)) * 7
        if url == "https://api.x.ai/v1/images/generations":
            return 200, json.dumps({"data": [{"b64_json": base64.b64encode(_png_demo(graine)).decode(), "mime_type": "image/png"}], "usage": {"cost_in_usd_ticks": 200000000}})
        if url.endswith("/images/generations"):
            return 200, json.dumps({"data": [{"b64_json": base64.b64encode(_png_demo(graine)).decode()}]})
        if ":generateContent" in url:
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": "Voici."}, {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(_png_demo(graine)).decode()}}]}}]})
        if url.startswith("http://127.0.0.1:8188"):
            if not self.comfy:
                return None, "connexion refusée"
            if url.endswith("/queue"):
                return 200, json.dumps({"queue_running": [], "queue_pending": []})
            if url.endswith("/system_stats"):
                return 200, "{}"
            if url.endswith("/object_info/CheckpointLoaderSimple"):
                return 200, json.dumps({"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["demo-sdxl.safetensors", "demo-sd15.safetensors", "demo-flux.safetensors"]]}}}})
            if url.endswith("/free") or url.endswith("/interrupt"):
                return 200, "{}"
            if url.endswith("/prompt") and methode == "POST":
                return 200, json.dumps({"prompt_id": "demo1"})
            if "/history/" in url:
                return 200, json.dumps({"demo1": {"outputs": {"7": {"images": [{"filename": "centre_00001_.png", "subfolder": "", "type": "output"}]}}, "status": {"status_str": "success"}}})
            if "/view?" in url:
                return 200, (_png_demo(graine) if octets else "")
        return None


def _png_demo(graine=0, n=256):
    """PNG valide n × n : dégradé dont les couleurs dépendent de `graine`."""
    import struct
    import zlib

    def bloc(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    lignes = []
    for y in range(n):
        ligne = bytearray(b"\x00")
        for x in range(n):
            ligne += bytes(((x + graine) % 256, (y * 2 + graine // 3) % 256, (255 - (x + y) // 2 + graine // 5) % 256))
        lignes.append(bytes(ligne))
    return b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0)) + bloc(b"IDAT", zlib.compress(b"".join(lignes))) + bloc(b"IEND", b"")


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
        if "<<<QUESTION>>>" in (stdin_texte or ""):
            texte = json.dumps({"verdict": "fiable", "resume": "Vérification SIMULÉE.", "affirmations": [
                {"texte": "Affirmation simulée", "statut": "confirmee", "raison": "simulation"}]}, ensure_ascii=False)
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
