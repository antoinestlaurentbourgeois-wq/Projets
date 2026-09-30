# -*- coding: utf-8 -*-
"""Table ronde : une question, plusieurs IA, TOUJOURS par Crew. Faux Crew (flux + estimation), aucun vrai réseau."""

import json

import pytest

from conftest import morceau, sse_table, usage_p
from centre import tableronde as T
from centre.ia import CrewTableRonde
from centre.reseau import Annulation
from test_salles import allumer, envoyer, texte, types

URL_CREW = "http://127.0.0.1:8765/v1/chat/completions"
TROIS = ["gemini", "deepseek", "gemma"]            # ordre du contrat (le Centre envoie la liste cochée, dans cet ordre)


def flux_normal():
    return sse_table(
        morceau("gemma", "Réponse "), morceau("gemma", "de gemma"), usage_p("gemma", 0.0, duree=1.2),
        morceau("gemini", "Réponse de Gemini"), usage_p("gemini", 0.0, duree=2.5),
        morceau("deepseek", "Réponse DeepSeek"), usage_p("deepseek", 0.0031, duree=3.1),
        morceau("synthese", "Synthèse : tout le monde est d'accord."), usage_p("synthese", 0.0004, duree=0.9))


def tr(participants=TROIS, critique=False, synthese=True, **extra):
    return {"participants": participants, "critique": critique, "synthese": synthese, **extra}


def prepare(centre, simulateur, reseau, flux=flux_normal):
    allumer(centre, simulateur)
    reseau.repondre(URL_CREW, lambda c, e: flux())


def envoi_crew(reseau):
    return [a for a in reseau.appels if a[1] == URL_CREW][-1]


# ----- options et estimation ------------------------------------------------------------------------------------------

def test_options_crew_arrete_puis_allume(centre, simulateur):
    o = centre.salles.table_ronde.options()
    assert o["crew_actif"] is False and "arrêté" in o["raison"] and "individuelles" in o["raison"]
    allumer(centre, simulateur)
    o = centre.salles.table_ronde.options()
    assert o["crew_actif"] and set(o["defaut"]) == {"gemma", "gemini", "deepseek"} and o["seuil_usd"] == 0.10
    assert [p["id"] for p in o["participants"]] == ["claude", "codex", "gemini", "grok", "deepseek", "gemma"]
    assert {p["id"] for p in o["participants"] if p["defaut"]} == set(TROIS)         # Claude, Codex, Grok décochés


def test_estimation_total_et_grises(centre, simulateur):
    allumer(centre, simulateur)
    simulateur.table_ronde_indispos = {"grok": "clé XAI_API_KEY absente"}
    e = centre.salles.table_ronde.estimer([{"role": "user", "content": "q"}], ["claude", "grok", "deepseek"])
    assert e["ok"] and e["total_usd"] == pytest.approx(0.053)                          # Grok grisé : pas compté
    g = {p["id"]: p for p in e["participants"]}
    assert g["grok"]["disponible"] is False and "XAI_API_KEY" in g["grok"]["raison"] and g["claude"]["libelle"] == "Claude"
    assert not e["depasse"]


def test_estimation_depasse_le_seuil_reglable(centre, simulateur):
    allumer(centre, simulateur)
    m = [{"role": "user", "content": "q"}]
    e = centre.salles.table_ronde.estimer(m, ["claude", "codex", "grok"])
    assert e["total_usd"] == pytest.approx(0.15) and e["depasse"] and "seuil de 0.10 $" in e["message"]
    centre.config.seuil_table_ronde_usd = 1.0
    assert not centre.salles.table_ronde.estimer(m, ["claude", "codex", "grok"])["depasse"]


def test_estimation_du_tour_de_critique(centre, simulateur):
    allumer(centre, simulateur)
    m = [{"role": "user", "content": "q"}]
    un = centre.salles.table_ronde.estimer(m, ["claude"], critique=False)["total_usd"]
    deux = centre.salles.table_ronde.estimer(m, ["claude"], critique=True)["total_usd"]
    assert deux == pytest.approx(2 * un)


def test_estimation_erreurs_claires(centre, simulateur):
    m = [{"role": "user", "content": "q"}]
    e = centre.salles.table_ronde.estimer(m, TROIS)
    assert not e["ok"] and "arrêté" in e["message"]                                     # Crew éteint
    allumer(centre, simulateur)
    simulateur.table_ronde_disponible = False
    e = centre.salles.table_ronde.estimer(m, TROIS)
    assert not e["ok"] and "n'expose pas encore la table ronde" in e["message"]


def test_seuil_lu_dans_reglages_json(tmp_path):
    from centre.config import Config
    d = tmp_path / "d"; d.mkdir()
    (d / "reglages.json").write_text('{"seuil_table_ronde_usd": 0.25}', encoding="utf-8")
    assert Config(dossier_donnees=str(d)).seuil_table_ronde_usd == 0.25
    for mauvais in ('{"seuil_table_ronde_usd": -1}', '{"seuil_table_ronde_usd": "x"}', '{"seuil_table_ronde_usd": true}'):
        (d / "reglages.json").write_text(mauvais, encoding="utf-8")
        assert Config(dossier_donnees=str(d)).seuil_table_ronde_usd == 0.10


# ----- envoi et flux ----------------------------------------------------------------------------------------------------

def test_flux_complet_un_seul_message_vers_crew(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau)
    evts, conv = envoyer(centre, "crew", "Compare ces deux options", table_ronde=tr())
    assert types(evts)[0] == "debut" and types(evts)[-1] == "fin"
    # un SEUL appel de chat, à Crew, avec le contrat convenu
    appels = [a for a in reseau.appels if a[1] == URL_CREW]
    assert len(appels) == 1
    _, url, corps, entetes = appels[0]
    assert corps["model"] == "crew-tableronde" and corps["stream"] is True
    assert corps["table_ronde"] == {"participants": TROIS, "critique": False, "synthese": True}
    assert corps["messages"][-1] == {"role": "user", "content": "Compare ces deux options"} and entetes["Authorization"] == "Bearer cle-crew-secrete"
    assert not [a for a in reseau.appels if "api.deepseek.com" in a[1] or "googleapis" in a[1]]      # jamais d'appel direct : tout passe par Crew
    # événements par participant
    deltas = [e for e in evts if e["t"] == "tr_delta"]
    assert {e["participant"] for e in deltas} == {"gemma", "gemini", "deepseek", "synthese"}
    assert "".join(e["texte"] for e in deltas if e["participant"] == "gemma") == "Réponse de gemma"
    fins = {e["participant"]: e for e in evts if e["t"] == "tr_fin"}
    assert fins["deepseek"]["cout_usd"] == 0.0031 and fins["gemma"]["duree_s"] == 1.2 and fins["deepseek"]["tour"] == 1
    # message enregistré : réponses de chacun, synthèse en dernier, historique = synthèse
    m = conv["messages"][-1]
    assert m["texte"] == "Synthèse : tout le monde est d'accord."
    assert [r["participant"] for r in m["table_ronde"]["reponses"]] == ["gemini", "deepseek", "gemma", "synthese"]      # synthèse en dernier
    assert m["cout_usd"] == pytest.approx(0.0035)
    # coûts RÉELS rangés sous chaque IA
    par_ia = centre.couts.totaux()["aujourdhui"]["par_ia"]
    assert par_ia["deepseek"] == pytest.approx(0.0031, abs=1e-4) and par_ia["crew"] == pytest.approx(0.0004, abs=1e-4)
    assert json.loads(open(centre.config.chemin("depenses.jsonl")).read().splitlines()[0])["estime"] is False


def test_un_participant_echoue_les_autres_continuent(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: sse_table(
        morceau("gemma", "ok gemma"), usage_p("gemma", 0.0, duree=1),
        {"participant": "gemini", "tour": 1, "statut": "erreur", "erreur": "503 surcharge chez Google"},
        morceau("deepseek", "ok deepseek"), usage_p("deepseek", 0.002, duree=2),
        morceau("synthese", "Synthèse sur deux IA"), usage_p("synthese", 0.0)))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr())
    assert [e["participant"] for e in evts if e["t"] == "tr_erreur"] == ["gemini"]
    assert "surcharge" in [e for e in evts if e["t"] == "tr_erreur"][0]["message"]
    rep = {r["participant"]: r for r in conv["messages"][-1]["table_ronde"]["reponses"]}
    assert rep["gemini"]["statut"] == "erreur" and rep["gemma"]["statut"] == "ok" and rep["synthese"]["texte"] == "Synthèse sur deux IA"
    assert types(evts)[-1] == "fin" and "erreur" not in types(evts)                                # la conversation n'est pas en erreur


def test_participant_exclu_pour_confidentialite_est_affiche_et_jamais_contourne(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: sse_table(
        {"participant": "claude", "tour": 1, "statut": "exclu", "raison": "contenu confidentiel, traité en local seulement"},
        morceau("gemma", "réponse locale"), usage_p("gemma", 0.0, duree=1),
        morceau("synthese", "Synthèse locale"), usage_p("synthese", 0.0)))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr(["claude", "gemma"]))
    ex = [e for e in evts if e["t"] == "tr_exclu"]
    assert ex and ex[0]["participant"] == "claude" and "confidentiel" in ex[0]["raison"]
    rep = {r["participant"]: r for r in conv["messages"][-1]["table_ronde"]["reponses"]}
    assert rep["claude"]["statut"] == "exclu" and rep["claude"]["texte"] == "" and "local seulement" in rep["claude"]["raison"]
    # le Centre a envoyé la liste COCHÉE telle quelle (c'est Crew qui exclut) et n'a fait AUCUN autre appel
    assert envoi_crew(reseau)[2]["table_ronde"]["participants"] == ["claude", "gemma"]
    assert len([a for a in reseau.appels if a[0] == "POST" and a[1] != URL_CREW]) == 0


def test_sans_synthese(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: sse_table(
        morceau("gemma", "avis A"), usage_p("gemma", 0.0), morceau("gemini", "avis B"), usage_p("gemini", 0.0)))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr(["gemma", "gemini"], synthese=False))
    assert envoi_crew(reseau)[2]["table_ronde"]["synthese"] is False
    m = conv["messages"][-1]
    assert m["table_ronde"]["synthese"] is False and not [r for r in m["table_ronde"]["reponses"] if r["participant"] == "synthese"]
    assert "gemma (local) : avis A" in m["texte"] and "Gemini : avis B" in m["texte"]        # l'historique garde du contenu utile


def test_tour_de_critique(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: sse_table(
        morceau("gemma", "avis 1"), usage_p("gemma", 0.0), morceau("deepseek", "avis 1 ds"), usage_p("deepseek", 0.001),
        morceau("gemma", "je critique DeepSeek", tour=2), usage_p("gemma", 0.0, tour=2),
        morceau("deepseek", "je critique gemma", tour=2), usage_p("deepseek", 0.001, tour=2),
        morceau("synthese", "synthèse finale"), usage_p("synthese", 0.0)))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr(["gemma", "deepseek"], critique=True))
    assert envoi_crew(reseau)[2]["table_ronde"]["critique"] is True
    tours = {(r["participant"], r["tour"]) for r in conv["messages"][-1]["table_ronde"]["reponses"]}
    assert {("gemma", 1), ("gemma", 2), ("deepseek", 2), ("synthese", 1)} <= tours
    assert conv["messages"][-1]["cout_usd"] == pytest.approx(0.002)
    assert conv["messages"][-1]["table_ronde"]["critique"] is True


# ----- contrôles AVANT tout appel payant ----------------------------------------------------------------------------------------

def test_au_dessus_du_seuil_il_faut_confirmer(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau)
    p = ["claude", "codex", "grok"]                                                        # 0,15 $ > 0,10 $
    evts, _ = envoyer(centre, "crew", "q", table_ronde=tr(p))
    assert types(evts) == ["erreur"] and evts[0]["code"] == "depassement" and "seuil" in evts[0]["message"]
    assert not [a for a in reseau.appels if a[1] == URL_CREW]                              # aucune IA appelée
    evts, _ = envoyer(centre, "crew", "q", table_ronde=tr(p, confirme_depassement=True))
    assert "tr_delta" in types(evts) and envoi_crew(reseau)[2]["table_ronde"]["participants"] == p


def test_ia_indisponible_refusee_avec_la_raison(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau)
    simulateur.table_ronde_indispos = {"grok": "clé XAI_API_KEY absente"}
    evts, _ = envoyer(centre, "crew", "q", table_ronde=tr(["gemma", "grok"]))
    assert types(evts) == ["erreur"] and "Grok" in evts[0]["message"] and "XAI_API_KEY" in evts[0]["message"]
    assert not [a for a in reseau.appels if a[1] == URL_CREW]


def test_crew_arrete_table_ronde_refusee_salles_individuelles_ok(centre, simulateur, reseau):
    from conftest import sse
    prepare(centre, simulateur, reseau)
    simulateur.crew_pids = []                                                              # Crew arrêté (ou Mode jeu)
    centre.rafraichir()
    evts, _ = envoyer(centre, "crew", "q", table_ronde=tr())
    assert types(evts) == ["erreur"] and "éteint" in evts[0]["message"] and not [a for a in reseau.appels if a[1] == URL_CREW]
    reseau.repondre("http://127.0.0.1:1234/v1/chat/completions", lambda c, e: sse("gemma répond seule"))
    assert texte(envoyer(centre, "gemma", "salut")[0]) == "gemma répond seule"             # la salle individuelle continue
    reseau.repondre("https://api.deepseek.com/chat/completions", lambda c, e: sse("deepseek aussi"))
    assert texte(envoyer(centre, "deepseek", "salut")[0]) == "deepseek aussi"


def test_conversation_privee_seule_gemma_participe(centre, simulateur, reseau):
    """Filet de sécurité du Centre (plus strict que Crew, jamais plus permissif) : le privé ne part pas vers des IA du nuage."""
    prepare(centre, simulateur, reseau)
    conv = centre.salles.creer_conversation("crew")
    conv["prive"] = True
    centre.salles.conversations.enregistrer(conv)
    evts = centre.salles.demarrer_envoi(conv["id"], "q", {"table_ronde": tr(["gemma", "gemini"])}).attendre()
    assert types(evts) == ["erreur"] and "contenu privé" in evts[0]["message"] and not [a for a in reseau.appels if a[1] == URL_CREW]
    evts = centre.salles.demarrer_envoi(conv["id"], "q", {"table_ronde": tr(["gemma"])}).attendre()
    assert "tr_delta" in types(evts)


def test_plafond_atteint_bloque_la_table_ronde(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau)
    centre.couts.definir_plafonds(1, None)
    centre.couts.enregistrer("deepseek", 1)
    evts, _ = envoyer(centre, "crew", "q", table_ronde=tr())
    assert types(evts) == ["erreur"] and "plafond" in evts[0]["message"]


def test_seulement_dans_la_salle_crew_et_participants_valides(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau)
    evts, _ = envoyer(centre, "gemma", "q", table_ronde=tr())
    assert "salle Crew" in evts[0]["message"]
    evts, _ = envoyer(centre, "crew", "q", table_ronde=tr([]))
    assert "au moins une IA" in evts[0]["message"]
    evts, _ = envoyer(centre, "crew", "q", table_ronde=tr(["pirate", "../x"]))
    assert "au moins une IA" in evts[0]["message"]
    assert T.nettoyer(["gemma", "gemma", "claude", "inconnu"]) == ["claude", "gemma"]


def test_crew_repond_une_erreur_http(centre, simulateur, reseau):
    allumer(centre, simulateur)
    reseau.repondre(URL_CREW, lambda c, e: (500, iter(['{"error":{"message":"boum sk-abcdefghijkl1234"}}'])))
    evts, _ = envoyer(centre, "crew", "q", table_ronde=tr())
    assert evts[-1]["t"] == "erreur" and "500" in evts[-1]["message"] and "sk-abcdefghijkl" not in evts[-1]["message"]


# ----- adaptateur : tolérance du flux ----------------------------------------------------------------------------------------------

def adapte(chunks, horloge=None):
    class R:
        def flux_post(self, *a, **k):
            return sse_table(*chunks)
    kw = {"horloge": horloge} if horloge else {}
    from centre.ia import RequeteChat
    return list(CrewTableRonde(R(), "http://127.0.0.1:8765/v1/chat/completions", lambda: "cle", **kw).repondre(
        RequeteChat(messages=[], table_ronde={"participants": ["gemma"]}), Annulation()))


def test_adaptateur_sans_participant_c_est_la_synthese_et_ids_invalides_ignores():
    evts = adapte([{"choices": [{"delta": {"content": "bloc sans participant"}}]},
                   {"choices": [{"delta": {"content": "piège"}}], "participant": "Bad Id;<script>", "tour": 1}])
    assert [e for e in evts if e["t"] == "tr_delta"] == [{"t": "tr_delta", "participant": "synthese", "tour": 1, "texte": "bloc sans participant"}]


def test_adaptateur_duree_mesuree_et_fin_implicite():
    t = iter([0.0, 10.0, 12.5, 20.0, 99.0, 99.0, 99.0])   # départ gemma, usage gemma, départ gemini, fin
    evts = adapte([morceau("gemma", "a"), usage_p("gemma", 0.0), morceau("gemini", "b")], horloge=lambda: next(t))
    fins = {e["participant"]: e for e in evts if e["t"] == "tr_fin"}
    assert fins["gemma"]["duree_s"] == 10.0                                                 # mesurée quand Crew ne la donne pas (10,0 - 0,0)
    assert fins["gemini"]["cout_usd"] is None and fins["gemini"]["duree_s"] == 7.5         # pas de bloc usage : fin implicite (20,0 - 12,5)


def test_adaptateur_tour_invalide_devient_1():
    evts = adapte([dict(morceau("gemma", "x"), tour="abc"), dict(morceau("gemma", "y"), tour=7)])
    assert [e["tour"] for e in evts if e["t"] == "tr_delta"] == [1, 1]


# ----- API HTTP -----------------------------------------------------------------------------------------------------------------------

def test_api_options_estimation_et_flux(client, centre, simulateur, reseau):
    prepare(centre, simulateur, reseau)
    o = client.get("/api/table-ronde/options").json()
    assert o["crew_actif"] and set(o["defaut"]) == set(TROIS)
    e = client.post("/api/table-ronde/estimation", json={"participants": ["claude", "gemma"], "texte": "ma question"}).json()
    assert e["ok"] and e["total_usd"] == pytest.approx(0.05) and not e["depasse"]
    e = client.post("/api/table-ronde/estimation", json={"participants": ["claude", "codex", "grok"], "critique": True}).json()
    assert e["depasse"] and e["total_usd"] == pytest.approx(0.30)
    assert client.post("/api/table-ronde/estimation", json={"participants": []}).status_code == 400
    c = client.post("/api/conversations", json={"salle": "crew"}).json()
    r = client.post(f"/api/conversations/{c['id']}/messages", json={"texte": "Question", "table_ronde": {"participants": TROIS, "critique": False, "synthese": True}})
    evts = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
    assert {e["participant"] for e in evts if e["t"] == "tr_delta"} == {"gemma", "gemini", "deepseek", "synthese"}
    assert client.get(f"/api/conversations/{c['id']}").json()["messages"][-1]["table_ronde"]["reponses"][-1]["participant"] == "synthese"


def test_api_table_ronde_exige_une_session(anonyme):
    assert anonyme.get("/api/table-ronde/options").status_code == 401
    assert anonyme.post("/api/table-ronde/estimation", json={}).status_code == 401


def test_aucun_secret_dans_les_fichiers(centre, simulateur, reseau):
    import os
    prepare(centre, simulateur, reseau)
    envoyer(centre, "crew", "q", table_ronde=tr())
    brut = ""
    for racine, _, noms in os.walk(centre.config.dossier_donnees):
        for n in noms:
            if n != "verrou.json":
                brut += open(os.path.join(racine, n), encoding="utf-8", errors="replace").read()
    assert "cle-crew-secrete" not in brut and "sk-secret-ne-pas-afficher" not in brut


def test_estimation_pour_l_ecran_grise_les_indisponibles_meme_decochees(client, centre, simulateur, reseau):
    prepare(centre, simulateur, reseau)
    simulateur.table_ronde_indispos = {"codex": "abonnement non connecté"}
    e = client.post("/api/table-ronde/estimation", json={"participants": ["claude", "gemma"], "tous": True}).json()
    ids = {p["id"]: p for p in e["participants"]}
    assert set(ids) == set(T.IDS) and ids["codex"]["disponible"] is False and "non connecté" in ids["codex"]["raison"]
    assert e["total_usd"] == pytest.approx(0.05)              # seulement Claude + gemma (cochées), pas les 6
