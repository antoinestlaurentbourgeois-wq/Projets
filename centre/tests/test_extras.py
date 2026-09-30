# -*- coding: utf-8 -*-
"""Phase 5 : sauvegarde, gardien, rapport, rappels, départements, bulletin, Truth Gate."""

import csv
import io
import json
import os
import time
import zipfile

import pytest

from conftest import sse
from centre import bulletin, departements, gardien
from centre import rapport, sauvegarde, verite
from centre.rappels import ErreurRappel, Rappels, suivante
from centre.salles import URLS_API, ErreurSalle

URL_GEMMA = "http://127.0.0.1:1234/v1/chat/completions"
URL_TTS = "https://api.openai.com/v1/audio/speech"


def ecrire(config, rel, contenu):
    chemin = config.chemin(rel)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)
    return chemin


def noms(zip_):
    with zipfile.ZipFile(zip_) as z:
        return z.namelist()


# ----- sauvegarde ------------------------------------------------------------------------------------------

def test_sauvegarde_sans_secrets(centre, verrou):
    cfg = centre.config
    ecrire(cfg, "conversations/aaaaaaaaaaaaaaaa.json", json.dumps({"id": "a", "messages": [{"texte": "bonjour"}]}))
    ecrire(cfg, "tiroir.json", "[]")
    ecrire(cfg, "conversations/bbbbbbbbbbbbbbbb.json", json.dumps({"texte": "ma clé est sk-abcdefghijkl1234567"}))
    ecrire(cfg, "reglages_perso.txt", "api_key=SUPERSECRET123456")
    ecrire(cfg, "zone.tmp", "temporaire")
    assert os.path.isfile(cfg.chemin("verrou.json"))
    r = sauvegarde.sauvegarder(cfg)
    assert r["ok"] and r["nom"].startswith("centre-") and r["nom"].endswith(".zip")
    archive = os.path.join(sauvegarde.dossier_sauvegardes(cfg), r["nom"])
    contenu = noms(archive)
    assert "conversations/aaaaaaaaaaaaaaaa.json" in contenu and "tiroir.json" in contenu and "MANIFESTE.json" in contenu
    assert "verrou.json" not in contenu                                             # empreintes du NIP/mot secret : jamais
    assert "conversations/bbbbbbbbbbbbbbbb.json" not in contenu and "reglages_perso.txt" not in contenu and "zone.tmp" not in contenu
    raisons = {e["fichier"]: e["raison"] for e in r["ecartes"]}
    assert "clé" in raisons["conversations/bbbbbbbbbbbbbbbb.json"] and "verrou.json" in raisons
    with zipfile.ZipFile(archive) as z:
        brut = b"".join(z.read(n) for n in z.namelist()).decode("utf-8", "replace")
    assert "sk-abcdefghijkl" not in brut and "SUPERSECRET" not in brut and json.loads(open(cfg.chemin("verrou.json")).read())["nip"] not in brut


def test_sauvegarde_garde_les_sept_dernieres(centre):
    cfg = centre.config
    ecrire(cfg, "tiroir.json", "[]")
    t0 = time.time()
    for i in range(9):
        r = sauvegarde.sauvegarder(cfg, maintenant=t0 + i * 3600)
        assert r["ok"]
    liste = sauvegarde.lister(cfg)
    assert len(liste) == 7 and liste[0]["nom"] > liste[-1]["nom"]
    assert len(r["supprimees"]) == 1


def test_restauration_dans_un_dossier_neuf(centre, tmp_path):
    cfg = centre.config
    ecrire(cfg, "tiroir.json", '[{"id": "x"}]')
    nom = sauvegarde.sauvegarder(cfg)["nom"]
    cible = str(tmp_path / "restaure")
    assert sauvegarde.restaurer(cfg, nom, cible) == os.path.abspath(cible)
    assert json.load(open(os.path.join(cible, "tiroir.json"))) == [{"id": "x"}]
    with pytest.raises(ValueError, match="vide"):                                   # jamais par-dessus
        sauvegarde.restaurer(cfg, nom, cible)
    for mauvais in ("../x.zip", "centre-1.zip", "", "centre-20260101-000000.zip"):
        with pytest.raises(ValueError):
            sauvegarde.restaurer(cfg, mauvais, str(tmp_path / "autre"))


def test_restauration_refuse_un_chemin_piege(centre, tmp_path):
    cfg = centre.config
    dossier = sauvegarde.dossier_sauvegardes(cfg)
    os.makedirs(dossier, exist_ok=True)
    with zipfile.ZipFile(os.path.join(dossier, "centre-20260101-000000.zip"), "w") as z:
        z.writestr("../evil.txt", "x")
    with pytest.raises(ValueError, match="suspecte"):
        sauvegarde.restaurer(cfg, "centre-20260101-000000.zip", str(tmp_path / "cible"))
    assert not os.path.exists(tmp_path / "evil.txt")


def test_sauvegarde_dossier_absent(tmp_path):
    from centre.config import Config
    assert sauvegarde.sauvegarder(Config(dossier_donnees=str(tmp_path / "rien")))["ok"] is False


# ----- gardien ------------------------------------------------------------------------------------------------

def test_gardien_tout_va_bien(centre, verrou):
    sauvegarde.sauvegarder(centre.config)
    r = gardien.verifier(centre.config, repond=lambda u, d=4: True, espace_libre=lambda: 100.0,
                         cles_presentes={"DEEPSEEK_API_KEY": True}, tailscale_funnel=False)
    assert r["ok"] and r["alertes"] == [] and r["details"]["derniere_sauvegarde"].startswith("centre-")


def test_gardien_alertes(centre, verrou):
    r = gardien.verifier(centre.config, repond=lambda u, d=4: False, espace_libre=lambda: 1.0,
                         cles_presentes={"XAI_API_KEY": False, "DEEPSEEK_API_KEY": True}, tailscale_funnel=True)
    texte = " | ".join(r["alertes"])
    assert not r["ok"]
    for attendu in ("ne répond pas", "1.0 Go", "Aucune sauvegarde", "XAI_API_KEY", "funnel"):
        assert attendu in texte


def test_gardien_sauvegarde_ancienne_et_verrou_absent(centre):
    os.remove(centre.config.chemin("verrou.json")) if os.path.exists(centre.config.chemin("verrou.json")) else None
    nom = sauvegarde.sauvegarder(centre.config)["nom"]
    vieux = time.time() - 40 * 3600
    os.utime(os.path.join(sauvegarde.dossier_sauvegardes(centre.config), nom), (vieux, vieux))
    r = gardien.verifier(centre.config, repond=lambda u, d=4: True, espace_libre=lambda: 100.0)
    texte = " | ".join(r["alertes"])
    assert "plus de 36 h" in texte and "verrou" in texte and not r["ok"]


def test_gardien_ecrire_lire_silence(centre):
    assert gardien.lire(centre.config)["silencieux"] is True
    r = gardien.verifier(centre.config, repond=lambda u, d=4: True, espace_libre=lambda: 100.0)
    gardien.ecrire(centre.config, r)
    assert gardien.lire(centre.config)["silencieux"] is False
    vieux = gardien.lire(centre.config, maintenant=time.time() + 3600)
    assert vieux["silencieux"] and "30 minutes" in " ".join(vieux["alertes"])


# ----- rapport ------------------------------------------------------------------------------------------------------

def test_rapport(centre, horloge):
    cfg = centre.config
    centre.couts.horloge = horloge
    centre.couts.enregistrer("deepseek", 0.5)
    centre.couts.enregistrer("grok", 1.0)
    horloge.t += 86400
    centre.couts.enregistrer("deepseek", 0.25)
    c = centre.salles.creer_conversation("deepseek")
    centre.salles.conversations.ajouter_message(c, "assistant", "ok", salle="deepseek")
    centre.salles.conversations.ajouter_message(c, "assistant", "erreur", salle="deepseek", erreur=True)
    centre.salles.conversations.enregistrer(c)
    centre.recus.ajouter("voix_live", modele="m", minutes=2.5, cout_usd=0.1)
    r = rapport.construire(cfg, 30, maintenant=horloge.t)
    assert r["total_usd"] == 1.75 and r["par_ia"] == {"grok": 1.0, "deepseek": 0.75}
    assert r["messages_par_salle"] == {"deepseek": 1} and r["conversations_actives"] == 1
    assert r["voix"]["sessions"] == 1 and r["voix"]["minutes"] == 2.5 and r["moyenne_par_jour_usd"] == pytest.approx(1.75 / 30, abs=1e-4)
    assert len(r["par_jour"]) == 2
    court = rapport.construire(cfg, 1, maintenant=horloge.t)
    assert court["total_usd"] == 0.25


def test_rapport_csv_neutralise_les_formules(centre):
    r = {"lignes": [{"jour": "2026-09-29", "ia": "=cmd|'/c calc'!A1", "usd": 1.5}], "messages_par_salle": {"@x": 2}}
    texte = rapport.en_csv(r)
    assert texte.startswith("﻿")
    lignes = list(csv.reader(io.StringIO(texte.lstrip("﻿")), delimiter=";"))
    assert lignes[1] == ["2026-09-29", "'=cmd|'/c calc'!A1", "1,5"] and lignes[4] == ["'@x", "2"]


# ----- rappels ------------------------------------------------------------------------------------------------------------

@pytest.fixture
def rappels(tmp_path, horloge):
    return Rappels(str(tmp_path / "r.json"), horloge=horloge)


def test_rappel_cycle_de_vie(rappels, horloge):
    r = rappels.ajouter("Appeler le client", horloge.t + 3600)
    assert r["zone"] == "prive" and r["fait"] is False
    assert rappels.dus() == []
    horloge.t += 3601
    assert [x["id"] for x in rappels.dus()] == [r["id"]]
    rappels.reporter(r["id"], 30)
    assert rappels.dus() == []
    horloge.t += 31 * 60
    rappels.terminer(r["id"])
    assert rappels.lister() == [] and rappels.lister(True)[0]["fait"] is True
    rappels.supprimer(r["id"])
    with pytest.raises(ErreurRappel):
        rappels.supprimer(r["id"])


@pytest.mark.parametrize("texte,echeance,rec,zone", [("", 1_800_000_000, "aucune", "prive"), ("x" * 501, 1_800_000_000, "aucune", "prive"),
                                                    ("x", "abc", "aucune", "prive"), ("x", 5, "aucune", "prive"), ("x", 9e12, "aucune", "prive"),
                                                    ("x", 1_800_000_000, "toutes-les-heures", "prive"), ("x", 1_800_000_000, "aucune", "publique")])
def test_rappel_invalide(rappels, texte, echeance, rec, zone):
    with pytest.raises(ErreurRappel):
        rappels.ajouter(texte, echeance, rec, zone)


def test_rappels_recurrents(rappels, horloge):
    r = rappels.ajouter("Quotidien", horloge.t - 3 * 86400 - 10, "quotidien")
    rappels.terminer(r["id"])
    nouveau = rappels.lister()[0]
    assert nouveau["fait"] is False and nouveau["echeance"] > horloge.t and nouveau["echeance"] - horloge.t <= 86400
    h = rappels.ajouter("Hebdo", horloge.t - 86400, "hebdomadaire")
    rappels.terminer(h["id"])
    assert 0 < [x for x in rappels.lister() if x["id"] == h["id"]][0]["echeance"] - horloge.t <= 7 * 86400


def test_recurrence_mensuelle_fin_de_mois():
    janvier31 = time.mktime((2026, 1, 31, 9, 0, 0, 0, 0, -1))
    apres = time.mktime((2026, 1, 31, 10, 0, 0, 0, 0, -1))
    f = time.localtime(suivante(janvier31, "mensuel", apres))
    assert (f.tm_year, f.tm_mon, f.tm_mday, f.tm_hour) == (2026, 2, 28, 9)
    decembre = time.mktime((2026, 12, 15, 8, 0, 0, 0, 0, -1))
    f = time.localtime(suivante(decembre, "mensuel", decembre + 1))
    assert (f.tm_year, f.tm_mon, f.tm_mday) == (2027, 1, 15)


def test_rappels_api(client, centre, horloge):
    r = client.post("/api/rappels", json={"texte": "Payer la facture", "echeance": time.time() - 60, "zone": "partageable"})
    assert r.status_code == 201
    ident = r.json()["id"]
    assert client.get("/api/rappels/dus").json()["dus"][0]["id"] == ident
    assert client.put(f"/api/rappels/{ident}", json={"action": "reporter", "minutes": 60}).status_code == 200
    assert client.get("/api/rappels/dus").json()["dus"] == []
    assert client.put(f"/api/rappels/{ident}", json={"action": "terminer"}).json()["fait"] is True
    assert client.put(f"/api/rappels/{ident}", json={"action": "x"}).status_code == 400
    assert client.put("/api/rappels/inconnu", json={"action": "terminer"}).status_code == 404
    assert client.post("/api/rappels", json={"texte": "", "echeance": 1}).status_code == 400
    assert client.delete(f"/api/rappels/{ident}").status_code == 200
    assert client.get("/api/rappels?tous=1").json()["rappels"] == []


# ----- départements ---------------------------------------------------------------------------------------------------------------------

def test_departements_fournis(centre):
    deps, problemes = departements.charger(centre.config)
    assert problemes == [] and {d["id"] for d in deps} >= {"bureau-etudes", "code", "ecriture", "veille", "maison"}
    assert all(d["demarrages"] and all(x["prompt"] and x["salle"] for x in d["demarrages"]) for d in deps)
    bureau = next(d for d in deps if d["id"] == "bureau-etudes")
    assert any(x["memoire"] for x in bureau["demarrages"])


def test_departements_utilisateur_remplace_et_invalides_signales(centre):
    ecrire(centre.config, "departements/bureau.json", json.dumps({"id": "bureau-etudes", "nom": "Mon bureau", "salle": "gemma",
                                                                  "demarrages": [{"titre": "Mon test", "prompt": "Fais ceci : "}]}))
    ecrire(centre.config, "departements/casse.json", "{pas du json")
    ecrire(centre.config, "departements/mauvais.json", json.dumps({"id": "MAUVAIS ID", "nom": "x"}))
    ecrire(centre.config, "departements/salle.json", json.dumps({"id": "salle", "nom": "x", "salle": "inconnue"}))
    ecrire(centre.config, "departements/vide.json", json.dumps({"id": "vide", "nom": "V", "demarrages": [{"titre": "sans prompt"}]}))
    deps, problemes = departements.charger(centre.config)
    b = next(d for d in deps if d["id"] == "bureau-etudes")
    assert b["nom"] == "Mon bureau" and b["demarrages"][0]["salle"] == "gemma" and len(problemes) == 4


def test_departements_api(client):
    d = client.get("/api/departements").json()
    assert len(d["departements"]) >= 5 and d["problemes"] == []


# ----- bulletin du matin ------------------------------------------------------------------------------------------------------------------

def test_bulletin_contenu_et_confidentialite(centre, simulateur, horloge):
    simulateur.tout_allumer(); centre.rafraichir()
    centre.rappels.horloge = horloge
    centre.rappels.ajouter("Rappeler Durand pour le contrat", horloge.t - 600, "aucune", "prive")
    centre.rappels.ajouter("Acheter du café", horloge.t + 60, "aucune", "partageable")
    centre.couts.definir_plafonds(5, 50)
    b = bulletin.composer(centre, maintenant=horloge.t)
    assert "Nous sommes le" in b["texte"] and "Allumés" in b["texte"] and "Mode de Crew" in b["texte"]
    assert "Rappeler Durand" in b["texte"] and "Acheter du café" in b["texte"]                  # à l'écran : tout
    assert "Rappeler Durand" not in b["texte_voix"] and "Acheter du café" in b["texte_voix"]    # voix du nuage : pas le privé
    assert "1 rappel privé" in b["texte_voix"] and "Plafond du jour" in b["texte"]


def test_bulletin_dates_en_francais():
    assert bulletin.date_fr(time.mktime((2026, 9, 29, 12, 0, 0, 0, 0, -1))) == "mardi 29 septembre 2026"
    assert bulletin.date_fr(time.mktime((2026, 2, 1, 12, 0, 0, 0, 0, -1))) == "dimanche 1er février 2026"


def test_bulletin_api_et_lecture(client, centre, simulateur, reseau):
    simulateur.cles["OPENAI_API_KEY"] = "sk-openai-secret-000000"
    centre.rappels.ajouter("Secret médical", time.time() - 60, "aucune", "prive")
    b = client.get("/api/bulletin").json()
    assert "Secret médical" in b["texte"] and "Secret médical" not in b["texte_voix"]
    vu = {}
    reseau.repondre(URL_TTS, lambda c, e: (vu.update(corps=c) or (200, b"MP3")))
    r = client.post("/api/bulletin/lire", json={"fournisseur": "openai"})
    assert r.status_code == 200 and r.content == b"MP3"
    assert "Secret médical" not in vu["corps"]["input"] and "1 rappel privé" in vu["corps"]["input"]      # le nuage ne le reçoit pas
    simulateur.fichiers[centre.L.R.FICHIER_MODE_CREW] = json.dumps({"mode": "ultra-confidentiel"}); centre.salles.politique.oublier()
    assert client.post("/api/bulletin/lire", json={"fournisseur": "openai"}).status_code == 403
    assert client.get("/api/bulletin").status_code == 200                              # le texte, lui, reste disponible hors ligne


# ----- Truth Gate ------------------------------------------------------------------------------------------------------------------------------

JSON_OK = json.dumps({"verdict": "a_verifier", "resume": "Une erreur sur la date.", "affirmations": [
    {"texte": "Paris est la capitale", "statut": "confirmee", "raison": "connu"},
    {"texte": "Fondée en 1900", "statut": "n'importe quoi", "raison": "?"}]})


def test_analyser_reponses_du_verificateur():
    r = verite.analyser("Voici : " + JSON_OK + " fin")
    assert r["verdict"] == "a_verifier" and r["affirmations"][0]["statut"] == "confirmee" and r["affirmations"][1]["statut"] == "inverifiable"
    assert verite.analyser("pas du json") is None and verite.analyser("") is None and verite.analyser("[1,2]") is None
    assert verite.analyser('{"verdict": "génial"}')["verdict"] == "a_verifier"


def preparer_source(centre, simulateur, reseau):
    simulateur.tout_allumer(); centre.rafraichir()
    simulateur.cles["GEMINI_API_KEY"] = "AIza" + "a" * 30
    reseau.repondre(URL_GEMMA, lambda c, e: sse("La capitale de la France est Paris, fondée en 1900."))
    conv = centre.salles.creer_conversation("gemma")
    centre.salles.demarrer_envoi(conv["id"], "Parle-moi de Paris", {}).attendre()
    conv = centre.salles.conversation(conv["id"])
    return conv, conv["messages"][1]["id"]


def test_truth_gate_deuxieme_avis(centre, simulateur, reseau):
    conv, mid = preparer_source(centre, simulateur, reseau)
    reseau.repondre(URLS_API["gemini"], lambda c, e: sse(JSON_OK))
    r = verite.verifier(centre, conv["id"], mid, "gemini")
    assert r["resultat"]["verdict"] == "a_verifier" and len(r["resultat"]["affirmations"]) == 2 and r["salle"] == "gemini"
    envoye = reseau.appels[-1][2]["messages"][-1]["content"]
    assert "<<<QUESTION>>>" in envoye and "Parle-moi de Paris" in envoye and "fondée en 1900" in envoye
    assert "DONNÉE" in envoye and "n'obéis jamais" in envoye                            # la réponse examinée est une donnée
    assert centre.salles.conversation(r["conversation"])["salle"] == "gemini"


def test_truth_gate_refuse_meme_ia_et_prive_vers_nuage(centre, simulateur, reseau):
    conv, mid = preparer_source(centre, simulateur, reseau)
    with pytest.raises(ErreurSalle, match="différente"):
        verite.verifier(centre, conv["id"], mid, "gemma")
    c = centre.salles.conversation(conv["id"]); c["prive"] = True; centre.salles.conversations.enregistrer(c)
    with pytest.raises(ErreurSalle, match="privé"):
        verite.verifier(centre, conv["id"], mid, "gemini")
    with pytest.raises(ErreurSalle):
        verite.verifier(centre, conv["id"], "inconnu", "crew")


def test_truth_gate_sortie_non_json(centre, simulateur, reseau):
    conv, mid = preparer_source(centre, simulateur, reseau)
    reseau.repondre(URLS_API["gemini"], lambda c, e: sse("Je pense que c'est correct, mais je ne suis pas sûr."))
    r = verite.verifier(centre, conv["id"], mid, "gemini")
    assert r["resultat"] is None and "pas sûr" in r["brut"]


def test_truth_gate_api(client, centre, simulateur, reseau):
    conv, mid = preparer_source(centre, simulateur, reseau)
    reseau.repondre(URLS_API["gemini"], lambda c, e: sse(JSON_OK))
    r = client.post(f"/api/conversations/{conv['id']}/verifier", json={"message_id": mid, "salle": "gemini"})
    assert r.status_code == 200 and r.json()["resultat"]["affirmations"]
    assert client.post(f"/api/conversations/{conv['id']}/verifier", json={"message_id": mid, "salle": "gemma"}).status_code == 400
    assert client.post(f"/api/conversations/{conv['id']}/verifier", json={"message_id": "zz", "salle": "gemini"}).status_code == 404


# ----- API : sauvegarde, gardien, rapport, sécurité --------------------------------------------------------------------------------------------

def test_api_sauvegarde_gardien_rapport(client, centre):
    assert client.get("/api/sauvegardes").json()["sauvegardes"] == []
    r = client.post("/api/sauvegardes")
    assert r.status_code == 200 and r.json()["ok"] and len(client.get("/api/sauvegardes").json()["sauvegardes"]) == 1
    assert any(x["action"] == "sauvegarde" for x in client.get("/api/recus").json()["recus"])
    assert client.get("/api/gardien").json()["silencieux"] is True
    d = client.get("/api/rapport?jours=7").json()
    assert d["jours"] == 7 and "par_ia" in d
    assert client.get("/api/rapport?jours=abc").json()["jours"] == 30 and client.get("/api/rapport?jours=99999").json()["jours"] == 366
    csv_ = client.get("/api/rapport.csv")
    assert csv_.status_code == 200 and "attachment" in csv_.headers["content-disposition"] and csv_.text.startswith("﻿")


def test_routes_extras_exigent_session(anonyme):
    for chemin in ("/api/rappels", "/api/rappels/dus", "/api/departements", "/api/bulletin", "/api/sauvegardes", "/api/gardien",
                   "/api/rapport", "/api/rapport.csv"):
        assert anonyme.get(chemin).status_code == 401, chemin
    for methode, chemin in (("POST", "/api/rappels"), ("POST", "/api/bulletin/lire"), ("POST", "/api/sauvegardes"),
                            ("POST", "/api/conversations/0123456789abcdef/verifier"), ("DELETE", "/api/rappels/x")):
        assert anonyme.request(methode, chemin, json={}).status_code == 401


def test_sauvegarde_manuelle_exige_le_nip_a_distance(centre, verrou):
    from starlette.testclient import TestClient
    from centre.app import creer_app
    from conftest import NIP, SECRET
    centre.config.hotes_autorises = ("pc.tail.ts.net",)
    c = TestClient(creer_app(centre, verrou), base_url="https://pc.tail.ts.net")
    c.headers.update({"X-Centre": "1", "Tailscale-User-Login": "moi@example.com"})
    c.post("/api/connexion", json={"nip": NIP, "secret": SECRET})
    assert c.post("/api/sauvegardes").status_code == 403
    assert c.post("/api/confirmer-nip", json={"nip": NIP}).status_code == 200
    assert c.post("/api/sauvegardes").status_code == 200


# ----- ligne de commande -------------------------------------------------------------------------------------------------------------------------------

def test_commandes(tmp_path, monkeypatch, capsys):
    from centre import __main__ as principal
    d = tmp_path / "donnees"
    d.mkdir()
    (d / "tiroir.json").write_text("[]", encoding="utf-8")
    monkeypatch.setenv("CENTRE_DONNEES", str(d))
    assert principal.main(["sauvegarde"]) == 0 and "Sauvegarde centre-" in capsys.readouterr().out
    assert principal.main(["rapport", "7"]) == 0 and '"jours": 7' in capsys.readouterr().out
    nom = os.listdir(tmp_path / "sauvegardes")[0]
    assert principal.main(["restaurer", nom, str(tmp_path / "neuf")]) == 0
    assert principal.main(["restaurer", nom, str(tmp_path / "neuf")]) == 1               # dossier non vide : refusé
