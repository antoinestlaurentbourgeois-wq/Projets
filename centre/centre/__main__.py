# -*- coding: utf-8 -*-
"""
Lancement du Centre de contrôle.

  python -m centre                 démarre le serveur (127.0.0.1:8740)
  python -m centre definir-verrou  choisit le NIP et le mot secret (demandés au clavier)
  python -m centre demo            démarre avec un PC SIMULÉ (rien n'est lancé pour de vrai)
  python -m centre tests-panneau   lance les tests du panneau (là où il est installé)
  python -m centre sauvegarde      crée une sauvegarde sans secrets (les 7 dernières sont gardées)
  python -m centre restaurer NOM DOSSIER   extrait une sauvegarde dans un dossier neuf
  python -m centre gardien         vérifications de santé (écrit gardien.json)
  python -m centre rapport [JOURS] rapport d'usage en texte
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


def demarrer(config, systeme=None, reseau=None, processus=None, amont=None):
    reparer_flux(config)
    import uvicorn
    from .app import creer_app
    from .service import Centre
    centre = Centre(config, systeme=systeme, reseau=reseau, processus=processus, amont=amont)
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
    from .simulation import AmontDemo, ProcessusDemo, ReseauDemo
    sim = Simulateur(temps_reel=True)
    sim.delai_docker, sim.delai_webui, sim.delai_crew = 2, 1, 1
    sim.tout_allumer()
    sim.table_ronde_indispos = {"codex": "Codex : abonnement ChatGPT non connecté"}
    # Démo du chef d'équipe : un modèle dont le test est mauvais, un modèle dont le chargement échoue.
    sim.chef_modeles_lm.append({"id": "demo/modele-trop-gros", "libelle": "Modèle trop gros (démo)", "taille_go": 31.0, "params": "70B", "architecture": "demo",
                                "quantification": "Q4", "contexte": 8000, "parallele": 1,
                                "avertissement": "Ce modèle est presque aussi gros que votre mémoire vidéo : le contexte sera réduit"})
    sim.chef_test_mauvais_pour = {"google/gemma-3-27b"}
    sim.chef_echec_pour = {"demo/modele-trop-gros": "Mémoire vidéo insuffisante pour charger ce modèle"}
    sim.cles.update({"GEMINI_API_KEY": "cle-demo", "XAI_API_KEY": "cle-demo", "OPENAI_API_KEY": "cle-demo"})
    reseau = ReseauDemo()
    sim.comfy_actif = False                          # démo : ComfyUI arrêté, les deux faux scripts le démarrent et l'arrêtent (le Centre fait tout seul le cycle)
    sim.comfy_crochet = lambda sens: setattr(reseau, "comfy", sens == "demarrer")
    demarrer(config, sim, reseau, ProcessusDemo(), AmontDemo())


def tests_panneau():
    import subprocess
    dossier = Config().dossier_panneau
    return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", os.path.join(dossier, "tests")],
                           cwd=dossier)


def lancer_gardien():
    """Vérifications de santé, appelées par le Planificateur de tâches (voir scripts\\gardien.ps1)."""
    import shutil
    import subprocess
    from . import cles, gardien
    from .cles import NOMS
    config = Config()
    funnel = None
    ts = shutil.which("tailscale") or (r"C:\Program Files\Tailscale\tailscale.exe" if os.path.isfile(r"C:\Program Files\Tailscale\tailscale.exe") else None)
    if ts:
        try:
            sortie = subprocess.run([ts, "funnel", "status"], capture_output=True, text=True, timeout=15, creationflags=0x08000000 if sys.platform == "win32" else 0)
            funnel = "Funnel on" in (sortie.stdout + sortie.stderr)
        except Exception:
            funnel = None
    presentes = {}
    c = cles.Cles(_SystemeCles())
    for f in ("deepseek", "gemini", "xai", "openai"):
        presentes[NOMS[f]] = c.presente(f)
    r = gardien.verifier(config, cles_presentes=presentes, tailscale_funnel=funnel)
    gardien.ecrire(config, r)
    for a in r["alertes"]:
        print("ALERTE :", a)
    print("OK" if r["ok"] else "PROBLEME")
    return 0 if r["ok"] else 1


class _SystemeCles:
    """Lit les variables utilisateur de Windows (HKCU\\Environment) sans dépendre du panneau."""

    def valeur_variable_utilisateur(self, nom):
        if sys.platform != "win32":
            return None
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return str(winreg.QueryValueEx(k, nom)[0]).strip() or None
        except OSError:
            return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    commande = argv[0] if argv else "serveur"
    if commande == "definir-verrou":
        definir_verrou(Config())
    elif commande == "demo":
        demo()
    elif commande == "tests-panneau":
        return tests_panneau()
    elif commande == "sauvegarde":
        from . import sauvegarde
        r = sauvegarde.sauvegarder(Config())
        print(r["message"])
        for e in r.get("ecartes", []):
            print("  écarté :", e["fichier"], "-", e["raison"])
        return 0 if r["ok"] else 1
    elif commande == "restaurer" and len(argv) == 3:
        from . import sauvegarde
        try:
            print("Restauré dans :", sauvegarde.restaurer(Config(), argv[1], argv[2]))
        except ValueError as e:
            print("Impossible :", e)
            return 1
    elif commande == "gardien":
        return lancer_gardien()
    elif commande == "rapport":
        from . import rapport
        import json as _j
        print(_j.dumps(rapport.construire(Config(), int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 30), ensure_ascii=False, indent=1))
    elif commande in ("serveur", "demarrer"):
        demarrer(Config())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
