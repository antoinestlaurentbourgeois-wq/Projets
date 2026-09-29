# -*- coding: utf-8 -*-
"""Historique des conversations : un fichier JSON par conversation, dans donnees/conversations/ (sur I:)."""

import json
import os
import re
import secrets
import threading
import time

ID_OK = re.compile(r"^[0-9a-f]{16}$")
MAX_TEXTE = 60000
MAX_TITRE = 120


class ErreurConversation(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


class Conversations:
    def __init__(self, dossier):
        self.dossier = dossier
        self._verrou = threading.RLock()
        os.makedirs(dossier, exist_ok=True)

    def _chemin(self, cid):
        if not ID_OK.match(str(cid or "")):
            raise ErreurConversation("Conversation inconnue.", 404)
        return os.path.join(self.dossier, cid + ".json")

    def creer(self, salle, titre=""):
        cid = secrets.token_hex(8)
        maintenant = time.time()
        conv = {"id": cid, "salle": salle, "titre": (titre or "Nouvelle conversation")[:MAX_TITRE],
                "cree": maintenant, "maj": maintenant, "prive": False, "cli_session": "",
                "en_attente": [], "messages": []}
        self.enregistrer(conv)
        return conv

    def lire(self, cid):
        with self._verrou:
            try:
                with open(self._chemin(cid), encoding="utf-8") as f:
                    return json.load(f)
            except OSError:
                raise ErreurConversation("Conversation inconnue.", 404)
            except ValueError:
                raise ErreurConversation("Conversation illisible.", 500)

    def enregistrer(self, conv):
        chemin = self._chemin(conv["id"])
        conv["maj"] = time.time()
        with self._verrou:
            temporaire = chemin + ".tmp"
            with open(temporaire, "w", encoding="utf-8") as f:
                json.dump(conv, f, ensure_ascii=False)
            os.replace(temporaire, chemin)

    def ajouter_message(self, conv, role, texte, **extra):
        m = {"id": secrets.token_hex(6), "role": role, "texte": str(texte)[:MAX_TEXTE], "ts": time.time()}
        m.update(extra)
        conv["messages"].append(m)
        return m

    def supprimer(self, cid):
        with self._verrou:
            try:
                os.remove(self._chemin(cid))
            except OSError:
                raise ErreurConversation("Conversation inconnue.", 404)

    def renommer(self, cid, titre):
        titre = str(titre or "").strip()[:MAX_TITRE]
        if not titre:
            raise ErreurConversation("Titre vide.")
        with self._verrou:
            conv = self.lire(cid)
            conv["titre"] = titre
            self.enregistrer(conv)
        return conv

    def lister(self, salle=None, limite=200):
        resume = []
        with self._verrou:
            for nom in os.listdir(self.dossier):
                if not nom.endswith(".json") or not ID_OK.match(nom[:-5]):
                    continue
                try:
                    with open(os.path.join(self.dossier, nom), encoding="utf-8") as f:
                        c = json.load(f)
                except (OSError, ValueError):
                    continue
                if salle and c.get("salle") != salle:
                    continue
                resume.append({"id": c["id"], "salle": c.get("salle"), "titre": c.get("titre"),
                               "maj": c.get("maj"), "prive": bool(c.get("prive")),
                               "messages": len(c.get("messages", []))})
        resume.sort(key=lambda c: -(c["maj"] or 0))
        return resume[:limite]
