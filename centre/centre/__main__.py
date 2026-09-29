# -*- coding: utf-8 -*-
"""
Lancement du Centre de contrôle.

  python -m centre                 démarre le serveur (127.0.0.1:8740)
  python -m centre definir-verrou  choisit le NIP et le mot secret (demandés au clavier)
  python -m centre demo            démarre avec un PC SIMULÉ (rien n'est lancé pour de vrai)
  python -m centre tests-panneau   lance les tests du panneau (là où il est installé)
"""

import getpass
import os
import sys

from .config import Config, HOTE, dossier_demo
from .verrou import ErreurVerrou, Verrou


def definir_verrou(config):
    verrou = Verrou(config.chemin("verrou.json"), config.duree_session)
    print("Choix du NIP et du mot secret du Centre de contrôle.")
    print("(Rien ne s'affiche pendant la saisie ; c'est normal.)\n")
    while True:
        nip = getpass.getpass("NIP (au moins 6 chiffres) : ")
        secret = getpass.getpass("Mot secret (au moins 10 caractères) : ")
        if getpass.getpass("Retapez le mot secret : ") != secret or getpass.getpass("Retapez le NIP : ") != nip:
            print("\nLes saisies ne correspondent pas. Recommencez.\n")
            continue
        try:
            verrou.definir(nip, secret)
        except ErreurVerrou as e:
            print(f"\n{e} Recommencez.\n")
            continue
        break
    print("\nVerrou enregistré. Toutes les sessions ouvertes sont déconnectées.")


def reparer_flux(config):
    """Sous pythonw (sans console), stdout/stderr valent None et uvicorn plante : on les envoie dans un fichier."""
    for nom in ("stdout", "stderr"):
        if getattr(sys, nom) is None:
            os.makedirs(config.dossier_donnees, exist_ok=True)
            setattr(sys, nom, open(config.chemin("console.log"), "a", encoding="utf-8", buffering=1))


def demarrer(config, systeme=None, reseau=None, processus=None):
    reparer_flux(config)
    import uvicorn
    from .app import creer_app
    from .service import Centre
    centre = Centre(config, systeme=systeme, reseau=reseau, processus=processus)
    app = creer_app(centre)
    # Adresse imposée : jamais autre chose que 127.0.0.1.
    uvicorn.run(app, host=HOTE, port=config.port, log_level="warning", access_log=False)


def demo():
    """PC simulé : pratique pour essayer l'interface sans rien risquer."""
    dossier_panneau = Config().dossier_panneau
    sys.path.insert(0, dossier_panneau)
    from simulateur import Simulateur
    config = Config(dossier_donnees=dossier_demo())
    Verrou(config.chemin("verrou.json")).definir("123456", "motsecret-demo")
    print("MODE DEMO : tout est simulé.  Adresse : http://127.0.0.1:%d   NIP : 123456   Mot secret : motsecret-demo"
          % config.port)
    from .simulation import ProcessusDemo, ReseauDemo
    sim = Simulateur(temps_reel=True)
    sim.delai_docker, sim.delai_webui, sim.delai_crew = 2, 1, 1
    sim.tout_allumer()
    sim.cles.update({"GEMINI_API_KEY": "cle-demo", "XAI_API_KEY": "cle-demo", "OPENAI_API_KEY": "cle-demo"})
    demarrer(config, sim, ReseauDemo(), ProcessusDemo())


def tests_panneau():
    import subprocess
    dossier = Config().dossier_panneau
    return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", os.path.join(dossier, "tests")],
                           cwd=dossier)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    commande = argv[0] if argv else "serveur"
    if commande == "definir-verrou":
        definir_verrou(Config())
    elif commande == "demo":
        demo()
    elif commande == "tests-panneau":
        return tests_panneau()
    elif commande in ("serveur", "demarrer"):
        demarrer(Config())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
