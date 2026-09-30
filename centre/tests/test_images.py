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


URL_XAI_MODELES = "https://api.x.ai/v1/models"


class Moteurs:
    """Faux moteurs : enregistre les appels et répond comme les vrais (corps JSON)."""

    def __init__(self, reseau):
        self.appels = []
        self.ordre = []            # suites d'événements (libération, création, free…) pour vérifier l'arbitrage de la carte graphique
        self.comfy = True
        self.erreur = {}           # url -> (code, texte)
        self.contenu = {}          # url -> octets à renvoyer à la place du PNG
        self.ticks = 200_000_000   # coût réel xAI (1 tick = 1e-10 $) ; None : pas de coût dans la réponse
        self.modeles_xai = ["grok-imagine-image-2.0", "grok-imagine-video", "grok-imagine-image", "grok-imagine-image-quality", "grok-4", "grok-imagine-video-pro"]
        reseau.requete = self.requete

    def requete(self, methode, url, entetes=None, corps=None, delai=30, octets=False, max_octets=0):
        self.appels.append((methode, url, corps, dict(entetes or {})))
        if url in self.erreur:
            return self.erreur[url]
        img = self.contenu.get(url, png())
        if url == URL_XAI_MODELES:
            return 200, json.dumps({"data": [{"id": m} for m in self.modeles_xai]})
        if url == URL_XAI:
            d = {"data": [{"b64_json": b64(img), "mime_type": "image/jpeg"}]}
            if self.ticks is not None:
                d["usage"] = {"cost_in_usd_ticks": self.ticks}
            return 200, json.dumps(d)
        if url == URL_OPENAI:
            return 200, json.dumps({"data": [{"b64_json": b64(img)}]})
        if url == URL_GEMINI:
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}, {"inlineData": {"mimeType": "image/png", "data": b64(img)}}]}}]})
        if url.startswith(COMFY):
            if not self.comfy:
                return None, "connexion refusée"
            if url.endswith("/system_stats"):
                return 200, "{}"
            if url.endswith("/object_info/CheckpointLoaderSimple"):
                return 200, json.dumps({"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["sdxl_base.safetensors", "sd15_dream.safetensors", "flux1-dev-fp8.safetensors"]]}}}})
            if url.endswith("/prompt"):
                self.ordre.append("creation")
                return 200, json.dumps({"prompt_id": "abc123"})
            if url.endswith("/free"):
                self.ordre.append("free")
                return 200, "{}"
            if url.endswith("/interrupt"):
                self.ordre.append("interrupt")
                return 200, "{}"
            if "/history/" in url:
                return 200, json.dumps({"abc123": {"outputs": {"7": {"images": [{"filename": "centre_0001_.png", "subfolder": "", "type": "output"}]}}}})
            if "/view?" in url:
                return 200, (self.contenu.get("view", png()) if octets else "")
        return None, "connexion refusée"


@pytest.fixture
def moteurs(reseau, centre, simulateur):
    m = Moteurs(reseau)
    allumer(centre, simulateur)
    centre.images.pauses = 0.0
    centre.images.dormir = lambda s: None
    centre.comfyui.dormir = lambda s: None
    centre.comfyui.pause_memoire = 0.0
    def scripts(sens):                                              # les deux scripts fournis : ils démarrent / arrêtent le faux ComfyUI
        m.comfy = sens == "demarrer"
        m.ordre.append("comfy_demarre" if sens == "demarrer" else "comfy_arrete")
    simulateur.comfy_crochet = scripts
    simulateur.comfy_actif = True                                   # par défaut : ComfyUI lancé À LA MAIN par l'utilisateur (voir « auto » pour le cas normal)
    simulateur.cles.update({"OPENAI_API_KEY": SECRET, "GEMINI_API_KEY": SECRET + "g", "XAI_API_KEY": SECRET + "x"})
    vrai = simulateur._crew_chef_operation
    def operation(op):
        rep = vrai(op)
        if rep[0] == 202:                                           # seulement si Crew a accepté
            m.ordre.append("liberer" if op == "liberer" else "reprendre")
        return rep
    simulateur._crew_chef_operation = operation
    return m


def auto(moteurs, simulateur):
    """Le cas normal : ComfyUI est arrêté, c'est le Centre qui le démarre (par le script) puis l'arrête."""
    moteurs.comfy = False
    simulateur.comfy_actif = False


def suivre_chef(centre):
    """Crew décharge / recharge le chef en arrière-plan : on le laisse finir en lisant GET /chef comme le fait l'écran."""
    for _ in range(4):
        centre.crew.lire_chef(crew_actif=True)


def creer(centre, moteur, **kw):
    kw.setdefault("prompt", "un chat astronaute")
    if moteur == "local":
        kw.setdefault("confirme_liberation", True)           # le chef de Crew occupe la carte : l'écran demande d'abord la confirmation
    j = centre.images.lancer(moteur, **kw)
    return centre.images.attendre(j["id"])


# ----- options et estimation ---------------------------------------------------------------------------------------------

def test_options_groupes_prix_modeles_et_raisons(centre, simulateur, reseau):
    m = Moteurs(reseau)
    allumer(centre, simulateur)
    centre.images.pauses = 0.0
    o = centre.images.options()
    mo = {x["id"]: x for x in o["moteurs"]}
    assert [x["id"] for x in o["moteurs"]] == ["xai", "gemini", "openai", "local"]                 # ordre : Nuage (xAI, Gemini, OpenAI) puis Local
    assert [mo[i]["groupe"] for i in ("xai", "gemini", "openai", "local")] == ["Nuage", "Nuage", "Nuage", "Local"]
    assert mo["local"]["disponible"] and not mo["local"]["nuage"] and mo["local"]["usd_image"] == 0 and mo["xai"]["usd_image"] == 0.02
    assert not mo["openai"]["disponible"] and "OPENAI_API_KEY" in mo["openai"]["raison"] and not mo["xai"]["disponible"]
    assert mo["local"]["modeles"] == ["sdxl_base.safetensors", "sd15_dream.safetensors", "flux1-dev-fp8.safetensors"]
    simulateur.cles["XAI_API_KEY"] = SECRET
    o = centre.images.options()
    mo = {x["id"]: x for x in o["moteurs"]}
    assert mo["xai"]["disponible"] and mo["xai"]["modeles"] == ["grok-imagine-image", "grok-imagine-image-2.0", "grok-imagine-image-quality"]   # jamais les vidéos ni grok-4
    assert mo["openai"]["modeles"] == ["gpt-image-1"] and mo["gemini"]["modeles"] == ["gemini-2.5-flash-image"]
    m.comfy = False
    mo = {x["id"]: x for x in centre.images.options()["moteurs"]}
    assert mo["local"]["disponible"] and mo["local"]["demarrage_auto"] and not mo["local"]["raison"]      # il démarrera tout seul, à la demande
    assert mo["local"]["modeles"] == ["sdxl_base.safetensors", "sd15_dream.safetensors", "flux1-dev-fp8.safetensors"]   # derniers modèles vus (mémorisés)
    simulateur.comfy_installe = False
    mo = {x["id"]: x for x in centre.images.options()["moteurs"]}
    assert not mo["local"]["disponible"] and "introuvable" in mo["local"]["raison"]


def test_choix_par_defaut_et_dernier_choix_par_utilisateur(centre, simulateur, reseau, moteurs):
    assert centre.images.options()["defaut"] == "local"                                     # ComfyUI s'il répond
    moteurs.comfy = False
    assert centre.images.options()["defaut"] == "xai"                                       # sinon xAI
    moteurs.comfy = True
    j = centre.images.lancer("xai", "x", modele="grok-imagine-image-quality", taille="paysage", utilisateur="antoine@exemple.com")
    centre.images.attendre(j["id"])
    o = centre.images.options("antoine@exemple.com")
    assert (o["defaut"], o["modele_defaut"], o["taille_defaut"]) == ("xai", "grok-imagine-image-quality", "paysage")
    o = centre.images.options("autre@exemple.com")                                         # un autre utilisateur n'hérite pas de ce choix
    assert (o["defaut"], o["modele_defaut"]) == ("local", "")
    assert "x" not in open(centre.config.chemin("images_prefs.json")).read().replace("xai", "").replace("paysage", "").replace("exemple", "").replace("max", "")


def test_moteur_choisi_indisponible_le_defaut_retombe(centre, simulateur, reseau, moteurs):
    centre.images.attendre(centre.images.lancer("xai", "x")["id"])
    del simulateur.cles["XAI_API_KEY"]
    assert centre.images.options()["defaut"] == "local"


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


def test_xai_modele_par_defaut_et_cout_reel_en_ticks(centre, moteurs):
    j = creer(centre, "xai")
    assert j["etat"] == "termine" and j["images"][0]["cout_usd"] == pytest.approx(0.02)                  # 200 000 000 ticks × 1e-10 = 0,02 $
    corps = [a for a in moteurs.appels if a[1] == URL_XAI][0][2]
    assert corps == {"model": "grok-imagine-image", "prompt": "un chat astronaute", "n": 1, "response_format": "b64_json"}
    g = centre.images.lister()[0]
    assert g["cout_usd"] == pytest.approx(0.02) and g["cout_reel"] is True and g["modele"] == "grok-imagine-image"
    assert centre.couts.totaux()["aujourdhui"]["par_ia"]["images"] == pytest.approx(0.02, abs=1e-6)
    assert json.loads(open(centre.config.chemin("depenses.jsonl")).read().splitlines()[0])["estime"] is False     # coût RÉEL


def test_xai_cout_reel_different_de_l_estimation(centre, moteurs):
    moteurs.ticks = 350_000_000
    j = creer(centre, "xai", modele="grok-imagine-image-quality")
    assert j["images"][0]["cout_usd"] == pytest.approx(0.035)
    assert [a for a in moteurs.appels if a[1] == URL_XAI][0][2]["model"] == "grok-imagine-image-quality"


def test_xai_sans_cout_dans_la_reponse_repli_sur_l_estimation(centre, moteurs):
    moteurs.ticks = None
    j = creer(centre, "xai")
    assert j["images"][0]["cout_usd"] == 0.02 and centre.images.lister()[0]["cout_reel"] is False
    assert json.loads(open(centre.config.chemin("depenses.jsonl")).read().splitlines()[0])["estime"] is True


def test_xai_modele_inconnu_ou_video_remplace_par_le_defaut(centre, moteurs):
    creer(centre, "xai", modele="grok-imagine-video")
    assert [a for a in moteurs.appels if a[1] == URL_XAI][0][2]["model"] == "grok-imagine-image"


def test_gemini_429_palier_gratuit_message_propre_et_moteur_grise(centre, moteurs):
    moteurs.erreur[URL_GEMINI] = (429, json.dumps({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": f"Quota exceeded {SECRET}"}}))
    j = creer(centre, "gemini")
    assert j["etat"] == "erreur" and "palier gratuit de Google" in j["message"] and "facturation" in j["message"] and SECRET not in j["message"]
    assert "RESOURCE_EXHAUSTED" not in j["message"] and "Rien n'a été facturé" in j["message"]
    assert centre.couts.totaux()["aujourdhui"]["total"] == 0
    mo = {x["id"]: x for x in centre.images.options()["moteurs"]}
    assert not mo["gemini"]["disponible"] and "palier gratuit" in mo["gemini"]["raison"]
    with pytest.raises(ErreurImage) as e:
        centre.images.lancer("gemini", "encore")
    assert e.value.code == 403


def test_plusieurs_images_un_appel_par_image_et_cout_compte(centre, moteurs):
    j = creer(centre, "openai", n=3, confirme_depassement=True)
    assert j["fait"] == 3 and len([a for a in moteurs.appels if a[1] == URL_OPENAI]) == 3
    t = centre.couts.totaux()["aujourdhui"]
    assert t["par_ia"]["images"] == pytest.approx(0.126, abs=1e-4)
    assert json.loads(open(centre.config.chemin("depenses.jsonl")).read().splitlines()[0])["estime"] is True


def test_local_comfyui(centre, moteurs):
    j = creer(centre, "local", n=2, taille="paysage", modele="sd15_dream.safetensors")
    assert j["etat"] == "termine" and j["fait"] == 2
    graphe = [a for a in moteurs.appels if a[1] == COMFY + "/prompt"][0][2]["prompt"]
    assert graphe["1"]["inputs"]["ckpt_name"] == "sd15_dream.safetensors" and graphe["2"]["inputs"]["text"] == "un chat astronaute"
    assert (graphe["4"]["inputs"]["width"], graphe["4"]["inputs"]["height"]) == (768, 512)              # SD 1.5 : petit format
    assert centre.couts.totaux()["aujourdhui"]["total"] == 0                                           # gratuit
    assert not [a for a in moteurs.appels if a[1].startswith("https://")]                              # rien n'est sorti du PC


def test_modele_local_inconnu_remplace_par_le_premier(centre, moteurs):
    creer(centre, "local", modele="../../etc/passwd")
    assert [a for a in moteurs.appels if a[1] == COMFY + "/prompt"][0][2]["prompt"]["1"]["inputs"]["ckpt_name"] == "sdxl_base.safetensors"


# ----- familles de modèles ComfyUI ----------------------------------------------------------------------------------------------

def graphe_pour(centre, moteurs, modele, taille="carre"):
    creer(centre, "local", modele=modele, taille=taille)
    return [a for a in moteurs.appels if a[1] == COMFY + "/prompt"][-1][2]["prompt"]


def test_famille_sdxl(centre, moteurs):
    g = graphe_pour(centre, moteurs, "sdxl_base.safetensors")
    assert (g["4"]["inputs"]["width"], g["4"]["inputs"]["height"]) == (1024, 1024)
    assert g["5"]["inputs"]["steps"] == 28 and 6 <= g["5"]["inputs"]["cfg"] <= 7 and g["3"]["class_type"] == "CLIPTextEncode"
    g = graphe_pour(centre, moteurs, "sdxl_base.safetensors", "portrait")
    assert (g["4"]["inputs"]["width"], g["4"]["inputs"]["height"]) == (832, 1216)
    g = graphe_pour(centre, moteurs, "sdxl_base.safetensors", "paysage")
    assert (g["4"]["inputs"]["width"], g["4"]["inputs"]["height"]) == (1216, 832)


def test_famille_sd15(centre, moteurs):
    g = graphe_pour(centre, moteurs, "sd15_dream.safetensors")
    assert (g["4"]["inputs"]["width"], g["4"]["inputs"]["height"]) == (512, 512) and g["5"]["inputs"]["steps"] == 25 and g["5"]["inputs"]["cfg"] == 7.0
    assert (graphe_pour(centre, moteurs, "sd15_dream.safetensors", "portrait")["4"]["inputs"]["height"]) == 768


def test_famille_flux_sans_consigne_negative_cfg_1(centre, moteurs):
    g = graphe_pour(centre, moteurs, "flux1-dev-fp8.safetensors")
    assert g["5"]["inputs"]["cfg"] == 1.0 and g["3"]["class_type"] == "ConditioningZeroOut"                # pas de texte négatif
    assert g["8"]["class_type"] == "FluxGuidance" and g["5"]["inputs"]["positive"] == ["8", 0]
    assert not [n for n in g.values() if n["class_type"] == "CLIPTextEncode" and "filigrane" in n["inputs"].get("text", "")]


def test_famille_inconnue_sdxl_prudent(centre, moteurs, reseau):
    from centre.images import famille_du_modele, familles
    t = familles()
    assert famille_du_modele("mon-modele-mystere.safetensors", t) == "sdxl"
    assert [famille_du_modele(n, t) for n in ("FLUX.1-schnell", "SDXL-turbo", "v1-5-pruned-emaonly.ckpt", "juggernautXL_v9", "realisticVision_sd1.5")] == ["flux", "sdxl", "sd15", "sdxl", "sd15"]


def test_table_des_familles_modifiable_dans_un_fichier(centre, moteurs):
    with open(centre.config.chemin("familles_comfy.json"), "w", encoding="utf-8") as f:
        json.dump({"sdxl": {"pas": 40, "cfg": 5, "tailles": {"carre": [896, 896], "portrait": [1, 1], "paysage": "x"}, "sampler": "euler; drop table", "motifs": ["base"]},
                   "../mauvais": {"pas": 1}, "nouvelle": {"motifs": ["special"], "pas": 10}}, f)
    g = graphe_pour(centre, moteurs, "sdxl_base.safetensors")
    assert (g["4"]["inputs"]["width"], g["5"]["inputs"]["steps"], g["5"]["inputs"]["cfg"]) == (896, 40, 5)
    assert g["5"]["inputs"]["sampler_name"] == "dpmpp_2m"                                              # valeur invalide ignorée
    assert graphe_pour(centre, moteurs, "sdxl_base.safetensors", "portrait")["4"]["inputs"]["height"] == 1216    # taille invalide ignorée
    from centre.images import familles
    assert "nouvelle" in familles(centre.config.dossier_donnees) and "../mauvais" not in familles(centre.config.dossier_donnees)


# ----- carte graphique partagée avec le chef de Crew --------------------------------------------------------------------------------

def test_chef_charge_demande_confirmation_puis_liberer_creer_free_reprendre(centre, simulateur, moteurs):
    R = centre.L.R
    with pytest.raises(ErreurImage) as e:
        centre.images.lancer("local", "un chat")
    assert e.value.code == 409 and e.value.extra == {"liberation": True} and "Crew libère la carte graphique" in str(e.value) and "environ 20 à 40 s" in str(e.value) and "environ 10 s" in str(e.value)
    assert moteurs.ordre == [] and simulateur.chef_operations == []                                  # rien n'a bougé sans confirmation
    assert centre.images.estimer("local")["chef_a_liberer"] is True
    j = creer(centre, "local")
    assert j["etat"] == "termine"
    assert moteurs.ordre == ["liberer", "creation", "free", "reprendre"]                               # l'ordre voulu
    assert simulateur.modeles[R.MODELE_GEMMA] == 1                                                   # déchargé puis rechargé par Crew : le chef est déjà revenu à « terminé »
    assert "Chef rechargé : Crew est de nouveau disponible." in j["message"]
    assert centre.images.lister()[0]["moteur"] == "local"


def test_le_centre_ne_touche_jamais_lm_studio(centre, simulateur, moteurs):
    avant = len(simulateur.commandes)
    creer(centre, "local")
    assert [c for c in simulateur.commandes[avant:] if "lms" in c[0].lower() or c[1:2] in (["load"], ["unload"])] == []


def test_mode_jeu_refuse_la_creation_locale_avec_une_explication(centre, simulateur, moteurs, monkeypatch):
    monkeypatch.setattr(centre, "mode_jeu_actif", lambda: True)
    with pytest.raises(ErreurImage) as e:
        creer(centre, "local", confirme_liberation=False)
    assert e.value.code == 403 and "Mode jeu" in str(e.value) and moteurs.ordre == [] and simulateur.chef_operations == []
    mo = {x["id"]: x for x in centre.images.options()["moteurs"]}
    assert not mo["local"]["disponible"] and "Mode jeu" in mo["local"]["raison"]


def test_laisser_la_carte_libre_pas_de_reprise(centre, simulateur, moteurs):
    creer(centre, "local", laisser_libre=True)
    assert moteurs.ordre == ["liberer", "creation", "free"] and simulateur.chef_operations == ["liberer"]


def test_reprise_annulee_si_le_mode_jeu_arrive_pendant_la_creation(centre, simulateur, moteurs, monkeypatch):
    etat = {"jeu": False}
    monkeypatch.setattr(centre, "mode_jeu_actif", lambda: etat["jeu"])
    vrai = moteurs.requete
    def requete(methode, url, *a, **k):
        if url.endswith("/prompt"):
            etat["jeu"] = True                                                                        # le Mode jeu démarre pendant la création
        return vrai(methode, url, *a, **k)
    from centre.images import Images
    centre.salles.reseau.requete = requete
    creer(centre, "local")
    assert "reprendre" not in moteurs.ordre and moteurs.ordre[-1] == "free"


def test_crew_arrete_aucune_adresse_de_crew_appelee(centre, simulateur, moteurs):
    simulateur.crew_pids = []
    centre.rafraichir()
    n = len(simulateur.requetes)
    j = creer(centre, "local", confirme_liberation=False)
    assert j["etat"] == "termine" and moteurs.ordre == ["creation"]
    assert not [r for r in simulateur.requetes[n:] if "8765" in r[1]]


def test_chef_pas_charge_rien_a_liberer(centre, simulateur, moteurs):
    simulateur.modeles[centre.L.R.MODELE_GEMMA] = 0
    j = creer(centre, "local", confirme_liberation=False)
    assert j["etat"] == "termine" and moteurs.ordre == ["creation"]


def test_adresses_de_crew_absentes_404_mode_degrade(centre, simulateur, moteurs):
    simulateur.chef_liberer_disponible = False
    j = creer(centre, "local")
    assert j["etat"] == "erreur" and "Libérez la carte graphique" in j["message"] and "Chef d'équipe" in j["message"] and moteurs.ordre == []
    mo = {x["id"]: x for x in centre.images.options()["moteurs"]}
    assert not mo["local"]["disponible"] and "Libérez la carte graphique" in mo["local"]["raison"]        # ComfyUI grisé tant que le chef occupe la carte
    simulateur.modeles[centre.L.R.MODELE_GEMMA] = 0                                                   # carte libérée à la main (page Chef d'équipe / Mode jeu)
    assert {x["id"]: x for x in centre.images.options()["moteurs"]}["local"]["disponible"]
    assert creer(centre, "local", confirme_liberation=False)["etat"] == "termine"


def test_crew_occupe_409_message_clair(centre, simulateur, moteurs):
    simulateur.chef_conflit = True
    j = creer(centre, "local")
    assert j["etat"] == "erreur" and "occupé" in j["message"] and moteurs.ordre == []


def test_echec_de_creation_le_chef_est_quand_meme_recharge(centre, simulateur, moteurs):
    moteurs.erreur[COMFY + "/prompt"] = (500, "boum")
    j = creer(centre, "local")
    suivre_chef(centre)
    assert j["etat"] == "erreur" and moteurs.ordre[-2:] == ["free", "reprendre"] and simulateur.modeles[centre.L.R.MODELE_GEMMA] == 1


# ----- file d'attente -----------------------------------------------------------------------------------------------------

def test_une_seule_creation_a_la_fois_les_autres_attendent_et_s_annulent(centre, moteurs, reseau):
    import threading
    porte = threading.Event()
    vrai = reseau.requete
    def lent(*a, **k):
        if a[1] == URL_XAI:
            porte.wait(5)
        return vrai(*a, **k)
    reseau.requete = lent
    j1 = centre.images.lancer("xai", "première")
    j2 = centre.images.lancer("xai", "seconde")
    j3 = centre.images.lancer("xai", "troisième")
    import time
    for _ in range(200):
        if centre.images.etat_job(j1["id"])["etat"] == "en_cours":
            break
        time.sleep(0.01)
    assert centre.images.etat_job(j2["id"])["etat"] == "attente" and centre.images.etat_job(j2["id"])["position"] == 1 and centre.images.etat_job(j3["id"])["position"] == 2
    assert centre.images.annuler(j2["id"])["etat"] == "annule"
    assert centre.images.etat_job(j3["id"])["position"] == 1
    porte.set()
    assert centre.images.attendre(j1["id"])["etat"] == "termine" and centre.images.attendre(j3["id"])["etat"] == "termine"
    assert centre.images.etat_job(j2["id"])["etat"] == "annule" and len([a for a in moteurs.appels if a[1] == URL_XAI]) == 2      # la tâche annulée n'a rien coûté


def test_annuler_une_creation_en_cours(centre, moteurs):
    j = centre.images.lancer("local", "x", n=4, confirme_liberation=True)
    centre.images.annuler(j["id"])
    f = centre.images.attendre(j["id"])
    assert f["etat"] in ("annule", "termine") and f["fait"] < 4 or f["etat"] == "termine"


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
        centre.images.lancer("openai", "x", n=3)                                           # 0,126 $ > 0,10 $
    assert e.value.code == 402 and e.value.extra == {"depassement": True} and "seuil" in str(e.value)
    assert not [a for a in moteurs.appels if a[1] == URL_OPENAI]
    assert creer(centre, "openai", n=3, confirme_depassement=True)["fait"] == 3


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
    r = client.post("/api/images", json={"moteur": "openai", "prompt": "x", "n": 3})
    assert r.status_code == 402 and r.json()["depassement"] is True
    r = client.post("/api/images", json={"moteur": "local", "prompt": "x"})
    assert r.status_code == 409 and r.json()["liberation"] is True
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
