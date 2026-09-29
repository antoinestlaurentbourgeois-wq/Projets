# -*- coding: utf-8 -*-
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANNEAU = os.path.join(os.path.dirname(RACINE), "panneau")
for d in (RACINE, PANNEAU):
    if d not in sys.path:
        sys.path.insert(0, d)

from simulateur import Simulateur  # noqa: E402  (fourni par le panneau)
from starlette.testclient import TestClient  # noqa: E402

from centre.app import creer_app  # noqa: E402
from centre.config import Config  # noqa: E402
from centre.service import Centre  # noqa: E402
from centre.verrou import Verrou  # noqa: E402

NIP, SECRET = "123456", "motsecret-de-test"


class Horloge:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def horloge():
    return Horloge()


@pytest.fixture
def simulateur():
    return Simulateur()


@pytest.fixture
def centre(tmp_path, simulateur):
    config = Config(dossier_donnees=str(tmp_path / "donnees"), rafraichir_en_fond=False)
    return Centre(config, systeme=simulateur)


@pytest.fixture
def verrou(centre, horloge):
    v = Verrou(centre.config.chemin("verrou.json"), horloge=horloge)
    v.definir(NIP, SECRET)
    return v


@pytest.fixture
def client(centre, verrou):
    """Client déjà connecté."""
    c = TestClient(creer_app(centre, verrou), base_url="http://127.0.0.1:8740")
    c.headers["X-Centre"] = "1"
    r = c.post("/api/connexion", json={"nip": NIP, "secret": SECRET})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def anonyme(centre, verrou):
    """Client sans session."""
    c = TestClient(creer_app(centre, verrou), base_url="http://127.0.0.1:8740", follow_redirects=False)
    c.headers["X-Centre"] = "1"
    return c
