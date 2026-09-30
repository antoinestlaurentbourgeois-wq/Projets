# -*- coding: utf-8 -*-
"""Table ronde : une question, plusieurs IA, TOUJOURS par Crew. Faux Crew (flux + estimation), aucun vrai réseau."""

import json

import pytest

from conftest import debut, erreur_p, exclu, fin_tr, flux_crew, reponse, sse_table, ROLE, PULSATION, STOP
from centre import tableronde as T
from centre.ia import CrewTableRonde
from centre.reseau import Annulation
from test_salles import allumer, envoyer, texte, types

URL_CREW = "http://127.0.0.1:8765/v1/chat/completions"
TROIS = ["gemini", "deepseek", "gemma"]            # ordre du contrat (le Centre envoie la liste cochée, dans cet ordre)


def flux_normal():
    return flux_crew(
        debut("gemma"), reponse("gemma", "Réponse de gemma", 0.0, duree=1.2),
        debut("gemini"), reponse("gemini", "Réponse de Gemini", 0.0, duree=2.5),
        debut("deepseek"), reponse("deepseek", "Réponse DeepSeek", 0.0031, duree=3.1),
        reponse("synthese", "Synthèse : tout le monde est d'accord.", 0.0004, duree=0.9))


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
    assert e["ok"] and e["total_usd"] == pytest.approx(0.053)                          # Grok grisé : pas estimé, pas compté
    g = {p["id"]: p for p in e["participants"]}
    assert set(g) == set(T.IDS)                                                        # les six IA, pour griser les indisponibles
    assert g["grok"]["disponible"] is False and "XAI_API_KEY" in g["grok"]["raison"] and g["claude"]["libelle"] == "Claude"
    assert g["codex"]["disponible"] and g["codex"]["cout_estime_usd"] is None          # non cochée : aucun coût demandé
    assert not e["depasse"] and not e["total_incomplet"]


def test_estimation_n_envoie_que_les_ia_cochees_et_disponibles_sans_tous(centre, simulateur, reseau):
    allumer(centre, simulateur)
    simulateur.table_ronde_indispos = {"grok": "clé absente"}
    envoyes = []
    vrai = simulateur.http
    def espion(methode, url, delai, entetes=None, corps_json=None):
        if url.endswith("/table-ronde/estimation"):
            envoyes.append(corps_json)
        return vrai(methode, url, delai, entetes, corps_json)
    simulateur.http = espion
    centre.salles.table_ronde.estimer([{"role": "user", "content": "q"}], ["claude", "grok", "gemma"], critique=True)
    assert envoyes == [{"model": "crew-tableronde", "messages": [{"role": "user", "content": "q"}], "stream": False,
                        "table_ronde": {"participants": ["claude", "gemma"], "critique": True, "synthese": True, "format": "brut"}}]
    assert "tous" not in json.dumps(envoyes)


def test_estimation_depasse_le_seuil_reglable(centre, simulateur):
    allumer(centre, simulateur)
    m = [{"role": "user", "content": "q"}]
    e = centre.salles.table_ronde.estimer(m, ["claude", "codex", "grok"])
    assert e["total_usd"] == pytest.approx(0.15) and e["depasse"] and "seuil de 0.10 $" in e["message"]
    centre.config.seuil_table_ronde_usd = 1.0
    assert not centre.salles.table_ronde.estimer(m, ["claude", "codex", "grok"])["depasse"]


def test_estimation_utilise_le_total_de_crew_deuxieme_tour_inclus(centre, simulateur):
    allumer(centre, simulateur)
    m = [{"role": "user", "content": "q"}]
    un = centre.salles.table_ronde.estimer(m, ["claude"], critique=False)["total_usd"]
    deux = centre.salles.table_ronde.estimer(m, ["claude"], critique=True)
    assert deux["total_usd"] == pytest.approx(2 * un) and deux["participants"][0]["cout_estime_usd"] == pytest.approx(0.10)   # pas doublé par le Centre


def test_tarif_inconnu_jamais_compte_comme_zero(centre, simulateur):
    allumer(centre, simulateur)
    simulateur.table_ronde_couts["grok"] = None                                        # tarif de Grok inconnu
    m = [{"role": "user", "content": "q"}]
    e = centre.salles.table_ronde.estimer(m, ["claude", "grok"])
    g = {p["id"]: p for p in e["participants"]}
    assert g["grok"]["cout_estime_usd"] is None and g["claude"]["cout_estime_usd"] == 0.05
    assert e["total_usd"] == pytest.approx(0.05) and e["total_incomplet"] is True
    e = centre.salles.table_ronde.estimer(m, ["claude", "codex", "grok"])
    assert e["total_incomplet"] and e["depasse"] is False and e["total_usd"] == pytest.approx(0.09)
    centre.config.seuil_table_ronde_usd = 0.05
    e = centre.salles.table_ronde.estimer(m, ["claude", "grok"])
    assert e["depasse"] is False                                                        # 0,05 $ : pas au-dessus, mais « au moins »
    centre.config.seuil_table_ronde_usd = 0.04
    assert "au moins 0.050 $" in centre.salles.table_ronde.estimer(m, ["claude", "grok"])["message"]


def test_estimation_erreurs_claires(centre, simulateur):
    m = [{"role": "user", "content": "q"}]
    e = centre.salles.table_ronde.estimer(m, TROIS)
    assert not e["ok"] and "arrêté" in e["message"]                                     # Crew éteint
    allumer(centre, simulateur)
    vrai = simulateur.http
    simulateur.http = lambda methode, url, delai, entetes=None, corps_json=None: (500, "boum") if "table-ronde" in url else vrai(methode, url, delai, entetes, corps_json)
    e = centre.salles.table_ronde.estimer(m, TROIS)
    assert not e["ok"] and "500" in e["message"]
    simulateur.http = lambda methode, url, delai, entetes=None, corps_json=None: (200, "pas du json") if "table-ronde" in url else vrai(methode, url, delai, entetes, corps_json)
    assert "illisible" in centre.salles.table_ronde.estimer(m, TROIS)["message"]


def test_estimation_pas_de_message_404_inventé(centre, simulateur):
    """Le vrai Crew n'a pas de « 404 : la table ronde n'existe pas » : le Centre ne l'invente plus."""
    import inspect
    assert "n'expose pas encore" not in inspect.getsource(T)


def test_crew_repond_400_le_message_de_crew_est_affiche(centre, simulateur):
    allumer(centre, simulateur)
    vrai = simulateur.http
    simulateur.http = lambda methode, url, delai, entetes=None, corps_json=None: (
        (400, '{"error": {"message": "participant inconnu : xyz"}}') if url.endswith("/estimation") else vrai(methode, url, delai, entetes, corps_json))
    e = centre.salles.table_ronde.estimer([{"role": "user", "content": "q"}], ["gemma"])
    assert not e["ok"] and "participant inconnu : xyz" in e["message"]


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
    assert corps["table_ronde"] == {"participants": TROIS, "critique": False, "synthese": True, "format": "brut"}
    assert corps["messages"][-1] == {"role": "user", "content": "Compare ces deux options"} and entetes["Authorization"] == "Bearer cle-crew-secrete"
    assert not [a for a in reseau.appels if "api.deepseek.com" in a[1] or "googleapis" in a[1]]      # jamais d'appel direct : tout passe par Crew
    # événements par participant
    deltas = [e for e in evts if e["t"] == "tr_delta"]
    assert {e["participant"] for e in deltas} == {"gemma", "gemini", "deepseek", "synthese"}
    assert [e["texte"] for e in deltas if e["participant"] == "gemma"] == ["Réponse de gemma"]                   # une réponse complète par IA
    assert [e["participant"] for e in evts if e["t"] == "tr_debut"] == ["gemma", "gemini", "deepseek"]          # la synthèse n'a pas de « debut »
    assert [e["participant"] for e in deltas] == ["gemma", "gemini", "deepseek", "synthese"]                    # ordre d'arrivée
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


def test_les_morceaux_sans_evenement_ne_sont_jamais_la_synthese(centre, simulateur, reseau):
    """Le vrai flux contient {"role"}, des pulsations de contenu vide, un morceau finish_reason « stop » : tous ignorés."""
    prepare(centre, simulateur, reseau, lambda: sse_table(
        ROLE, PULSATION, debut("gemma"), PULSATION, reponse("gemma", "réponse gemma", 0.0, duree=1.0), PULSATION,
        {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": "TEXTE ÉGARÉ sans evenement"}}]},     # jamais affiché
        STOP, fin_tr(0.0)))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr(["gemma"], synthese=False))
    assert [(e["participant"], e["texte"]) for e in evts if e["t"] == "tr_delta"] == [("gemma", "réponse gemma")]
    assert "synthese" not in {e.get("participant") for e in evts}
    assert "ÉGARÉ" not in json.dumps(conv["messages"][-1], ensure_ascii=False)


def test_ligne_fin_cout_reel_total_exclus_et_notes(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: flux_crew(
        debut("gemma"), reponse("gemma", "avis", 0.0, duree=1),
        fin_tr(cout=0.0123, exclus=["claude"], notes=["partageable/notes/mecanique.md"])))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr(["claude", "gemma"], synthese=False))
    m = conv["messages"][-1]
    assert m["cout_usd"] == pytest.approx(0.0123)                                     # coût réel total annoncé par Crew
    assert m["table_ronde"]["notes"] == ["partageable/notes/mecanique.md"]
    ex = [e for e in evts if e["t"] == "tr_exclu"]                                    # exclusion vue seulement dans « exclus » : jamais silencieuse
    assert ex and ex[0]["participant"] == "claude"
    assert {r["participant"]: r["statut"] for r in m["table_ronde"]["reponses"]} == {"claude": "exclu", "gemma": "ok"}


def test_debut_sans_reponse_devient_un_echec(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: flux_crew(debut("gemma"), debut("gemini"), reponse("gemini", "ok", 0.0, duree=1)))
    _, conv = envoyer(centre, "crew", "q", table_ronde=tr(["gemini", "gemma"], synthese=False))
    rep = {r["participant"]: r for r in conv["messages"][-1]["table_ronde"]["reponses"]}
    assert rep["gemma"]["statut"] == "erreur" and "Aucune réponse" in rep["gemma"]["raison"] and rep["gemini"]["statut"] == "ok"


def test_un_participant_echoue_les_autres_continuent(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: flux_crew(
        debut("gemma"), reponse("gemma", "ok gemma", 0.0, duree=1),
        debut("gemini"), erreur_p("gemini", "503 surcharge chez Google"),
        debut("deepseek"), reponse("deepseek", "ok deepseek", 0.002, duree=2),
        reponse("synthese", "Synthèse sur deux IA", 0.0)))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr())
    assert [e["participant"] for e in evts if e["t"] == "tr_erreur"] == ["gemini"]
    assert "surcharge" in [e for e in evts if e["t"] == "tr_erreur"][0]["message"]
    rep = {r["participant"]: r for r in conv["messages"][-1]["table_ronde"]["reponses"]}
    assert rep["gemini"]["statut"] == "erreur" and rep["gemma"]["statut"] == "ok" and rep["synthese"]["texte"] == "Synthèse sur deux IA"
    assert types(evts)[-1] == "fin" and "erreur" not in types(evts)                                # la conversation n'est pas en erreur


def test_ia_indisponible_donne_un_evenement_erreur_pas_exclu(centre, simulateur, reseau):
    """Côté Crew, une IA indisponible produit « erreur » (le Centre grise déjà les indisponibles avant l'envoi)."""
    prepare(centre, simulateur, reseau, lambda: flux_crew(
        debut("grok"), erreur_p("grok", "Grok : clé XAI_API_KEY absente"), reponse("synthese", "Synthèse", 0.0)))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr(["grok"]))
    assert [e["t"] for e in evts if e["t"] in ("tr_erreur", "tr_exclu")] == ["tr_erreur"]
    assert conv["messages"][-1]["table_ronde"]["reponses"][0]["statut"] == "erreur"


def test_participant_exclu_pour_confidentialite_est_affiche_et_jamais_contourne(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: flux_crew(
        exclu("claude"), debut("gemma"), reponse("gemma", "réponse locale", 0.0, duree=1),
        reponse("synthese", "Synthèse locale", 0.0), fin_tr(0.0, exclus=["claude"])))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr(["claude", "gemma"]))
    ex = [e for e in evts if e["t"] == "tr_exclu"]
    assert len(ex) == 1 and ex[0]["participant"] == "claude" and "confidentiel" in ex[0]["raison"]     # une seule fois (pas doublé par « exclus »)
    rep = {r["participant"]: r for r in conv["messages"][-1]["table_ronde"]["reponses"]}
    assert rep["claude"]["statut"] == "exclu" and rep["claude"]["texte"] == "" and "local seulement" in rep["claude"]["raison"]
    # le Centre a envoyé la liste COCHÉE telle quelle (c'est Crew qui exclut) et n'a fait AUCUN autre appel de chat
    assert envoi_crew(reseau)[2]["table_ronde"]["participants"] == ["claude", "gemma"]
    assert len([a for a in reseau.appels if a[0] == "POST" and a[1] != URL_CREW]) == 0


def test_sans_synthese(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: flux_crew(
        debut("gemma"), reponse("gemma", "avis A", 0.0), debut("gemini"), reponse("gemini", "avis B", 0.0)))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr(["gemma", "gemini"], synthese=False))
    assert envoi_crew(reseau)[2]["table_ronde"]["synthese"] is False
    m = conv["messages"][-1]
    assert m["table_ronde"]["synthese"] is False and not [r for r in m["table_ronde"]["reponses"] if r["participant"] == "synthese"]
    assert "Chef local (" in m["texte"] and ") : avis A" in m["texte"] and "Gemini : avis B" in m["texte"]        # l'historique garde du contenu utile


def test_tour_de_critique(centre, simulateur, reseau):
    prepare(centre, simulateur, reseau, lambda: flux_crew(
        debut("gemma"), reponse("gemma", "avis 1", 0.0), debut("deepseek"), reponse("deepseek", "avis 1 ds", 0.001),
        debut("gemma", 2), reponse("gemma", "je critique DeepSeek", 0.0, tour=2),
        debut("deepseek", 2), reponse("deepseek", "je critique gemma", 0.001, tour=2),
        reponse("synthese", "synthèse finale", 0.0)))
    evts, conv = envoyer(centre, "crew", "q", table_ronde=tr(["gemma", "deepseek"], critique=True))
    assert envoi_crew(reseau)[2]["table_ronde"]["critique"] is True
    tours = {(r["participant"], r["tour"]) for r in conv["messages"][-1]["table_ronde"]["reponses"]}
    assert {("gemma", 1), ("gemma", 2), ("deepseek", 2), ("synthese", 1)} <= tours          # la synthèse (tour 0 chez Crew) est rangée au tour 1
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


def test_adaptateur_ignore_tout_morceau_sans_evenement():
    evts = adapte([ROLE, PULSATION, {"choices": [{"delta": {"content": "bloc sans evenement"}}]},
                   {"choices": [{"delta": {"content": "piège"}}], "participant": "synthese", "tour": 0},          # avec participant mais SANS evenement
                   STOP])
    assert [e["t"] for e in evts] == ["fin"]


def test_adaptateur_ids_invalides_ignores_et_tour_invalide_devient_1():
    evts = adapte([dict(reponse("gemma", "x"), participant="Bad Id;<script>"), dict(reponse("gemma", "y"), tour="abc"), dict(reponse("gemma", "z"), tour=7)])
    assert [(e["participant"], e["tour"], e["texte"]) for e in evts if e["t"] == "tr_delta"] == [("gemma", 1, "y"), ("gemma", 1, "z")]


def test_adaptateur_duree_du_morceau_sinon_mesuree_entre_debut_et_reponse():
    t = iter([0.0, 10.0, 99.0, 99.0])
    evts = adapte([debut("gemma"), reponse("gemma", "a", 0.0), reponse("gemini", "b", 0.0, duree=4.2)], horloge=lambda: next(t))
    fins = {e["participant"]: e for e in evts if e["t"] == "tr_fin"}
    assert fins["gemma"]["duree_s"] == 10.0                                                 # Crew ne l'a pas donnée : mesurée
    assert fins["gemini"]["duree_s"] == 4.2                                                 # duree_s au niveau du morceau


def test_adaptateur_cout_entree_sortie_et_erreur_globale():
    evts = adapte([reponse("gemma", "a", 0.0042, duree=1)])
    f = [e for e in evts if e["t"] == "tr_fin"][0]
    assert f["cout_usd"] == 0.0042 and f["entree"] == 10 and f["sortie"] == 20
    evts = adapte([{"error": {"message": "Crew a un souci sk-abcdefghijkl1234"}}])
    assert evts[-1]["t"] == "erreur" and "sk-abcdefghijkl" not in evts[-1]["message"]


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
    e = client.post("/api/table-ronde/estimation", json={"participants": ["claude", "gemma"]}).json()
    ids = {p["id"]: p for p in e["participants"]}
    assert set(ids) == set(T.IDS) and ids["codex"]["disponible"] is False and "non connecté" in ids["codex"]["raison"]
    assert e["total_usd"] == pytest.approx(0.05) and e["total_incomplet"] is False          # seulement Claude + gemma (cochées)
