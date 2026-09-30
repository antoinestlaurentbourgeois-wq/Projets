# -*- coding: utf-8 -*-
import json

import pytest

from centre.verrou import ErreurVerrou, Verrou
from conftest import NIP, SECRET


def test_non_defini(tmp_path):
    v = Verrou(str(tmp_path / "v.json"))
    assert not v.est_defini()
    with pytest.raises(ErreurVerrou):
        v.connexion(NIP, SECRET)


@pytest.mark.parametrize("nip,secret", [("12345", SECRET), ("abcdef", SECRET), (NIP, "court"), (NIP, NIP)])
def test_definir_refuse_les_valeurs_faibles(tmp_path, nip, secret):
    with pytest.raises(ErreurVerrou):
        Verrou(str(tmp_path / "v.json")).definir(nip, secret)


def test_ni_nip_ni_secret_ne_sont_ecrits(verrou):
    brut = open(verrou.chemin, encoding="utf-8").read()
    assert NIP not in brut and SECRET not in brut
    assert set(json.loads(brut)) >= {"nip", "secret", "sel_nip", "sel_secret"}


def test_connexion_ok_et_mauvais(verrou):
    jeton = verrou.connexion(NIP, SECRET)
    assert verrou.session_valide(jeton)
    for nip, secret in [("000000", SECRET), (NIP, "mauvais-secret-x"), ("", "")]:
        with pytest.raises(ErreurVerrou, match="incorrect"):
            verrou.connexion(nip, secret)


def test_les_deux_facteurs_sont_necessaires(verrou):
    with pytest.raises(ErreurVerrou):
        verrou.connexion(NIP, "faux-secret-123")
    with pytest.raises(ErreurVerrou):
        verrou.connexion("999999", SECRET)


def test_attente_apres_cinq_echecs_puis_doublement(verrou, horloge):
    for _ in range(5):
        with pytest.raises(ErreurVerrou):
            verrou.connexion("000000", "x" * 12)
    with pytest.raises(ErreurVerrou, match="Patientez"):
        verrou.connexion(NIP, SECRET)          # même le bon mot de passe est refusé pendant l'attente
    assert verrou.attente_restante() == 30
    horloge.t += 31
    with pytest.raises(ErreurVerrou, match="incorrect"):
        verrou.connexion("000000", "x" * 12)
    assert verrou.attente_restante() == 60     # ça double
    horloge.t += 61
    assert verrou.session_valide(verrou.connexion(NIP, SECRET))
    assert verrou.attente_restante() == 0


def test_attente_plafonnee(verrou, horloge):
    for _ in range(30):
        horloge.t += 10_000
        with pytest.raises(ErreurVerrou):
            verrou.connexion("000000", "x" * 12)
    assert verrou.attente_restante() == 900


def test_session_expire_apres_12_h(verrou, horloge):
    jeton = verrou.connexion(NIP, SECRET)
    horloge.t += 12 * 3600 - 1
    assert verrou.session_valide(jeton)
    horloge.t += 2
    assert not verrou.session_valide(jeton)


def test_deconnexion_et_jeton_inconnu(verrou):
    jeton = verrou.connexion(NIP, SECRET)
    verrou.deconnexion(jeton)
    assert not verrou.session_valide(jeton)
    assert not verrou.session_valide("n-importe-quoi") and not verrou.session_valide(None)


def test_changer_le_secret_deconnecte_tout_le_monde(verrou):
    jeton = verrou.connexion(NIP, SECRET)
    verrou.definir("654321", "un-autre-mot-secret")
    assert not verrou.session_valide(jeton)
    assert verrou.session_valide(verrou.connexion("654321", "un-autre-mot-secret"))
