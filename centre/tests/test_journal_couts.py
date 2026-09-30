# -*- coding: utf-8 -*-
import json
import time

import pytest

from centre import couts as K
from centre.journal import Recus, masquer, nettoyer_details


# ----- journal --------------------------------------------------------------------------------

@pytest.mark.parametrize("texte", [
    "Authorization: Bearer abcdefghijklmnop1234", "cle sk-abcdefgh12345678", "xai-abcdefghijkl123456",
    "AIzaSyA1234567890123456789012345", "api_key=SUPERSECRET123", 'nip: "123456"', "token=abcd1234",
])
def test_masquer(texte):
    sortie = masquer(texte)
    for secret in ("abcdefghijklmnop1234", "abcdefgh12345678", "abcdefghijkl123456", "SUPERSECRET123", "1234567890123456789012345", "123456", "abcd1234"):
        assert secret not in sortie


def test_details_sans_secret():
    d = nettoyer_details({"mode": "econome", "cle": "sk-xxxxxxxxxxxx", "sous": {"mot_secret": "a", "ok": 1}, "liste": ["Bearer aaaaaaaaaaaa"]})
    brut = json.dumps(d)
    assert "sk-xxxx" not in brut and "aaaaaaaa" not in brut and d["mode"] == "econome" and d["sous"]["ok"] == 1


def test_recus(tmp_path):
    r = Recus(str(tmp_path / "recus.jsonl"))
    r.ajouter("a", x=1)
    r.ajouter("b", "erreur", cle_api="sk-abcdefghijkl")
    d = r.derniers()
    assert [x["action"] for x in d] == ["b", "a"] and d[0]["resultat"] == "erreur"
    assert "sk-abcdefghijkl" not in open(r.chemin, encoding="utf-8").read()


# ----- coûts -----------------------------------------------------------------------------------

@pytest.fixture
def couts(tmp_path, horloge):
    return K.Couts(str(tmp_path / "d.jsonl"), str(tmp_path / "p.json"), horloge=horloge)


def test_totaux_jour_et_mois(couts, horloge):
    couts.enregistrer("deepseek", 0.5)
    couts.enregistrer("deepseek", 0.25)
    couts.enregistrer("grok", 1)
    t = couts.totaux()
    assert t["aujourdhui"]["total"] == 1.75 and t["aujourdhui"]["par_ia"] == {"deepseek": 0.75, "grok": 1.0}
    horloge.t += 86400 * 1.5                      # le lendemain (même mois en général)
    t2 = couts.totaux()
    if time.strftime("%Y-%m", time.localtime(horloge.t)) == time.strftime("%Y-%m", time.localtime(horloge.t - 86400 * 1.5)):
        assert t2["aujourdhui"]["total"] == 0 and t2["mois"]["total"] == 1.75
    horloge.t += 86400 * 40                       # le mois suivant au plus tard
    assert couts.totaux()["mois"]["total"] == 0


@pytest.mark.parametrize("montant", ["abc", -1, float("nan"), 1e9, None])
def test_montant_invalide(couts, montant):
    with pytest.raises(K.ErreurCouts):
        couts.enregistrer("grok", montant)


def test_plafonds_validation(couts):
    assert couts.definir_plafonds("5", "50,5") == {"jour": 5.0, "mois": 50.5}
    assert couts.definir_plafonds("", None) == {"jour": None, "mois": None}
    for jour, mois in [("abc", 1), (-1, 10), (10, 5), (True, 1), ("1e9", None)]:
        with pytest.raises(K.ErreurCouts):
            couts.definir_plafonds(jour, mois)


def test_plafond_bloque_les_ia_payantes_pas_les_locales(couts):
    couts.definir_plafonds(1, 10)
    assert couts.peut_utiliser("deepseek") == (True, "")
    couts.enregistrer("deepseek", 1.0)
    ok, msg = couts.peut_utiliser("deepseek")
    assert not ok and "plafond du jour atteint" in msg
    assert couts.peut_utiliser("gemma") == (True, "")
    assert couts.peut_utiliser("crew", "econome")[0] is False
    assert couts.peut_utiliser("crew", "confidentiel")[0] is True     # Crew local : jamais bloqué
    assert couts.peut_utiliser("crew", "ultra-confidentiel")[0] is True
    couts.definir_plafonds(None, None)                                # plafond relevé : débloqué
    assert couts.peut_utiliser("deepseek")[0] is True


def test_plafond_mensuel(couts):
    couts.definir_plafonds(None, 2)
    couts.enregistrer("grok", 2)
    ok, msg = couts.peut_utiliser("grok")
    assert not ok and "du mois" in msg


def test_ia_inconnue_consideree_payante(couts):
    couts.definir_plafonds(0, None)
    assert couts.peut_utiliser("nouvelle-ia")[0] is False


def test_fichiers_corrompus_toleres(couts):
    open(couts.chemin_depenses, "w", encoding="utf-8").write("pas du json\n{\"ts\": 1}\n")
    open(couts.chemin_plafonds, "w", encoding="utf-8").write("{")
    assert couts.totaux()["mois"]["total"] == 0 and couts.plafonds() == {"jour": None, "mois": None}


# ----- solde DeepSeek ----------------------------------------------------------------------------

CORPS = json.dumps({"is_available": True, "balance_infos": [
    {"currency": "USD", "total_balance": "12.30", "granted_balance": "2.00", "topped_up_balance": "10.30"}]})


def test_solde_ok_et_cache():
    appels = []

    def http(m, url, entetes, delai):
        appels.append((m, url, entetes))
        return 200, CORPS
    t = [0]
    s = K.SoldeDeepSeek(lambda: "sk-secret", http, horloge=lambda: t[0])
    r = s.lire()
    assert r["ok"] and r["soldes"][0]["total"] == "12.30" and r["disponible"] is True
    assert appels[0][1] == K.URL_SOLDE_DEEPSEEK and appels[0][2]["Authorization"] == "Bearer sk-secret"
    assert "sk-secret" not in json.dumps(r)
    s.lire(); assert len(appels) == 1                  # cache 60 s
    t[0] = 61; s.lire(); assert len(appels) == 2
    s.lire(forcer=True); assert len(appels) == 3


@pytest.mark.parametrize("cle,reponse,attendu", [
    (None, (200, CORPS), "absente"), ("k", (401, ""), "refusée"), ("k", (500, ""), "500"),
    ("k", (None, "boum"), "injoignable"), ("k", (200, "pas du json"), "illisible"), ("k", (200, "{}"), "inattendue"),
])
def test_solde_erreurs(cle, reponse, attendu):
    r = K.SoldeDeepSeek(lambda: cle, lambda *a: reponse).lire()
    assert not r["ok"] and attendu in r["message"]


def test_http_sortant_refuse_les_autres_serveurs():
    for url in ("https://evil.example/x", "http://api.deepseek.com/user/balance", "https://127.0.0.1/"):
        with pytest.raises(ValueError):
            K.http_sortant("GET", url, {}, 1)
