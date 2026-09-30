# -*- coding: utf-8 -*-
"""
Génération d'images par IA : OpenAI (gpt-image-1), Gemini (image), Grok/xAI, ou LOCAL (ComfyUI sur ce PC).

Règles (comme le reste du Centre) :
  - les clés restent sur le PC (variables d'environnement Windows), jamais dans le navigateur, les fichiers, les reçus ni les journaux ;
  - le texte de la demande n'est JAMAIS écrit dans un journal ni un reçu (seulement dans la galerie, sur le PC, à côté de l'image) ;
  - « contenu confidentiel » coché, ou mode Confidentiel / Ultra-confidentiel : moteur LOCAL seulement, jamais le nuage ;
  - coût estimé AVANT l'envoi, plafonds jour/mois respectés, confirmation au-dessus du seuil (`seuil_image_usd`, reglages.json) ;
  - le contenu reçu est une donnée : le type réel est vérifié sur les octets (PNG, JPEG, WebP), jamais d'après ce que dit le serveur.
Les coûts par image sont des estimations indicatives (PLACEHOLDERS à vérifier chez chaque fournisseur).
"""

import base64
import binascii
import json
import logging
import os
import re
import secrets
import threading
import time

from . import ia
from .journal import masquer
from .pieces import TYPES, type_reel

journal = logging.getLogger("centre")

URL_COMFY = "http://127.0.0.1:8188"
ID_OK = re.compile(r"^[0-9a-f]{16}$")
MAX_PROMPT = 4000
MAX_IMAGES_PAR_DEMANDE = 4
MAX_GALERIE = 500
MAX_OCTETS = 20_000_000

MOTEURS = {
    "openai": {"libelle": "OpenAI (gpt-image-1)", "fournisseur": "openai", "nuage": True, "modele": "gpt-image-1",
               "url": "https://api.openai.com/v1/images/generations", "usd_image": 0.042},
    "gemini": {"libelle": "Gemini (image)", "fournisseur": "gemini", "nuage": True, "modele": "gemini-2.5-flash-image",
               "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent", "usd_image": 0.039},
    "xai": {"libelle": "Grok (xAI)", "fournisseur": "xai", "nuage": True, "modele": "grok-2-image",
            "url": "https://api.x.ai/v1/images/generations", "usd_image": 0.07},
    "local": {"libelle": "Local (ComfyUI)", "fournisseur": "", "nuage": False, "modele": "", "url": URL_COMFY, "usd_image": 0.0},
}
TAILLES = {"carre": "Carré", "portrait": "Portrait", "paysage": "Paysage"}
PIXELS = {       # (largeur, hauteur) par moteur ; xAI et Gemini choisissent eux-mêmes
    "openai": {"carre": "1024x1024", "portrait": "1024x1536", "paysage": "1536x1024"},
    "local": {"carre": (768, 768), "portrait": (640, 960), "paysage": (960, 640)},
}


class ErreurImage(Exception):
    def __init__(self, message, code=400, **extra):
        super().__init__(message)
        self.code, self.extra = code, extra


class Images:
    def __init__(self, centre, horloge=time.time):
        self.centre = centre
        self.horloge = horloge
        self.dossier = centre.config.chemin("images")
        self._verrou = threading.Lock()
        self._jobs = {}
        self._actif = None

    # ----- ce que l'écran affiche avant tout choix ---------------------------------------------------------------------------

    def _salles(self):
        return self.centre.salles

    def _comfy_repond(self):
        try:
            code, _ = self._salles().reseau.requete("GET", URL_COMFY + "/system_stats", delai=2)
        except ia.ErreurReseau:
            return False
        return code == 200

    def checkpoints(self):
        """Modèles (checkpoints) installés dans ComfyUI, ou liste vide."""
        try:
            code, texte = self._salles().reseau.requete("GET", URL_COMFY + "/object_info/CheckpointLoaderSimple", delai=5)
            noms = json.loads(texte)["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
            return [n for n in noms if isinstance(n, str) and len(n) < 200][:100] if code == 200 else []
        except (ia.ErreurReseau, ValueError, KeyError, IndexError, TypeError):
            return []

    def _dispo(self, moteur):
        m = MOTEURS[moteur]
        if not m["nuage"]:
            if self._comfy_repond():
                return True, ""
            return False, "ComfyUI ne répond pas sur ce PC (adresse 127.0.0.1:8188) : lancez-le d'abord."
        ok, msg = self._salles().politique.nuage_autorise()
        if not ok:
            return False, msg
        if not self._salles().cles.presente(m["fournisseur"]):
            return False, f"Clé {self._salles().cles.nom(m['fournisseur'])} absente (variables d'environnement Windows)."
        ok, msg = self.centre.couts.peut_utiliser("images", self._salles().mode_crew())
        if not ok:
            return False, msg
        return True, ""

    def options(self):
        self.centre.assurer_etats()
        moteurs = []
        for ident, m in MOTEURS.items():
            ok, raison = self._dispo(ident)
            moteurs.append({"id": ident, "libelle": m["libelle"], "nuage": m["nuage"], "disponible": ok, "raison": raison,
                            "usd_image": m["usd_image"], "tarif_verifie": False})
        premier = next((m["id"] for m in moteurs if m["disponible"]), "")
        return {"moteurs": moteurs, "tailles": [{"id": k, "libelle": v} for k, v in TAILLES.items()], "defaut": premier,
                "seuil_usd": self.centre.config.seuil_image_usd, "max_images": MAX_IMAGES_PAR_DEMANDE,
                "checkpoints": self.checkpoints() if any(m["id"] == "local" and m["disponible"] for m in moteurs) else []}

    def estimer(self, moteur, n=1):
        if moteur not in MOTEURS:
            raise ErreurImage("Moteur d'images inconnu.")
        n = max(1, min(MAX_IMAGES_PAR_DEMANDE, int(n) if isinstance(n, int) and not isinstance(n, bool) else 1))
        usd = round(MOTEURS[moteur]["usd_image"] * n, 4)
        seuil = self.centre.config.seuil_image_usd
        return {"usd": usd, "n": n, "depasse": usd > seuil, "seuil_usd": seuil, "fiable": False,
                "texte": "Gratuit (local)" if usd == 0 else f"≈ {usd:.3f} $ pour {n} image{'s' if n > 1 else ''} (estimation indicative)"}

    # ----- galerie (sur le PC) --------------------------------------------------------------------------------------------------

    def _chemin(self, ident, ext):
        return os.path.join(self.dossier, f"{ident}.{ext}")

    def _enregistrer(self, octets, meta):
        if len(self.lister()) >= MAX_GALERIE:
            raise ErreurImage(f"Galerie pleine ({MAX_GALERIE} images) : supprimez-en avant d'en créer d'autres.", 507)
        ext = type_reel(octets)
        if ext not in ("png", "jpg", "webp"):
            raise ErreurImage("Le moteur n'a pas renvoyé une image valide.", 502)
        os.makedirs(self.dossier, exist_ok=True)
        ident = secrets.token_hex(8)
        for chemin, contenu, mode in ((self._chemin(ident, ext), octets, "wb"),):
            with open(chemin + ".tmp", mode) as f:
                f.write(contenu)
            os.replace(chemin + ".tmp", chemin)
        meta = dict(meta, id=ident, type=TYPES[ext], taille_octets=len(octets), ts=self.horloge())
        with open(self._chemin(ident, "json") + ".tmp", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        os.replace(self._chemin(ident, "json") + ".tmp", self._chemin(ident, "json"))
        return meta

    def lister(self, limite=200):
        sortie = []
        try:
            noms = os.listdir(self.dossier)
        except OSError:
            return []
        for nom in noms:
            if not nom.endswith(".json") or not ID_OK.match(nom[:-5]):
                continue
            try:
                with open(os.path.join(self.dossier, nom), encoding="utf-8") as f:
                    m = json.load(f)
                if isinstance(m, dict) and m.get("id") == nom[:-5]:
                    sortie.append(m)
            except (OSError, ValueError):
                continue
        sortie.sort(key=lambda m: m.get("ts", 0), reverse=True)
        return sortie[:limite]

    def lire(self, ident):
        if not isinstance(ident, str) or not ID_OK.match(ident):
            raise ErreurImage("Image introuvable.", 404)
        for ext, mime in TYPES.items():
            try:
                with open(self._chemin(ident, ext), "rb") as f:
                    return f.read(), mime
            except OSError:
                continue
        raise ErreurImage("Image introuvable.", 404)

    def supprimer(self, ident):
        if not isinstance(ident, str) or not ID_OK.match(ident):
            raise ErreurImage("Image introuvable.", 404)
        trouve = False
        for ext in list(TYPES) + ["json"]:
            try:
                os.remove(self._chemin(ident, ext))
                trouve = True
            except OSError:
                pass
        if not trouve:
            raise ErreurImage("Image introuvable.", 404)

    # ----- génération (en arrière-plan) --------------------------------------------------------------------------------------------

    def lancer(self, moteur, prompt, taille="carre", n=1, prive=False, checkpoint="", confirme_depassement=False, session=""):
        """Contrôles, puis démarrage en arrière-plan. Renvoie l'état de la tâche (id, etat, fait, sur…)."""
        if moteur not in MOTEURS:
            raise ErreurImage("Moteur d'images inconnu.")
        prompt = str(prompt or "").strip()
        if not prompt:
            raise ErreurImage("Décrivez l'image à créer.")
        if len(prompt) > MAX_PROMPT:
            raise ErreurImage(f"Description trop longue (maximum {MAX_PROMPT} caractères).")
        if taille not in TAILLES:
            raise ErreurImage("Format d'image inconnu.")
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_IMAGES_PAR_DEMANDE:
            raise ErreurImage(f"Le nombre d'images doit être de 1 à {MAX_IMAGES_PAR_DEMANDE}.")
        m = MOTEURS[moteur]
        self.centre.assurer_etats()
        if prive and m["nuage"]:
            raise ErreurImage("Contenu confidentiel : seul le moteur local peut créer cette image (rien ne doit quitter le PC).", 403)
        ok, raison = self._dispo(moteur)
        if not ok:
            raise ErreurImage(raison, 403)
        est = self.estimer(moteur, n)
        if m["nuage"] and est["depasse"] and not confirme_depassement:
            raise ErreurImage(f"Coût estimé {est['usd']:.3f} $ : au-dessus du seuil de {est['seuil_usd']:.2f} $. Confirmez pour créer.", 402, depassement=True)
        if not m["nuage"]:
            noms = self.checkpoints()
            if not noms:
                raise ErreurImage("ComfyUI n'a aucun modèle (checkpoint) installé.", 409)
            checkpoint = checkpoint if checkpoint in noms else noms[0]
        with self._verrou:
            if self._actif and self._jobs.get(self._actif, {}).get("etat") == "en_cours":
                raise ErreurImage("Une image est déjà en cours de création : attendez qu'elle soit terminée.", 409)
            ident = secrets.token_hex(8)
            job = {"id": ident, "etat": "en_cours", "fait": 0, "sur": n, "images": [], "message": "", "moteur": moteur, "debut": self.horloge()}
            self._jobs[ident] = job
            self._actif = ident
            for k in [k for k, j in self._jobs.items() if j["etat"] != "en_cours" and self.horloge() - j["debut"] > 3600]:
                del self._jobs[k]
        self.centre.recus.ajouter("image", "demarree", moteur=moteur, n=n, prive=bool(prive), session=session)     # jamais le texte de la demande
        fil = threading.Thread(target=self._travailler, args=(job, prompt, taille, n, bool(prive), checkpoint), name="centre-image", daemon=True)
        fil.start()
        return self.etat_job(ident)

    def etat_job(self, ident):
        with self._verrou:
            j = self._jobs.get(ident)
            if j is None:
                raise ErreurImage("Tâche inconnue ou trop ancienne.", 404)
            return {k: (list(v) if isinstance(v, list) else v) for k, v in j.items() if k != "debut"}

    def attendre(self, ident, delai=30):
        """Pour les tests : attend la fin de la tâche."""
        fin = time.time() + delai
        while time.time() < fin:
            if self.etat_job(ident)["etat"] != "en_cours":
                break
            time.sleep(0.02)
        return self.etat_job(ident)

    def _travailler(self, job, prompt, taille, n, prive, checkpoint):
        m = MOTEURS[job["moteur"]]
        try:
            for i in range(n):
                octets = self._une_image(job["moteur"], prompt, taille, checkpoint, i)
                for o in (octets if isinstance(octets, list) else [octets]):
                    meta = self._enregistrer(o, {"prompt": prompt, "moteur": job["moteur"], "moteur_libelle": m["libelle"], "modele": m["modele"] or checkpoint,
                                                 "taille": taille, "prive": prive, "cout_usd": m["usd_image"]})
                    if m["usd_image"] > 0:
                        self.centre.couts.enregistrer("images", m["usd_image"], detail=f"{job['moteur']} image", estime=True)
                    with self._verrou:
                        job["images"].append({k: meta[k] for k in ("id", "type", "ts", "cout_usd")})
                        job["fait"] = len(job["images"])
            with self._verrou:
                job["etat"] = "termine"
        except ErreurImage as e:
            with self._verrou:
                job["etat"], job["message"] = "erreur", masquer(str(e))[:400]
        except Exception as e:               # jamais de plantage silencieux ni de secret dans le message
            journal.exception("Génération d'image impossible")
            with self._verrou:
                job["etat"], job["message"] = "erreur", masquer(f"Erreur inattendue : {e}")[:400]
        finally:
            self.centre.recus.ajouter("image", "ok" if job["etat"] == "termine" else "erreur", moteur=job["moteur"], images=len(job["images"]))

    def _une_image(self, moteur, prompt, taille, checkpoint, rang):
        m = MOTEURS[moteur]
        if moteur == "local":
            return self._comfy(prompt, taille, checkpoint, rang)
        cle = self._salles().cles.lire(m["fournisseur"])
        if not cle:
            raise ErreurImage("Clé absente.", 403)
        try:
            if moteur == "gemini":
                entetes = {"x-goog-api-key": cle}
                corps = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
            else:
                entetes = {"Authorization": "Bearer " + cle}
                corps = {"model": m["modele"], "prompt": prompt, "n": 1}
                if moteur == "openai":
                    corps["size"] = PIXELS["openai"][taille]
                else:
                    corps["response_format"] = "b64_json"
            try:
                code, texte = self._salles().reseau.requete("POST", m["url"], entetes, corps, delai=240)
            except ia.ErreurReseau as e:
                raise ErreurImage(str(e), 502)
        finally:
            del cle
        if code is None:
            raise ErreurImage(f"{m['libelle']} ne répond pas : {masquer(texte)[:200]}", 502)
        if code != 200:
            raise ErreurImage(ia.message_http(m["libelle"], code, texte), 502)
        return self._decoder(moteur, texte)

    @staticmethod
    def _decoder(moteur, texte):
        try:
            d = json.loads(texte)
            if moteur == "gemini":
                b64 = [p["inlineData"]["data"] for c in d["candidates"] for p in c["content"]["parts"] if isinstance(p, dict) and "inlineData" in p][0]
            else:
                b64 = d["data"][0]["b64_json"]
            octets = base64.b64decode(b64, validate=True)
        except (ValueError, KeyError, IndexError, TypeError, binascii.Error):
            raise ErreurImage("Réponse du moteur d'images illisible (aucune image reçue).", 502)
        if len(octets) > MAX_OCTETS:
            raise ErreurImage("Image reçue trop lourde.", 502)
        return octets

    def _comfy(self, prompt, taille, checkpoint, rang):
        l, h = PIXELS["local"][taille]
        graphe = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "texte, filigrane, déformé, flou", "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": l, "height": h, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"seed": secrets.randbelow(2 ** 32), "steps": 25, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal",
                                                     "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "centre"}},
        }
        reseau = self._salles().reseau
        try:
            code, texte = reseau.requete("POST", URL_COMFY + "/prompt", None, {"prompt": graphe}, delai=30)
            if code != 200:
                raise ErreurImage(f"ComfyUI a refusé la demande ({code}) : {masquer(str(texte))[:200]}", 502)
            pid = json.loads(texte)["prompt_id"]
            if not isinstance(pid, str) or not re.match(r"^[A-Za-z0-9_-]{1,80}$", pid):
                raise ValueError("identifiant")
            fin = time.time() + 600
            while time.time() < fin:
                code, texte = reseau.requete("GET", f"{URL_COMFY}/history/{pid}", delai=10)
                histoire = json.loads(texte).get(pid) if code == 200 else None
                if histoire and histoire.get("outputs"):
                    for sortie in histoire["outputs"].values():
                        for im in sortie.get("images", []):
                            nom, sous, genre = str(im.get("filename", "")), str(im.get("subfolder", "")), str(im.get("type", "output"))
                            if not re.match(r"^[\w.\-]{1,120}$", nom) or not re.match(r"^[\w.\-/]{0,80}$", sous) or ".." in sous or genre not in ("output", "temp", "input"):
                                continue
                            from urllib.parse import urlencode
                            code, octets = reseau.requete("GET", f"{URL_COMFY}/view?" + urlencode({"filename": nom, "subfolder": sous, "type": genre}), delai=30, octets=True)
                            if code == 200:
                                return octets
                    raise ErreurImage("ComfyUI n'a produit aucune image.", 502)
                if histoire and histoire.get("status", {}).get("status_str") == "error":
                    raise ErreurImage("ComfyUI a signalé une erreur pendant la création (mémoire vidéo ? modèle ?).", 502)
                time.sleep(1.0)
            raise ErreurImage("ComfyUI met trop de temps (plus de 10 minutes).", 504)
        except ia.ErreurReseau as e:
            raise ErreurImage(str(e), 502)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ErreurImage("Réponse de ComfyUI illisible.", 502)
