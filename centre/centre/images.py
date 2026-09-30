# -*- coding: utf-8 -*-
"""
Génération d'images par IA : Grok/xAI, Gemini, OpenAI, ou LOCAL (ComfyUI sur ce PC).

Règles (comme le reste du Centre) :
  - les clés restent sur le PC (variables d'environnement Windows), jamais dans le navigateur, les fichiers, les reçus ni les journaux ;
  - le texte de la demande n'est JAMAIS écrit dans un journal ni un reçu (seulement dans la galerie et la conversation, sur le PC) ;
  - contenu confidentiel, conversation privée, mode Confidentiel / Ultra-confidentiel : moteur LOCAL seulement (refus fait par le SERVEUR) ;
  - coût estimé AVANT l'envoi, plafonds jour/mois respectés, confirmation au-dessus du seuil (`seuil_image_usd`, reglages.json) ;
    la dépense est enregistrée au coût RÉEL quand le fournisseur le donne (xAI : usage.cost_in_usd_ticks, 1 tick = 1e-10 $) ;
  - le contenu reçu est une donnée : le type réel est vérifié sur les octets (PNG, JPEG, WebP), jamais d'après ce que dit le serveur ;
  - une création à la fois (les autres attendent, avec un bouton Annuler).
Carte graphique partagée avec le « chef d'équipe » de Crew : pour un travail ComfyUI, c'est CREW qui décharge puis recharge le chef
(POST /chef/liberer, POST /chef/reprendre) ; le Centre ne charge ni ne décharge JAMAIS LM Studio lui-même.
ComfyUI démarre à la demande et s'arrête ensuite (comfyui.py) : un CYCLE = libérer le chef, démarrer ComfyUI, créer toutes les images en attente,
arrêter ComfyUI, recharger le chef. Plusieurs demandes locales à la suite = UN seul cycle ; le « finally » remet toujours tout en ordre.
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
from urllib.parse import urlencode

from . import ia
from .comfyui import ErreurComfyUI
from .journal import masquer
from .pieces import TYPES, type_reel

journal = logging.getLogger("centre")

URL_COMFY = "http://127.0.0.1:8188"
URL_XAI_MODELES = "https://api.x.ai/v1/models"
ID_OK = re.compile(r"^[0-9a-f]{16}$")
MODELE_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+() \-]{0,199}$")
MAX_PROMPT = 4000
MAX_IMAGES_PAR_DEMANDE = 4
MAX_GALERIE = 500
MAX_OCTETS = 20_000_000
TICK_USD = 1e-10                          # xAI : usage.cost_in_usd_ticks
QUOTA_GEMINI_DUREE = 600                  # après un 429 « quota » de Gemini, le moteur reste grisé ce nombre de secondes

MOTEURS = {
    "xai": {"libelle": "Grok (xAI)", "fournisseur": "xai", "nuage": True, "modele": "grok-imagine-image",
            "url": "https://api.x.ai/v1/images/generations", "usd_image": 0.02},
    "gemini": {"libelle": "Gemini (image)", "fournisseur": "gemini", "nuage": True, "modele": "gemini-2.5-flash-image",
               "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent", "usd_image": 0.039},
    "openai": {"libelle": "OpenAI (gpt-image-1)", "fournisseur": "openai", "nuage": True, "modele": "gpt-image-1",
               "url": "https://api.openai.com/v1/images/generations", "usd_image": 0.042},
    "local": {"libelle": "ComfyUI (local)", "fournisseur": "", "nuage": False, "modele": "", "url": URL_COMFY, "usd_image": 0.0},
}
ORDRE = ("xai", "gemini", "openai", "local")
TAILLES = {"carre": "Carré", "portrait": "Portrait", "paysage": "Paysage"}
OPENAI_TAILLES = {"carre": "1024x1024", "portrait": "1024x1536", "paysage": "1536x1024"}

# Familles de modèles ComfyUI : détectées par le nom du checkpoint ; table modifiable (familles_comfy.json dans le dossier des données).
FAMILLES_DEFAUT = {
    "sdxl": {"motifs": ["sdxl", "xl", "pony", "juggernaut", "illustrious", "realvis"], "tailles": {"carre": [1024, 1024], "portrait": [832, 1216], "paysage": [1216, 832]},
             "pas": 28, "cfg": 6.5, "sampler": "dpmpp_2m", "scheduler": "karras", "negatif": True},
    "sd15": {"motifs": ["sd15", "sd1.5", "sd_1", "v1-5", "1.5", "dreamshaper_8", "deliberate"], "tailles": {"carre": [512, 512], "portrait": [512, 768], "paysage": [768, 512]},
             "pas": 25, "cfg": 7.0, "sampler": "euler", "scheduler": "normal", "negatif": True},
    "flux": {"motifs": ["flux"], "tailles": {"carre": [1024, 1024], "portrait": [832, 1216], "paysage": [1216, 832]},
             "pas": 20, "cfg": 1.0, "sampler": "euler", "scheduler": "simple", "negatif": False, "guidance": 3.5},
}
FAMILLE_INCONNUE = "sdxl"                 # inconnu : SDXL prudent
TEXTE_CHEF = ("Crew libère la carte graphique, ComfyUI démarre (environ 20 à 40 s), crée l'image puis s'arrête, et Crew recharge son chef (environ 10 s). "
              "Pendant ce temps Crew continue par un modèle de nuage en mode normal et reste indisponible en mode confidentiel.")
TEXTE_SANS_CHEF = "ComfyUI démarre (environ 20 à 40 s), crée l'image puis s'arrête."


class ErreurImage(Exception):
    def __init__(self, message, code=400, **extra):
        super().__init__(message)
        self.code, self.extra = code, extra


def familles(dossier_donnees=None):
    """Table des familles : celle du code, complétée ou corrigée par familles_comfy.json (valeurs validées, le reste ignoré)."""
    t = {k: json.loads(json.dumps(v)) for k, v in FAMILLES_DEFAUT.items()}
    if not dossier_donnees:
        return t
    try:
        with open(os.path.join(dossier_donnees, "familles_comfy.json"), encoding="utf-8-sig") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return t
    if not isinstance(d, dict):
        return t
    for nom, v in d.items():
        if not isinstance(v, dict) or not re.match(r"^[a-z0-9_]{1,20}$", str(nom)):
            continue
        base = t.get(nom) or json.loads(json.dumps(t[FAMILLE_INCONNUE]))
        if isinstance(v.get("motifs"), list):
            base["motifs"] = [str(m).lower()[:40] for m in v["motifs"] if str(m).strip()][:20]
        if isinstance(v.get("tailles"), dict):
            for k, dim in v["tailles"].items():
                if k in TAILLES and isinstance(dim, list) and len(dim) == 2 and all(isinstance(x, int) and not isinstance(x, bool) and 64 <= x <= 2048 for x in dim):
                    base["tailles"][k] = [dim[0], dim[1]]
        for cle, bas, haut in (("pas", 1, 150), ("cfg", 0, 30), ("guidance", 0, 30)):
            x = v.get(cle)
            if isinstance(x, (int, float)) and not isinstance(x, bool) and bas <= x <= haut:
                base[cle] = x
        for cle in ("sampler", "scheduler"):
            if isinstance(v.get(cle), str) and re.match(r"^[a-z0-9_]{1,40}$", v[cle]):
                base[cle] = v[cle]
        if isinstance(v.get("negatif"), bool):
            base["negatif"] = v["negatif"]
        t[nom] = base
    return t


def famille_du_modele(checkpoint, table):
    """Nom de la famille d'après le nom du checkpoint (flux avant sdxl avant sd15 ; inconnu : SDXL prudent)."""
    nom = str(checkpoint).lower()
    for fam in ("flux", "sdxl", "sd15"):
        if fam in table and any(m in nom for m in table[fam]["motifs"]):
            return fam
    for fam, v in table.items():
        if fam not in ("flux", "sdxl", "sd15") and any(m in nom for m in v.get("motifs", [])):
            return fam
    return FAMILLE_INCONNUE


def graphe_comfy(famille, p, checkpoint, prompt, taille, graine):
    """Graphe ComfyUI standard pour la famille (p = paramètres de la table). Flux : pas de consigne négative (vecteur nul), cfg 1."""
    l, h = p["tailles"][taille]
    g = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
         "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
         "4": {"class_type": "EmptyLatentImage", "inputs": {"width": l, "height": h, "batch_size": 1}}}
    positif = ["2", 0]
    if famille == "flux" or not p.get("negatif", True):
        if p.get("guidance") is not None:
            g["8"] = {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": p["guidance"]}}
            positif = ["8", 0]
        g["3"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}}
    else:
        g["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": "texte, filigrane, déformé, flou, mal dessiné", "clip": ["1", 1]}}
    g["5"] = {"class_type": "KSampler", "inputs": {"seed": graine, "steps": p["pas"], "cfg": p["cfg"], "sampler_name": p["sampler"], "scheduler": p["scheduler"],
                                                 "denoise": 1.0, "model": ["1", 0], "positive": positif, "negative": ["3", 0], "latent_image": ["4", 0]}}
    g["6"] = {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}}
    g["7"] = {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "centre"}}
    return g


class Images:
    def __init__(self, centre, horloge=time.time, dormir=time.sleep):
        self.centre = centre
        self.horloge, self.dormir = horloge, dormir
        self.dossier = centre.config.chemin("images")
        self._verrou = threading.RLock()
        self._jobs = {}
        self._params = {}               # id de tâche -> paramètres (dont la description : jamais renvoyée dans l'état de la tâche)
        self._file = []                 # ids des tâches en attente (une seule s'exécute à la fois)
        self._fil = None
        self._quota_gemini = 0.0
        self._liberer_404 = 0.0
        self._cycle = {"liberee": False}     # ce que le cycle en cours a pris à Crew (le chef déchargé) : il faudra le rendre à la fin
        self._cache_modeles_xai = (0.0, None)
        self.pauses = 1.0               # secondes entre deux lectures de l'avancement (ComfyUI, Crew)

    # ----- petits accès ------------------------------------------------------------------------------------------------------

    def _salles(self):
        return self.centre.salles

    def _famille_table(self):
        return familles(self.centre.config.dossier_donnees)

    def _crew_actif(self):
        return self.centre.etats["crew"].code == self.centre.L.ACTIF

    def _chef_charge(self):
        """Le chef de Crew est-il en mémoire vidéo ? (None si on ne sait pas : Crew arrêté ou muet)"""
        if not self._crew_actif():
            return None
        try:
            return bool(self.centre.crew.lire_chef(crew_actif=True).chef_charge)
        except self.centre.C.ErreurCrew:
            return None

    def _proc(self):
        return self.centre.comfyui

    def _comfy_repond(self):
        return self._proc().repond()

    def local_en_cours(self):
        """Une création ComfyUI est-elle en attente ou en cours ? (alors ComfyUI et la carte graphique sont gardés pour elle)"""
        with self._verrou:
            return any(j["moteur"] == "local" and j["etat"] in ("attente", "en_cours") for j in self._jobs.values())

    def checkpoints(self):
        """Modèles de ComfyUI (il doit répondre). La liste est mémorisée : le menu reste utile quand ComfyUI est arrêté."""
        try:
            code, texte = self._salles().reseau.requete("GET", URL_COMFY + "/object_info/CheckpointLoaderSimple", delai=5)
            noms = json.loads(texte)["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
            noms = [n for n in noms if isinstance(n, str) and 0 < len(n) < 200 and ".." not in n][:100] if code == 200 else []
        except (ia.ErreurReseau, ValueError, KeyError, IndexError, TypeError):
            return []
        if noms and noms != self.checkpoints_connus():
            try:
                t = self.centre.config.chemin("images_checkpoints.json")
                with open(t + ".tmp", "w", encoding="utf-8") as f:
                    json.dump({"noms": noms}, f, ensure_ascii=False)
                os.replace(t + ".tmp", t)
            except OSError:
                journal.warning("images_checkpoints.json non écrit")
        return noms

    def checkpoints_connus(self):
        """Derniers modèles vus quand ComfyUI tournait (vide si jamais vu)."""
        try:
            with open(self.centre.config.chemin("images_checkpoints.json"), encoding="utf-8") as f:
                d = json.load(f)
            return [n for n in d["noms"] if isinstance(n, str) and 0 < len(n) < 200 and ".." not in n][:100]
        except (OSError, ValueError, KeyError, TypeError):
            return []

    def modeles_xai(self):
        """Modèles d'IMAGES du compte xAI : les identifiants « grok-imagine-image* » de GET /v1/models (jamais les vidéos)."""
        t0, cache = self._cache_modeles_xai
        if cache is not None and self.horloge() - t0 < 600:
            return cache
        defaut = [MOTEURS["xai"]["modele"]]
        cle = self._salles().cles.lire("xai")
        if not cle:
            return defaut
        try:
            code, texte = self._salles().reseau.requete("GET", URL_XAI_MODELES, {"Authorization": "Bearer " + cle}, delai=15)
            ids = [m["id"] for m in json.loads(texte)["data"] if isinstance(m, dict) and isinstance(m.get("id"), str)] if code == 200 else []
        except (ia.ErreurReseau, ValueError, KeyError, TypeError):
            ids = []
        finally:
            del cle
        liste = sorted({i for i in ids if i.startswith("grok-imagine-image") and MODELE_OK.match(i)})
        liste = liste or defaut
        if MOTEURS["xai"]["modele"] in liste:                    # le modèle par défaut en premier
            liste.remove(MOTEURS["xai"]["modele"])
            liste.insert(0, MOTEURS["xai"]["modele"])
        self._cache_modeles_xai = (self.horloge(), liste)
        return liste

    # ----- ce que l'écran affiche avant tout choix ---------------------------------------------------------------------------

    def _dispo(self, moteur):
        m = MOTEURS[moteur]
        if not m["nuage"]:
            if self.centre.mode_jeu_actif():
                return False, "Le Mode jeu est actif : la carte graphique est réservée au jeu, aucune création locale. Rallumez d'abord Crew ou LM Studio."
            if not self._comfy_repond():
                ok, raison = self._proc().installe()          # il démarrera tout seul, à la demande : il suffit qu'il soit installé
                if not ok:
                    return False, raison
            if self.horloge() - self._liberer_404 < 600 and self._chef_charge():
                return False, "Libérez la carte graphique d'abord (page Chef d'équipe ou Mode jeu) : cette version de Crew ne sait pas le faire toute seule."
            return True, ""
        ok, msg = self._salles().politique.nuage_autorise()
        if not ok:
            return False, msg
        if not self._salles().cles.presente(m["fournisseur"]):
            return False, f"Clé {self._salles().cles.nom(m['fournisseur'])} absente (variables d'environnement Windows)."
        if moteur == "gemini" and self.horloge() - self._quota_gemini < QUOTA_GEMINI_DUREE:
            return False, "Le palier gratuit de Google n'inclut pas la génération d'images (facturation Google requise)."
        ok, msg = self.centre.couts.peut_utiliser("images", self._salles().mode_crew())
        if not ok:
            return False, msg
        return True, ""

    def _prefs(self):
        try:
            with open(self.centre.config.chemin("images_prefs.json"), encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _noter_choix(self, utilisateur, moteur, modele, taille):
        with self._verrou:
            d = self._prefs()
            d[str(utilisateur)[:80]] = {"moteur": moteur, "modele": modele if MODELE_OK.match(modele or "") else "", "taille": taille}
            try:
                t = self.centre.config.chemin("images_prefs.json")
                with open(t + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False)
                os.replace(t + ".tmp", t)
            except OSError:
                journal.warning("images_prefs.json non écrit")

    def options(self, utilisateur="local"):
        self.centre.assurer_etats()
        moteurs = []
        for ident in ORDRE:
            m = MOTEURS[ident]
            ok, raison = self._dispo(ident)
            if ident == "local":
                modeles = (self.checkpoints() or self.checkpoints_connus()) if ok and self._comfy_repond() else (self.checkpoints_connus() if ok else [])
            elif ident == "xai":
                modeles = self.modeles_xai() if ok else [m["modele"]]
            else:
                modeles = [m["modele"]]
            moteurs.append({"id": ident, "libelle": m["libelle"], "nuage": m["nuage"], "groupe": "Nuage" if m["nuage"] else "Local", "disponible": ok, "raison": raison,
                            "usd_image": m["usd_image"], "tarif_verifie": ident == "xai", "modeles": modeles, "demarrage_auto": ident == "local"})
        dispo = {m["id"]: m for m in moteurs if m["disponible"]}
        dernier = self._prefs().get(str(utilisateur)[:80]) or {}
        comfy_repond = self._comfy_repond()
        defaut = dernier.get("moteur") if dernier.get("moteur") in dispo else (
            "local" if "local" in dispo and comfy_repond else ("xai" if "xai" in dispo else ("local" if "local" in dispo else next(iter(dispo), ""))))
        modele = dernier.get("modele") if defaut == dernier.get("moteur") and dernier.get("modele") in (dispo.get(defaut) or {}).get("modeles", []) else ""
        return {"moteurs": moteurs, "tailles": [{"id": k, "libelle": v} for k, v in TAILLES.items()], "defaut": defaut, "modele_defaut": modele,
                "taille_defaut": dernier.get("taille") if dernier.get("taille") in TAILLES else "carre",
                "seuil_usd": self.centre.config.seuil_image_usd, "max_images": MAX_IMAGES_PAR_DEMANDE,
                "chef_a_liberer": bool(defaut == "local" and self._chef_charge()),
                "comfy": {"repond": comfy_repond, "manuel": bool(comfy_repond and not self._proc().demarre_par_le_centre)},
                "confirmation_locale": self.texte_confirmation_locale()}

    def texte_confirmation_locale(self):
        """Le texte de la fenêtre de confirmation d'une création locale (un seul clic)."""
        return "Pour créer cette image en local : " + (TEXTE_CHEF if self._chef_charge() else TEXTE_SANS_CHEF)

    def estimer(self, moteur, n=1):
        if moteur not in MOTEURS:
            raise ErreurImage("Moteur d'images inconnu.")
        n = max(1, min(MAX_IMAGES_PAR_DEMANDE, int(n) if isinstance(n, int) and not isinstance(n, bool) else 1))
        usd = round(MOTEURS[moteur]["usd_image"] * n, 4)
        seuil = self.centre.config.seuil_image_usd
        fiable = moteur == "xai"
        return {"usd": usd, "n": n, "depasse": usd > seuil, "seuil_usd": seuil, "fiable": fiable, "chef_a_liberer": bool(moteur == "local" and self._chef_charge()),
                "confirmation_locale": self.texte_confirmation_locale() if moteur == "local" else "",
                "texte": "Gratuit (local)" if usd == 0 else f"≈ {usd:.3f} $ pour {n} image{'s' if n > 1 else ''}" + ("" if fiable else " (estimation indicative)")}

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
        chemin = self._chemin(ident, ext)
        with open(chemin + ".tmp", "wb") as f:
            f.write(octets)
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

    # ----- demandes : contrôles, file d'attente ----------------------------------------------------------------------------------

    def lancer(self, moteur, prompt, taille="carre", n=1, prive=False, modele="", confirme_depassement=False, confirme_liberation=False,
               laisser_libre=False, session="", conversation=None, salle=None, utilisateur="local", proposition=None, arreter_comfyui=False):
        """Contrôles, puis mise en file (une création à la fois). Renvoie l'état de la tâche. `prive` : contenu confidentiel (le serveur refuse alors le nuage)."""
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
            raise ErreurImage("Contenu confidentiel : seul le moteur local (ComfyUI) peut créer cette image (rien ne doit quitter le PC).", 403)
        ok, raison = self._dispo(moteur)
        if not ok:
            raise ErreurImage(raison, 403)
        modele = str(modele or "")
        if moteur == "local":
            if self._comfy_repond():
                noms = self.checkpoints()
                if not noms:
                    raise ErreurImage("ComfyUI n'a aucun modèle (checkpoint) installé.", 409)
            else:
                noms = self.checkpoints_connus()                   # ComfyUI est arrêté : on s'appuie sur les derniers modèles vus
            modele = (modele if modele in noms else noms[0]) if noms else (modele if MODELE_OK.match(modele) else "")     # aucun connu : choisi au démarrage
        elif moteur == "xai":
            liste = self.modeles_xai()
            modele = modele if modele in liste else liste[0]
        else:
            modele = m["modele"]
        est = self.estimer(moteur, n)
        if m["nuage"] and est["depasse"] and not confirme_depassement:
            raise ErreurImage(f"Coût estimé {est['usd']:.3f} $ : au-dessus du seuil de {est['seuil_usd']:.2f} $. Confirmez pour créer.", 402, depassement=True)
        if moteur == "local":
            if (self._chef_charge() or not self._comfy_repond()) and not confirme_liberation:         # un seul clic de confirmation, avant toute libération
                raise ErreurImage(self.texte_confirmation_locale() + " Continuer ?", 409, liberation=True)
        self._noter_choix(utilisateur, moteur, modele, taille)
        with self._verrou:
            ident = secrets.token_hex(8)
            job = {"id": ident, "etat": "attente", "fait": 0, "sur": n, "images": [], "message": "", "moteur": moteur, "modele": modele, "etape": "En attente…",
                   "conversation": conversation, "salle": salle, "debut": self.horloge(), "annule": False, "taille": taille}
            self._jobs[ident] = job
            self._params[ident] = {"prompt": prompt, "taille": taille, "n": n, "prive": bool(prive), "modele": modele, "laisser_libre": bool(laisser_libre), "proposition": proposition,
                                  "arreter_comfyui": bool(arreter_comfyui)}
            self._file.append(ident)
            for k in [k for k, j in self._jobs.items() if j["etat"] not in ("attente", "en_cours") and self.horloge() - j["debut"] > 3600]:
                self._jobs.pop(k, None)
                self._params.pop(k, None)
            if self._fil is None or not self._fil.is_alive():
                self._fil = threading.Thread(target=self._boucle, name="centre-image", daemon=True)
                self._fil.start()
        self.centre.recus.ajouter("image", "demandee", moteur=moteur, n=n, prive=bool(prive), session=session)     # jamais le texte de la demande
        return self.etat_job(ident)

    def etat_job(self, ident):
        with self._verrou:
            j = self._jobs.get(ident)
            if j is None:
                raise ErreurImage("Tâche inconnue ou trop ancienne.", 404)
            return self._public(j)

    def _public(self, j):
        sortie = {k: (list(v) if isinstance(v, list) else v) for k, v in j.items() if k not in ("debut", "annule")}
        sortie["position"] = (self._file.index(j["id"]) + 1) if j["id"] in self._file else 0
        return sortie

    def jobs_de(self, conversation):
        """Tâches (en attente ou en cours) d'une conversation : l'écran les retrouve à la réouverture."""
        with self._verrou:
            return [self._public(j) for j in self._jobs.values() if j["conversation"] == conversation and j["etat"] in ("attente", "en_cours")]

    def annuler(self, ident):
        with self._verrou:
            j = self._jobs.get(ident)
            if j is None:
                raise ErreurImage("Tâche inconnue ou trop ancienne.", 404)
            if j["etat"] == "attente":
                j["etat"], j["message"] = "annule", "Annulée."
                if ident in self._file:
                    self._file.remove(ident)
            elif j["etat"] == "en_cours":
                j["annule"] = True
            return self._public(j)

    def attendre(self, ident, delai=30):
        """Pour les tests : attend la fin de la tâche."""
        fin = time.time() + delai
        while time.time() < fin:
            if self.etat_job(ident)["etat"] not in ("attente", "en_cours"):
                break
            time.sleep(0.01)
        return self.etat_job(ident)

    # ----- exécution (un fil, une création à la fois) -----------------------------------------------------------------------------

    def _boucle(self):
        while True:
            with self._verrou:
                if not self._file:
                    return
                ident = self._file.pop(0)
                job = self._jobs[ident]
                if job["etat"] != "attente":
                    continue
                job["etat"], job["etape"] = "en_cours", "Démarrage…"
                p = self._params[ident]
            try:
                self._executer(job, p)
            except Exception as e:                   # jamais de plantage silencieux ni de secret dans le message
                journal.exception("Génération d'image impossible")
                with self._verrou:
                    job["etat"], job["message"] = "erreur", masquer(f"Erreur inattendue : {e}")[:400]
            finally:
                self.centre.recus.ajouter("image", {"termine": "ok", "erreur": "erreur", "annule": "annulee"}.get(job["etat"], job["etat"]), moteur=job["moteur"], images=len(job["images"]))

    def _etape(self, job, texte):
        with self._verrou:
            job["etape"] = texte

    def _executer(self, job, p):
        m = MOTEURS[job["moteur"]]
        etat, message = "termine", ""
        try:
            if job["moteur"] == "local":
                self._preparer_cycle(job, p)
            for i in range(p["n"]):
                if job["annule"]:
                    break
                self._etape(job, f"Création de l'image {i + 1} sur {p['n']}…")
                octets, cout_reel = self._une_image(job["moteur"], p["prompt"], p["taille"], p["modele"], job)
                usd = cout_reel if cout_reel is not None else m["usd_image"]
                meta = self._enregistrer(octets, {"prompt": p["prompt"], "moteur": job["moteur"], "moteur_libelle": m["libelle"], "modele": p["modele"],
                                                  "taille": p["taille"], "prive": p["prive"], "cout_usd": usd, "cout_reel": cout_reel is not None})
                if usd > 0:
                    self.centre.couts.enregistrer("images", usd, detail=f"{job['moteur']} image", estime=cout_reel is None)
                with self._verrou:
                    job["images"].append({k: meta[k] for k in ("id", "type", "ts", "cout_usd")})
                    job["fait"] = len(job["images"])
            if job["annule"]:
                etat, message = "annule", "Annulée."
        except ErreurImage as e:
            etat, message = ("annule", "Annulée.") if job["annule"] else ("erreur", masquer(str(e))[:400])
        except Exception as e:                   # jamais de plantage silencieux ni de secret dans le message
            journal.exception("Génération d'image impossible")
            etat, message = "erreur", masquer(f"Erreur inattendue : {e}")[:400]
        finally:
            if job["moteur"] == "local":
                self._clore_cycle(job, p)                       # TOUJOURS, AVANT d'annoncer la fin : la carte est rendue quand l'écran voit « terminé »
        with self._verrou:
            total = (message + " " + job["message"]).strip() if job["message"] else message
        self._apres_job(dict(job, etat=etat, message=total), p)        # l'image est dans la conversation AVANT que l'écran voie « terminé »
        with self._verrou:
            job["etat"], job["message"] = etat, total

    # ----- carte graphique partagée avec le chef de Crew (c'est Crew qui décharge et recharge, jamais le Centre) -----------------------

    def _attendre_chef(self, job, libelle):
        fin = time.time() + 180
        while time.time() < fin:
            self.dormir(self.pauses)
            try:
                info = self.centre.crew.lire_chef(crew_actif=True)
            except self.centre.C.ErreurCrew:
                continue
            ch = info.changement
            if ch is None or ch["etat"] == "termine":
                return
            if ch["etat"] == "echec":
                raise ErreurImage(f"{libelle} : {ch['message'] or 'Crew a échoué.'}", 502)
            self._etape(job, ch["etape"] or libelle)
        raise ErreurImage(f"{libelle} : Crew met trop de temps (plus de 3 minutes).", 504)

    def _liberer_carte(self, job):
        """Si le chef de Crew occupe la carte graphique : Crew le décharge (POST /chef/liberer). Note dans le cycle qu'il faudra le rendre."""
        if not self._crew_actif() or not self._chef_charge():
            return
        self._etape(job, "Libération de la carte graphique par Crew…")
        try:
            self.centre.crew.liberer_chef()
        except self.centre.C.ErreurDemande as e:
            if e.code == 404:
                self._liberer_404 = self.horloge()
                raise ErreurImage("Libérez la carte graphique d'abord (page Chef d'équipe ou Mode jeu) : cette version de Crew ne sait pas le faire toute seule.", 409)
            if e.code == 503:
                return                                            # LM Studio arrêté : rien à libérer
            raise ErreurImage(f"{e} Réessayez dans un instant.", 409)        # 409 : travail Crew en cours, affiché tel quel
        except self.centre.C.ErreurCrew as e:
            raise ErreurImage(str(e), 502)
        self._cycle["liberee"] = True                             # dès que Crew a accepté : même si la suite échoue, le « finally » rendra le chef
        self._attendre_chef(job, "Libération de la carte graphique")

    def _preparer_cycle(self, job, p):
        """Début d'une création locale : Mode jeu refusé, chef libéré (une fois par cycle), ComfyUI démarré s'il ne tourne pas."""
        if self.centre.mode_jeu_actif():
            raise ErreurImage("Le Mode jeu est actif : la carte graphique est réservée au jeu, aucune création locale.", 409)
        if not self._cycle["liberee"]:
            self._liberer_carte(job)
        comfy = self._proc()
        if self._comfy_repond():
            comfy.noter_activite()
        else:
            self._etape(job, "Démarrage de ComfyUI…")
            try:
                comfy.demarrer()
            except ErreurComfyUI as e:
                raise ErreurImage(str(e), e.code)
        with self._verrou:
            job["demarre_par_le_centre"] = bool(comfy.demarre_par_le_centre)
        noms = self.checkpoints()                                 # ComfyUI tourne : le modèle demandé doit exister (sinon le premier)
        if not noms:
            raise ErreurImage("ComfyUI n'a aucun modèle (checkpoint) installé.", 409)
        if p["modele"] not in noms:
            p["modele"] = noms[0]
            with self._verrou:
                job["modele"] = noms[0]

    def _clore_cycle(self, job, p):
        """Fin d'une création locale (TOUJOURS appelée : succès, échec ou annulation). S'il reste une création locale en attente, on garde ComfyUI
        et la carte pour elle (un seul cycle). Sinon : arrêt de ComfyUI (s'il est au Centre, ou si demandé), puis rechargement du chef par Crew
        — sauf Mode jeu, Crew arrêté ou « laisser la carte libre ensuite »."""
        comfy = self._proc()
        with self._verrou:
            autre_locale = any(self._jobs[i]["moteur"] == "local" for i in self._file if i in self._jobs)
        if autre_locale:
            comfy.noter_activite()
            return
        liberee = self._cycle["liberee"]
        try:
            self._arreter_ou_liberer_comfy(job, p, comfy, liberee)
        finally:
            self._cycle["liberee"] = False                          # le cycle est terminé quoi qu'il arrive
        if not liberee:
            return
        if p.get("laisser_libre") or self.centre.mode_jeu_actif() or not self._crew_actif():
            return                                                  # choix de l'utilisateur, Mode jeu ou Crew arrêté : on ne recharge rien
        self._etape(job, "Rechargement du chef…")
        try:
            self.centre.crew.reprendre_chef()
        except self.centre.C.ErreurCrew as e:
            journal.warning("Crew n'a pas rechargé le chef : %s", e)
            with self._verrou:
                job["message"] = (job["message"] + " " if job["message"] else "") + "Crew n'a pas pu recharger le chef : utilisez la page Chef d'équipe."
            return
        try:
            self._attendre_chef(job, "Rechargement du chef")
        except ErreurImage as e:
            with self._verrou:
                job["message"] = (job["message"] + " " if job["message"] else "") + masquer(str(e))[:200]
            return
        with self._verrou:
            job["message"] = (job["message"] + " " if job["message"] else "") + "Chef rechargé : Crew est de nouveau disponible."

    def _arreter_ou_liberer_comfy(self, job, p, comfy, liberee):
        if not (comfy.demarre_par_le_centre or self._comfy_repond()):
            return                                                  # ComfyUI ne tourne pas (déjà arrêté, ou arrêté par le Mode jeu)
        if comfy.demarre_par_le_centre or p.get("arreter_comfyui"):
            self._etape(job, "Arrêt de ComfyUI…")
            try:
                ferme = comfy.arreter()
            except Exception:
                journal.exception("Arrêt de ComfyUI impossible")
                ferme = False
            if not ferme:
                with self._verrou:
                    job["message"] = (job["message"] + " " if job["message"] else "") + "ComfyUI ne s'est pas arrêté : arrêtez-le depuis la page Centre."
            return
        if not liberee:
            comfy.noter_activite()
            return
        try:                                                        # lancé à la main par l'utilisateur : on le laisse tourner, mais on lui fait rendre la mémoire
            self._salles().reseau.requete("POST", URL_COMFY + "/free", None, {"unload_models": True, "free_memory": True}, delai=30)
        except ia.ErreurReseau:
            pass
        comfy.noter_activite()

    # ----- moteurs ----------------------------------------------------------------------------------------------------------------

    def _une_image(self, moteur, prompt, taille, modele, job):
        """(octets, coût réel en dollars ou None si le fournisseur ne le donne pas)."""
        m = MOTEURS[moteur]
        if moteur == "local":
            return self._comfy(prompt, taille, modele, job), None
        cle = self._salles().cles.lire(m["fournisseur"])
        if not cle:
            raise ErreurImage("Clé absente.", 403)
        try:
            if moteur == "gemini":
                entetes = {"x-goog-api-key": cle}
                corps = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
            else:
                entetes = {"Authorization": "Bearer " + cle}
                corps = {"model": modele, "prompt": prompt, "n": 1}
                if moteur == "openai":
                    corps["size"] = OPENAI_TAILLES[taille]
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
        if code == 429 and moteur == "gemini":
            self._quota_gemini = self.horloge()
            raise ErreurImage("Gemini : le palier gratuit de Google n'inclut pas la génération d'images (facturation Google requise). Rien n'a été facturé.", 402)
        if code != 200:
            raise ErreurImage(ia.message_http(m["libelle"], code, texte), 502)
        return self._decoder(moteur, texte)

    @staticmethod
    def _decoder(moteur, texte):
        cout = None
        try:
            d = json.loads(texte)
            if moteur == "gemini":
                b64 = [p["inlineData"]["data"] for c in d["candidates"] for p in c["content"]["parts"] if isinstance(p, dict) and "inlineData" in p][0]
            else:
                b64 = d["data"][0]["b64_json"]
                ticks = (d.get("usage") or {}).get("cost_in_usd_ticks") if moteur == "xai" and isinstance(d.get("usage"), dict) else None
                if isinstance(ticks, (int, float)) and not isinstance(ticks, bool) and 0 <= ticks < 1e13:
                    cout = round(ticks * TICK_USD, 6)
            octets = base64.b64decode(b64, validate=True)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError, binascii.Error):
            raise ErreurImage("Réponse du moteur d'images illisible (aucune image reçue).", 502)
        if len(octets) > MAX_OCTETS:
            raise ErreurImage("Image reçue trop lourde.", 502)
        return octets, cout

    def _comfy(self, prompt, taille, checkpoint, job):
        table = self._famille_table()
        fam = famille_du_modele(checkpoint, table)
        graphe = graphe_comfy(fam, table[fam], checkpoint, prompt, taille, secrets.randbelow(2 ** 32))
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
                if job["annule"]:
                    reseau.requete("POST", URL_COMFY + "/interrupt", None, {}, delai=5)
                    raise ErreurImage("Annulée.", 499)
                code, texte = reseau.requete("GET", f"{URL_COMFY}/history/{pid}", delai=10)
                histoire = json.loads(texte).get(pid) if code == 200 else None
                if histoire and histoire.get("outputs"):
                    for sortie in histoire["outputs"].values():
                        for im in sortie.get("images", []):
                            nom, sous, genre = str(im.get("filename", "")), str(im.get("subfolder", "")), str(im.get("type", "output"))
                            if not re.match(r"^[\w.\-]{1,120}$", nom) or not re.match(r"^[\w.\-/]{0,80}$", sous) or ".." in sous or genre not in ("output", "temp", "input"):
                                continue
                            code, octets = reseau.requete("GET", f"{URL_COMFY}/view?" + urlencode({"filename": nom, "subfolder": sous, "type": genre}), delai=30, octets=True)
                            if code == 200:
                                return octets
                    raise ErreurImage("ComfyUI n'a produit aucune image.", 502)
                if histoire and histoire.get("status", {}).get("status_str") == "error":
                    raise ErreurImage("ComfyUI a signalé une erreur pendant la création (mémoire vidéo ? modèle ?).", 502)
                self.dormir(self.pauses)
            raise ErreurImage("ComfyUI met trop de temps (plus de 10 minutes).", 504)
        except ia.ErreurReseau as e:
            raise ErreurImage(str(e), 502)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ErreurImage("Réponse de ComfyUI illisible.", 502)

    # ----- fin de tâche : l'image revient DANS la conversation de la salle --------------------------------------------------------

    def _apres_job(self, job, p):
        cid = job.get("conversation")
        if not cid or job["etat"] not in ("termine", "erreur", "annule"):
            return
        try:
            self._salles().ajouter_resultat_image(cid, job, p)
        except Exception:
            journal.exception("Image non ajoutée à la conversation")
