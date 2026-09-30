# -*- coding: utf-8 -*-
import os
import sys

from centre import __main__ as principal
from centre.config import Config, HOTE


def test_sans_console_les_flux_sont_rediriges(tmp_path, monkeypatch):
    config = Config(dossier_donnees=str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    principal.reparer_flux(config)
    assert sys.stdout is not None and sys.stderr is not None and hasattr(sys.stdout, "isatty")
    print("test")
    sys.stdout.flush()
    assert os.path.isfile(config.chemin("console.log"))


def test_ecoute_uniquement_en_local():
    assert HOTE == "127.0.0.1"


def test_commande_inconnue(capsys):
    assert principal.main(["nimporte"]) == 2
