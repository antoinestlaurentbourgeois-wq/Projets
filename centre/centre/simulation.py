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
