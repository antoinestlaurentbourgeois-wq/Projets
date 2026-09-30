# -*- coding: utf-8 -*-
"""ComfyUI automatique : libérer le chef, démarrer, créer, arrêter, recharger. Faux Crew, faux scripts, faux ComfyUI : aucun vrai processus."""

import threading

import pytest

from test_images import COMFY, auto, creer, moteurs, suivre_chef  # noqa: F401  (moteurs : fixture)
from centre.images import ErreurImage

ETAPES_ATTENDUES = ["Libération de la carte graphique par Crew…", "Démarrage de ComfyUI…", "Création de l'image 1 sur 1…", "Arrêt de ComfyUI…", "Rechargement du chef…"]


@pytest.fixture
def cycle(centre, simulateur, moteurs):
    """Cas normal : ComfyUI arrêté, le Centre le démarre lui-même. Enregistre les étapes affichées."""
    auto(moteurs, simulateur)
    vues = []
    vrai = centre.images._etape
    def etape(job, texte):
        vues.append(texte)
        vrai(job, texte)
    centre.images._etape = etape
    moteurs.etapes = vues
    return moteurs


def scripts(simulateur):
    return [s[0] for s in simulateur.comfy_scripts]


# ----- la séquence complète --------------------------------------------------------------------------------------------------

def test_sequence_complete_dans_l_ordre_exact(centre, simulateur, cycle):
    j = creer(centre, "local")
    assert j["etat"] == "termine"
    assert cycle.ordre == ["liberer", "comfy_demarre", "creation", "comfy_arrete", "reprendre"]        # libérer AVANT démarrer, arrêter AVANT reprendre
    vues = [e for i, e in enumerate(cycle.etapes) if e in ETAPES_ATTENDUES and (i == 0 or cycle.etapes[i - 1] != e)]
    assert vues == ETAPES_ATTENDUES                                                                      # les étapes affichées à l'écran, dans l'ordre
    assert "Chef rechargé : Crew est de nouveau disponible." in j["message"]
    assert simulateur.modeles[centre.L.R.MODELE_GEMMA] == 1 and not simulateur.comfy_actif
    assert simulateur.chef_operations == ["liberer", "reprendre"]
    assert centre.comfyui.demarre_par_le_centre is False and centre.images.lister()[0]["moteur"] == "local"


def test_un_seul_clic_de_confirmation_et_rien_ne_part_avant(centre, simulateur, cycle):
    with pytest.raises(ErreurImage) as e:
        centre.images.lancer("local", "un chat")
    assert e.value.code == 409 and e.value.extra == {"liberation": True}
    assert "Pour créer cette image en local : Crew libère la carte graphique, ComfyUI démarre (environ 20 à 40 s), crée l'image puis s'arrête" in str(e.value)
    assert "et Crew recharge son chef (environ 10 s). Pendant ce temps Crew continue par un modèle de nuage en mode normal et reste indisponible en mode confidentiel." in str(e.value)
    assert cycle.ordre == [] and simulateur.comfy_scripts == [] and simulateur.chef_operations == []


def test_sans_crew_seulement_comfyui_et_confirmation_courte(centre, simulateur, cycle):
    simulateur.crew_pids = []
    centre.rafraichir()
    with pytest.raises(ErreurImage) as e:
        centre.images.lancer("local", "un chat")
    assert "ComfyUI démarre" in str(e.value) and "Crew libère" not in str(e.value)                      # le démarrage d'un processus demande aussi le clic
    n = len(simulateur.requetes)
    j = creer(centre, "local")
    assert j["etat"] == "termine" and cycle.ordre == ["comfy_demarre", "creation", "comfy_arrete"]
    assert not [r for r in simulateur.requetes[n:] if "8765" in r[1]]                                   # Crew arrêté : aucune adresse de Crew appelée


def test_le_modele_est_choisi_au_demarrage_quand_aucun_n_est_connu(centre, simulateur, cycle):
    j = creer(centre, "local", modele="sdxl_base.safetensors")
    assert j["modele"] == "sdxl_base.safetensors"
    import os
    os.remove(centre.config.chemin("images_checkpoints.json"))                                          # rien de mémorisé, ComfyUI arrêté
    auto(cycle, simulateur)
    j = creer(centre, "local")
    assert j["etat"] == "termine" and j["modele"] == "sdxl_base.safetensors"                            # le premier modèle vu après le démarrage


# ----- « finally » : on remet toujours tout en ordre ----------------------------------------------------------------------------

def test_echec_de_demarrage_le_chef_revient_quand_meme(centre, simulateur, cycle):
    simulateur.comfy_echec_demarrage = True
    j = creer(centre, "local")
    assert j["etat"] == "erreur" and "ComfyUI n'a pas démarré" in j["message"] and "comfyui.log" in j["message"]
    assert "Traceback" not in j["message"] and "Exception" not in j["message"]                          # jamais de trace technique brute
    assert scripts(simulateur) == ["demarrer", "arreter"]                                               # on arrête quand même ce qui a pu démarrer
    assert cycle.ordre == ["liberer", "comfy_arrete", "reprendre"] and simulateur.modeles[centre.L.R.MODELE_GEMMA] == 1


def test_echec_de_creation_arret_puis_reprise(centre, simulateur, cycle):
    cycle.erreur[COMFY + "/prompt"] = (500, "boum")
    j = creer(centre, "local")
    assert j["etat"] == "erreur" and cycle.ordre == ["liberer", "comfy_demarre", "comfy_arrete", "reprendre"]
    assert simulateur.modeles[centre.L.R.MODELE_GEMMA] == 1


def test_annulation_arret_puis_reprise(centre, simulateur, cycle):
    porte, pris = threading.Event(), {}
    vrai = centre.salles.reseau.requete
    def requete(methode, url, *a, **k):
        if url.endswith("/history/abc123") and "id" in pris:
            centre.images.annuler(pris["id"])
        return vrai(methode, url, *a, **k)
    centre.salles.reseau.requete = requete
    cycle.contenu  # noqa: B018
    j = centre.images.lancer("local", "un chat", confirme_liberation=True)
    pris["id"] = j["id"]
    fin = centre.images.attendre(j["id"])
    assert fin["etat"] in ("annule", "termine")
    assert cycle.ordre[-2:] == ["comfy_arrete", "reprendre"] and not simulateur.comfy_actif


def test_pas_de_reprise_si_mode_jeu_crew_arrete_ou_laisser_libre(centre, simulateur, cycle, monkeypatch):
    j = creer(centre, "local", laisser_libre=True)                                                      # l'utilisateur a coché « laisser la carte libre ensuite »
    assert j["etat"] == "termine" and cycle.ordre == ["liberer", "comfy_demarre", "creation", "comfy_arrete"] and simulateur.chef_operations == ["liberer"]
    simulateur.chef_operations.clear()
    cycle.ordre.clear()
    auto(cycle, simulateur)
    etat = {"jeu": False}
    monkeypatch.setattr(centre, "mode_jeu_actif", lambda: etat["jeu"])
    vrai = cycle.requete
    def requete(methode, url, *a, **k):
        if url.endswith("/prompt"):
            etat["jeu"] = True                                                                          # le Mode jeu arrive pendant la création
        return vrai(methode, url, *a, **k)
    centre.salles.reseau.requete = requete
    simulateur.modeles[centre.L.R.MODELE_GEMMA] = 1
    simulateur.chef_libere = False
    j = creer(centre, "local")
    assert "reprendre" not in cycle.ordre and "comfy_arrete" in cycle.ordre                             # ComfyUI arrêté, chef laissé libre pour le jeu


def test_le_vrai_mode_jeu_pendant_la_creation_ne_fait_rien_recharger(centre, simulateur, cycle):
    """Le Mode jeu lancé pendant la création (course réelle) : ComfyUI est arrêté par lui, le chef n'est PAS rechargé derrière lui."""
    vrai = centre.salles.reseau.requete
    lance = {}
    def requete(methode, url, *a, **k):
        if url.endswith("/prompt") and not lance:
            lance["oui"] = True
            centre.lancer_action("mode_jeu")
            centre.attendre_action()
            cycle.comfy = False                                                                          # le Mode jeu a arrêté ComfyUI : la création va échouer
        return vrai(methode, url, *a, **k)
    centre.salles.reseau.requete = requete
    j = creer(centre, "local")
    assert "reprendre" not in cycle.ordre and simulateur.chef_operations == ["liberer"]
    assert centre.mode_jeu_actif() is True                                                               # « en vigueur » : rien n'a été rallumé


# ----- file d'attente : un seul cycle -----------------------------------------------------------------------------------------------

def test_plusieurs_demandes_un_seul_cycle(centre, simulateur, cycle):
    porte = threading.Event()
    vrai = centre.salles.reseau.requete
    def lent(methode, url, *a, **k):
        if url.endswith("/prompt") and not porte.is_set():
            porte.wait(5)
        return vrai(methode, url, *a, **k)
    centre.salles.reseau.requete = lent
    js = [centre.images.lancer("local", f"image {i}", confirme_liberation=True) for i in range(3)]
    porte.set()
    fins = [centre.images.attendre(j["id"]) for j in js]
    assert [f["etat"] for f in fins] == ["termine"] * 3
    assert cycle.ordre == ["liberer", "comfy_demarre", "creation", "creation", "creation", "comfy_arrete", "reprendre"]
    assert scripts(simulateur) == ["demarrer", "arreter"] and simulateur.chef_operations == ["liberer", "reprendre"]


def test_la_demande_suivante_garde_comfyui_meme_si_la_premiere_echoue(centre, simulateur, cycle):
    porte = threading.Event()
    vrai = centre.salles.reseau.requete
    n = {"p": 0}
    def requete(methode, url, *a, **k):
        if url.endswith("/prompt"):
            if n["p"] == 0:
                porte.wait(5)
            n["p"] += 1
            if n["p"] == 1:
                return 500, "boum"
        return vrai(methode, url, *a, **k)
    centre.salles.reseau.requete = requete
    j1 = centre.images.lancer("local", "a", confirme_liberation=True)
    j2 = centre.images.lancer("local", "b", confirme_liberation=True)
    porte.set()
    assert centre.images.attendre(j1["id"])["etat"] == "erreur" and centre.images.attendre(j2["id"])["etat"] == "termine"
    assert cycle.ordre.count("comfy_demarre") == 1 and cycle.ordre.count("comfy_arrete") == 1 and cycle.ordre[-2:] == ["comfy_arrete", "reprendre"]


# ----- ComfyUI lancé à la main -------------------------------------------------------------------------------------------------------

def test_comfyui_a_la_main_pas_demarre_ni_arrete(centre, simulateur, moteurs):
    j = creer(centre, "local")                                                                           # moteurs : ComfyUI déjà lancé à la main
    assert j["etat"] == "termine" and scripts(simulateur) == [] and simulateur.comfy_actif
    assert moteurs.ordre == ["liberer", "creation", "free", "reprendre"]
    assert j["demarre_par_le_centre"] is False


def test_comfyui_a_la_main_arrete_si_l_utilisateur_le_demande(centre, simulateur, moteurs):
    j = creer(centre, "local", arreter_comfyui=True)
    assert j["etat"] == "termine" and scripts(simulateur) == ["arreter"] and not simulateur.comfy_actif
    assert moteurs.ordre == ["liberer", "creation", "comfy_arrete", "reprendre"]


def test_l_etat_du_travail_note_demarre_par_le_centre(centre, simulateur, cycle):
    j = creer(centre, "local")
    assert j["demarre_par_le_centre"] is True


# ----- sécurité mémoire : arrêt après 10 minutes d'inactivité ----------------------------------------------------------------------

def test_arret_apres_dix_minutes_d_inactivite(centre, simulateur, cycle):
    t = {"t": 1000.0}
    centre.comfyui.horloge = lambda: t["t"]
    simulateur.comfy_actif = True
    cycle.comfy = True
    assert centre.comfyui.surveiller() is False                                                          # pas lancé par le Centre : jamais arrêté ici
    centre.comfyui.noter_demarrage_manuel()
    t["t"] += 599
    assert centre.comfyui.surveiller() is False and simulateur.comfy_actif
    t["t"] += 2
    assert centre.comfyui.surveiller() is True and not simulateur.comfy_actif and cycle.comfy is False
    assert centre.comfyui.demarre_par_le_centre is False
    assert any(r["action"] == "comfyui" and r["resultat"] == "arret_inactivite" for r in centre.recus.derniers(20))


def test_pas_d_arret_si_comfyui_travaille_encore(centre, simulateur, cycle):
    import json
    t = {"t": 1000.0}
    centre.comfyui.horloge = lambda: t["t"]
    simulateur.comfy_actif = True
    cycle.comfy = True
    centre.comfyui.noter_demarrage_manuel()
    t["t"] += 700
    vrai = centre.salles.reseau.requete
    def requete(methode, url, *a, **k):
        if url.endswith("/queue"):
            return 200, json.dumps({"queue_running": [["x"]], "queue_pending": []})
        return vrai(methode, url, *a, **k)
    centre.salles.reseau.requete = requete
    assert centre.comfyui.surveiller() is False and simulateur.comfy_actif


def test_pas_d_arret_pendant_une_creation(centre, simulateur, cycle):
    t = {"t": 1000.0}
    centre.comfyui.horloge = lambda: t["t"]
    simulateur.comfy_actif = True
    cycle.comfy = True
    centre.comfyui.noter_demarrage_manuel()
    t["t"] += 5000
    centre.images.local_en_cours = lambda: True
    assert centre.comfyui.surveiller() is False and simulateur.comfy_actif


def test_demarrage_par_le_bouton_du_centre_est_note(client, centre, simulateur, cycle):
    assert client.post("/api/action", json={"sens": "demarrer", "ident": "comfyui"}).status_code == 202
    centre.attendre_action()
    assert simulateur.comfy_actif and centre.comfyui.demarre_par_le_centre is True
    assert scripts(simulateur) == ["demarrer"]


def test_mode_jeu_arrete_comfyui(client, centre, simulateur, moteurs):
    assert simulateur.comfy_actif
    assert client.post("/api/action", json={"sens": "mode_jeu"}).status_code == 202
    centre.attendre_action()
    assert not simulateur.comfy_actif and "arreter" in scripts(simulateur)
    assert centre.mode_jeu_actif() is True
    with pytest.raises(ErreurImage) as e:
        centre.images.lancer("local", "un chat", confirme_liberation=True)
    assert e.value.code == 403 and "Mode jeu" in str(e.value)
    assert client.post("/api/action", json={"sens": "tout_demarrer"}).status_code == 202
    centre.attendre_action()
    assert centre.mode_jeu_actif() is False and not simulateur.comfy_actif                               # « Tout démarrer » ne lance pas ComfyUI


# ----- réconciliation au démarrage : un bouton, jamais d'action automatique ---------------------------------------------------------------

def test_bandeau_carte_encore_liberee_jamais_automatique(client, centre, simulateur, cycle):
    simulateur.chef_libere = True
    simulateur.modeles[centre.L.R.MODELE_GEMMA] = 0
    n = len(simulateur.chef_operations)
    d = client.get("/api/comfyui").json()
    assert d["bandeau_chef"] is True and d["chef_libere"] is True and d["bandeau_comfyui"] is False and d["repond"] is False
    assert len(simulateur.chef_operations) == n and scripts(simulateur) == []                            # RIEN n'est fait tout seul
    r = client.post("/api/comfyui/reprendre-chef")
    assert r.status_code == 202 and simulateur.chef_operations[-1] == "reprendre"
    suivre_chef(centre)
    assert client.get("/api/comfyui").json()["bandeau_chef"] is False and simulateur.modeles[centre.L.R.MODELE_GEMMA] == 1


def test_bandeau_comfyui_tourne_avec_bouton_arreter(client, centre, simulateur, moteurs):
    d = client.get("/api/comfyui").json()
    assert d["bandeau_comfyui"] is True and d["repond"] is True and d["bandeau_chef"] is False
    assert scripts(simulateur) == []                                                                     # jamais arrêté tout seul
    r = client.post("/api/comfyui/arreter")
    assert r.status_code == 200 and r.json()["repond"] is False and scripts(simulateur) == ["arreter"]


def test_pas_de_bandeau_pendant_une_creation(client, centre, simulateur, moteurs):
    centre.images.local_en_cours = lambda: True
    d = client.get("/api/comfyui").json()
    assert d["creation_en_cours"] is True and d["bandeau_comfyui"] is False and d["bandeau_chef"] is False
    r = client.post("/api/comfyui/arreter")
    assert r.status_code == 409 and scripts(simulateur) == []
    simulateur.chef_libere = True
    assert client.post("/api/comfyui/reprendre-chef").status_code == 409


def test_recharger_le_chef_refuse_en_mode_jeu_ou_tant_que_comfyui_occupe_la_carte(client, centre, simulateur, moteurs):
    simulateur.chef_libere = True
    r = client.post("/api/comfyui/reprendre-chef")
    assert r.status_code == 409 and "ComfyUI occupe encore la carte" in r.json()["erreur"] and simulateur.chef_operations == []
    simulateur.comfy_actif = False
    moteurs.comfy = False
    centre._mode_jeu_vigueur = True
    d = client.get("/api/comfyui").json()
    assert d["mode_jeu"] is True and d["bandeau_chef"] is False                                          # jamais en Mode jeu
    r = client.post("/api/comfyui/reprendre-chef")
    assert r.status_code == 409 and "Mode jeu" in r.json()["erreur"] and simulateur.chef_operations == []


# ----- sécurité : chemins validés, rien d'extérieur dans les commandes -------------------------------------------------------------------

def test_aucun_texte_exterieur_dans_les_commandes(centre, simulateur, cycle):
    creer(centre, "local", prompt="un chat'; Remove-Item -Recurse C:\\ #  $(calc) `whoami`")
    assert len(simulateur.comfy_scripts) == 2
    for sens, script, args in simulateur.comfy_scripts:
        assert len(args) == 6 and args[1:5] == ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
        assert args[5] == script and script.endswith(("demarrer_comfyui.ps1", "arreter_comfyui.ps1"))
    tout = " ".join(" ".join(map(str, c)) for c in simulateur.commandes)
    assert "Remove-Item" not in tout and "whoami" not in tout


def test_dossier_invalide_refuse_sans_rien_lancer(centre, simulateur, cycle):
    centre.ctrl.dossier_comfyui = "I:\\IA\\..\\ailleurs"
    mo = {x["id"]: x for x in centre.images.options()["moteurs"]}
    assert not mo["local"]["disponible"] and "invalide" in mo["local"]["raison"]
    with pytest.raises(ErreurImage):
        creer(centre, "local")
    assert simulateur.comfy_scripts == []


def test_cle_dossier_comfyui_de_reglages(tmp_path, simulateur, reseau, processus, amont):
    from centre.config import Config
    from centre.service import Centre
    d = tmp_path / "donnees"
    d.mkdir()
    (d / "reglages.json").write_text('{"dossier_comfyui": "D:\\\\Outils\\\\ComfyUI"}', encoding="utf-8")
    c = Centre(Config(dossier_donnees=str(d), rafraichir_en_fond=False), systeme=simulateur, reseau=reseau, processus=processus, amont=amont)
    assert c.ctrl.dossier_comfyui == "D:\\Outils\\ComfyUI"
    assert c.ctrl.scripts_comfyui() == ("D:\\Outils\\ComfyUI\\demarrer_comfyui.ps1", "D:\\Outils\\ComfyUI\\arreter_comfyui.ps1")


def test_le_centre_ne_touche_jamais_lm_studio_pendant_le_cycle(centre, simulateur, cycle):
    avant = len(simulateur.commandes)
    creer(centre, "local")
    neuves = simulateur.commandes[avant:]
    assert not [c for c in neuves if "lms" in c[0].lower()]                                               # que des scripts PowerShell
    assert all("-File" in c for c in neuves)


def test_pas_de_description_d_image_dans_le_journal(centre, simulateur, cycle, caplog):
    import logging
    with caplog.at_level(logging.DEBUG, logger="centre"):
        creer(centre, "local", prompt="description-secrete-xyz")
    assert "description-secrete-xyz" not in caplog.text
    assert "description-secrete-xyz" not in open(centre.config.chemin("recus.jsonl"), encoding="utf-8").read()
