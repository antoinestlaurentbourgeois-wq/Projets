# -*- coding: utf-8 -*-
"""
Tests automatiques du panneau. Ils n'utilisent QUE le simulateur :
aucune vraie commande n'est lancée.

Lancer :  python -m unittest discover -s tests -v   (depuis le dossier panneau)
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reglages as R  # noqa: E402
import panneau_logique as L  # noqa: E402
from panneau_logique import ACTIF, ARRETE, INCONNU, TRANSITION, Etat, Composant  # noqa: E402
from simulateur import Simulateur  # noqa: E402


def sans_progres(*_):
    pass


class Enregistreur:
    """Garde la trace des états envoyés à l'interface."""

    def __init__(self):
        self.evenements = []

    def __call__(self, ident, etat, fini):
        self.evenements.append((ident, etat.code, etat.message, fini))

    def finaux(self):
        return [(i, c) for i, c, _, fini in self.evenements if fini]


def commandes(sim, *debut):
    """Commandes simulées dont les premiers mots valent `debut` (programme ignoré)."""
    return [c for c in sim.commandes if c[1:1 + len(debut)] == list(debut)]


# ---------------------------------------------------------------------------
# 1. Ordre des dépendances
# ---------------------------------------------------------------------------

class TestOrdre(unittest.TestCase):
    def test_ordre_demarrage_exact(self):
        self.assertEqual(L.ordre_demarrage(),
                         ["docker", "openwebui", "kokoro", "lmstudio", "gemma", "embeddings", "crew"])

    def test_ordre_arret_exact(self):
        self.assertEqual(L.ordre_arret(),
                         ["crew", "embeddings", "gemma", "lmstudio", "kokoro", "openwebui", "docker"])

    def test_chaque_composant_apres_ses_dependances(self):
        ordre = L.ordre_demarrage()
        for c in L.COMPOSANTS:
            for d in c.dependances:
                self.assertLess(ordre.index(d), ordre.index(c.ident), f"{d} avant {c.ident}")

    def test_boucle_detectee(self):
        boucle = [Composant("a", "A", "", ("b",)), Composant("b", "B", "", ("a",))]
        with self.assertRaises(ValueError):
            L.ordre_demarrage(boucle)

    def test_dependance_inconnue_detectee(self):
        with self.assertRaises(ValueError):
            L.ordre_demarrage([Composant("a", "A", "", ("zzz",))])

    def test_dependances_indirectes(self):
        self.assertEqual(L.toutes_dependances("crew"), {"gemma", "lmstudio"})
        self.assertEqual(L.tous_dependants("docker"), {"openwebui", "kokoro"})
        self.assertEqual(L.tous_dependants("lmstudio"), {"gemma", "embeddings", "crew"})

    def test_dependances_a_demarrer(self):
        etats = {i: Etat(ARRETE) for i in L.PAR_ID}
        self.assertEqual(L.dependances_a_demarrer("crew", etats), ["lmstudio", "gemma"])
        etats["lmstudio"] = Etat(ACTIF)
        self.assertEqual(L.dependances_a_demarrer("crew", etats), ["gemma"])
        self.assertEqual(L.dependances_a_demarrer("docker", etats), [])

    def test_dependants_a_arreter(self):
        etats = {i: Etat(ACTIF) for i in L.PAR_ID}
        etats["embeddings"] = Etat(ARRETE)
        self.assertEqual(L.dependants_a_arreter("lmstudio", etats), ["crew", "gemma"])
        self.assertEqual(L.dependants_a_arreter("docker", etats), ["kokoro", "openwebui"])


# ---------------------------------------------------------------------------
# 2. Analyse des réponses
# ---------------------------------------------------------------------------

class TestAnalyse(unittest.TestCase):
    G = R.MODELE_GEMMA

    def test_api_modeles_charge_et_non_charge(self):
        corps = json.dumps({"data": [
            {"id": self.G, "state": "loaded"},
            {"id": R.MODELE_EMBEDDINGS, "state": "not-loaded"},
        ]})
        self.assertEqual(L.analyser_api_modeles(corps, self.G), [self.G])
        self.assertEqual(L.analyser_api_modeles(corps, R.MODELE_EMBEDDINGS), [])

    def test_api_modeles_detecte_copie_en_double(self):
        corps = json.dumps({"data": [{"id": self.G, "state": "loaded"},
                                     {"id": self.G + ":2", "state": "loaded"}]})
        self.assertEqual(L.analyser_api_modeles(corps, self.G), [self.G, self.G + ":2"])

    def test_api_modeles_sans_editeur(self):
        corps = json.dumps({"data": [{"id": "gemma-4-12b-qat", "state": "loaded"}]})
        self.assertEqual(L.analyser_api_modeles(corps, self.G), ["gemma-4-12b-qat"])

    def test_api_modeles_ne_confond_pas(self):
        corps = json.dumps({"data": [{"id": "google/gemma-4-27b-qat", "state": "loaded"}]})
        self.assertEqual(L.analyser_api_modeles(corps, self.G), [])

    def test_api_modeles_illisible(self):
        for mauvais in ("<html>", "", '{"autre": 1}'):
            with self.assertRaises(ValueError):
                L.analyser_api_modeles(mauvais, self.G)

    def test_lms_ps_json(self):
        sortie = json.dumps([{"identifier": self.G, "modelKey": self.G},
                             {"identifier": "autre-modele", "modelKey": "autre-modele"}])
        self.assertEqual(L.analyser_lms_ps(sortie, self.G), [self.G])

    def test_lms_ps_texte_ancien_format(self):
        sortie = ("\nLOADED MODELS\n\nIdentifier: google/gemma-4-12b-qat\n  • Type:  LLM\n"
                  "  • Path: google/gemma-4-12b-qat/model.gguf\n\n"
                  "Identifier: text-embedding-nomic-embed-text-v1.5\n  • Type:  Embedding\n")
        self.assertEqual(L.analyser_lms_ps(sortie, self.G), [self.G])
        self.assertEqual(L.analyser_lms_ps(sortie, R.MODELE_EMBEDDINGS), [R.MODELE_EMBEDDINGS])

    def test_lms_ps_texte_tableau(self):
        sortie = ("IDENTIFIER                   MODEL                    STATUS   SIZE     CONTEXT\n"
                  "google/gemma-4-12b-qat       google/gemma-4-12b-qat   IDLE     7.15 GB  32000\n"
                  "google/gemma-4-12b-qat:2     google/gemma-4-12b-qat   IDLE     7.15 GB  4096\n")
        self.assertEqual(L.analyser_lms_ps(sortie, self.G), [self.G, self.G + ":2"])

    def test_lms_ps_aucun_modele(self):
        self.assertEqual(L.analyser_lms_ps("\nNo models are currently loaded\n", self.G), [])

    def test_lms_ps_avec_couleurs_terminal(self):
        sortie = "\x1b[1mIdentifier: \x1b[0mgoogle/gemma-4-12b-qat\n"
        self.assertEqual(L.analyser_lms_ps(sortie, self.G), [self.G])

    def test_sante_crew(self):
        self.assertTrue(L.analyser_sante_crew(200, '{"ok": true}'))
        self.assertFalse(L.analyser_sante_crew(200, '{"ok": false}'))
        self.assertFalse(L.analyser_sante_crew(200, '{"ok": "true"}'))
        self.assertFalse(L.analyser_sante_crew(500, '{"ok": true}'))
        self.assertFalse(L.analyser_sante_crew(None, "connexion refusée"))
        self.assertFalse(L.analyser_sante_crew(200, "pas du json"))

    def test_inspect(self):
        self.assertTrue(L.analyser_inspect("true\n"))
        self.assertFalse(L.analyser_inspect("false"))
        self.assertTrue(L.analyser_inspect('"true"'))
        self.assertIsNone(L.analyser_inspect(""))

    def test_tasklist_independant_de_la_langue(self):
        self.assertTrue(L.analyser_tasklist('"Docker Desktop.exe","5120","Console","1","150 000 Ko"',
                                            "Docker Desktop.exe"))
        self.assertFalse(L.analyser_tasklist("INFORMATIONS : aucune tâche en service...", "Docker Desktop.exe"))
        self.assertFalse(L.analyser_tasklist("INFO: No tasks are running which match...", "Docker Desktop.exe"))

    def test_pids_et_retour_wmi(self):
        self.assertEqual(L.analyser_pids("1234\r\n5678\r\n\r\n"), [1234, 5678])
        self.assertEqual(L.analyser_pids(""), [])
        self.assertEqual(L.analyser_retour_wmi("RETOUR=0\r\n"), 0)
        self.assertEqual(L.analyser_retour_wmi("RETOUR=9"), 9)
        self.assertIsNone(L.analyser_retour_wmi("erreur"))

    def test_chaine_powershell(self):
        self.assertEqual(L.chaine_powershell(r"I:\Python\l'ami"), r"'I:\Python\l''ami'")

    def test_powershell_encode_le_script(self):
        """Le script passe encodé : guillemets et apostrophes ne posent pas de problème."""
        import base64
        vu = []
        sw = L.SystemeWindows()
        sw.executer = lambda args, delai: vu.append(args) or L.Resultat(0)
        script = "Write-Output (\"RETOUR=\" + 'l''ami')"
        sw.powershell(script, 5)
        self.assertEqual(vu[0][-2], "-EncodedCommand")
        self.assertEqual(base64.b64decode(vu[0][-1]).decode("utf-16-le"), script)
        self.assertIn("-NoProfile", vu[0])

    def test_resume(self):
        self.assertEqual(L.resume("ligne 1\n\x1b[31mErreur finale\x1b[0m\n\n"), "Erreur finale")
        self.assertEqual(len(L.resume("x" * 500)), 140)

    def test_seulement_localhost(self):
        for url in (R.URL_WEBUI, R.URL_LMSTUDIO, R.URL_LMSTUDIO_MODELES, R.URL_CREW_SANTE):
            self.assertTrue(L.url_est_locale(url), url)
        self.assertFalse(L.url_est_locale("http://example.com/api"))
        self.assertFalse(L.url_est_locale("http://localhost.example.com/"))
        with self.assertRaises(ValueError):
            L.SystemeWindows().http_get("https://example.com", 1)


# ---------------------------------------------------------------------------
# 3. Voyants (vérifications)
# ---------------------------------------------------------------------------

class TestVoyants(unittest.TestCase):
    def setUp(self):
        self.sim = Simulateur()
        self.ctrl = L.Controleur(self.sim)

    def test_tout_eteint(self):
        e = self.ctrl.verifier_tout()
        self.assertEqual(e["docker"].code, ARRETE)
        self.assertEqual(e["openwebui"].code, ARRETE)
        self.assertIn("Docker n'est pas lancé : Open WebUI ne peut pas démarrer", e["openwebui"].message)
        self.assertEqual(e["lmstudio"].code, ARRETE)
        self.assertEqual(e["gemma"].code, INCONNU)       # serveur arrêté : on ne sait pas
        self.assertEqual(e["crew"].code, ARRETE)

    def test_tout_allume(self):
        self.sim.tout_allumer()
        e = self.ctrl.verifier_tout()
        self.assertEqual({k: v.code for k, v in e.items()}, {k: ACTIF for k in e})

    def test_docker_en_cours_de_demarrage_est_orange(self):
        self.sim.ouvrir_programme(R.DOCKER_DESKTOP_CANDIDATS[0])
        self.assertEqual(self.ctrl.verifier_docker().code, TRANSITION)

    def test_webui_conteneur_lance_mais_site_pas_pret(self):
        self.sim.docker_ouvert, self.sim.docker_pret_a = True, 0
        self.sim.conteneurs[R.CONTENEUR_WEBUI] = True
        self.sim.webui_pret_a = 999
        self.assertEqual(self.ctrl.verifier_openwebui().code, TRANSITION)

    def test_conteneur_introuvable(self):
        self.sim.docker_ouvert, self.sim.docker_pret_a = True, 0
        self.sim.webui_existe = False
        etat = self.ctrl.verifier_openwebui()
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("introuvable", etat.message)

    def test_modele_en_double_signale(self):
        self.sim.lms_serveur = True
        self.sim.modeles[R.MODELE_GEMMA] = 2
        etat = self.ctrl.verifier_modele("gemma")
        self.assertEqual(etat.code, ACTIF)
        self.assertIn("2 copies", etat.message)

    def test_serveur_arrete_se_souvient_du_dernier_etat(self):
        self.sim.lms_serveur = True
        self.assertEqual(self.ctrl.verifier_modele("gemma").code, ARRETE)
        self.sim.lms_serveur = False
        etat = self.ctrl.verifier_modele("gemma")
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("serveur LM Studio arrêté", etat.message)

    def test_voyants_ne_reveillent_pas_lm_studio(self):
        """Serveur arrêté : les vérifications automatiques ne lancent jamais `lms`."""
        self.ctrl.verifier_tout()
        self.assertEqual(commandes(self.sim, "ps"), [])

    def test_api_v0_absente_repli_sur_lms_ps(self):
        self.sim.lms_serveur = True
        self.sim.api_v0_existe = False
        self.sim.modeles[R.MODELE_GEMMA] = 1
        self.assertEqual(self.ctrl.verifier_modele("gemma").code, ACTIF)
        self.sim.lms_ps_json = False     # très ancienne version : sortie texte seulement
        self.assertEqual(self.ctrl.verifier_modele("gemma").code, ACTIF)

    def test_crew_processus_sans_reponse_est_orange(self):
        self.sim.lms_serveur = True
        self.sim.modeles[R.MODELE_GEMMA] = 1
        self.sim.crew_pids = [1, 2]
        self.sim.crew_pret_a = 999
        self.assertEqual(self.ctrl.verifier_crew().code, TRANSITION)

    def test_crew_explique_gemma_absent(self):
        self.sim.lms_serveur = True
        etat = self.ctrl.verifier_crew()
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("gemma n'est pas chargé", etat.message)

    def test_cles_presentes_sans_valeur(self):
        cles = self.ctrl.verifier_cles()
        self.assertEqual(cles, {"DEEPSEEK_API_KEY": True, "GEMINI_API_KEY": False,
                                "OPENWEBUI_API_KEY": False})
        self.assertNotIn("sk-secret", repr(cles))


# ---------------------------------------------------------------------------
# 4. Actions
# ---------------------------------------------------------------------------

class TestActions(unittest.TestCase):
    def setUp(self):
        self.sim = Simulateur()
        self.ctrl = L.Controleur(self.sim)

    def test_tout_demarrer_dans_le_bon_ordre(self):
        prog = Enregistreur()
        res = self.ctrl.tout_demarrer(prog)
        self.assertEqual({k: v.code for k, v in res.items()}, {k: ACTIF for k in res})
        self.assertEqual([i for i, _ in prog.finaux()], L.ordre_demarrage())
        # le voyant passe à l'orange pendant l'action
        self.assertIn(("docker", TRANSITION), [(i, c) for i, c, _, f in prog.evenements if not f])
        self.assertEqual({k: v.code for k, v in self.ctrl.verifier_tout().items()},
                         {k: ACTIF for k in L.PAR_ID})

    def test_mode_jeu_dans_le_bon_ordre(self):
        self.sim.tout_allumer()
        prog = Enregistreur()
        res = self.ctrl.mode_jeu(prog)
        self.assertEqual([i for i, _ in prog.finaux()], L.ordre_arret())
        self.assertTrue(all(e.code == ARRETE for e in res.values()), res)
        self.assertEqual(self.sim.modeles, {R.MODELE_GEMMA: 0, R.MODELE_EMBEDDINGS: 0})
        self.assertFalse(self.sim.docker_ouvert or self.sim.lms_serveur or self.sim.crew_pids)
        # les modèles sont déchargés AVANT l'arrêt du serveur LM Studio
        ordre = [c[1] for c in self.sim.commandes if c[0].endswith("lms.exe") and c[1] in ("unload", "server")]
        self.assertEqual(ordre.count("unload"), 2)
        self.assertEqual(ordre[-1], "server")

    def test_mode_jeu_puis_tout_demarrer(self):
        self.sim.tout_allumer()
        self.ctrl.mode_jeu(sans_progres)
        res = self.ctrl.tout_demarrer(sans_progres)
        self.assertTrue(all(e.code == ACTIF for e in res.values()), res)
        self.assertEqual(self.sim.modeles, {R.MODELE_GEMMA: 1, R.MODELE_EMBEDDINGS: 1})

    def test_ne_charge_jamais_une_deuxieme_copie(self):
        self.sim.tout_allumer()
        self.ctrl.tout_demarrer(sans_progres)
        self.ctrl.demarrer("gemma", sans_progres)
        self.assertEqual(commandes(self.sim, "load"), [])
        self.assertEqual(self.sim.modeles[R.MODELE_GEMMA], 1)

    def test_chargement_gemma_avec_contexte(self):
        self.sim.lms_serveur = True
        self.assertEqual(self.ctrl.demarrer("gemma", sans_progres).code, ACTIF)
        self.assertEqual([c[1:] for c in commandes(self.sim, "load")],
                         [["load", R.MODELE_GEMMA, "--context-length", "32000", "--parallel", "4", "-y"]])

    def test_pas_de_chargement_si_etat_inconnu(self):
        self.sim.lms_serveur = True
        self.sim.api_v0_existe = False
        self.sim.lms_ps_json = False
        self.sim.executer = lambda args, d: L.Resultat(None, "", "délai dépassé")
        etat = self.ctrl.demarrer("gemma", sans_progres)
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("2e copie", etat.message)

    def test_arret_decharge_aussi_les_copies_en_trop(self):
        self.sim.lms_serveur = True
        self.sim.modeles[R.MODELE_GEMMA] = 2
        self.assertEqual(self.ctrl.arreter("gemma", sans_progres).code, ARRETE)
        self.assertEqual(self.sim.modeles[R.MODELE_GEMMA], 0)

    def test_docker_desktop_stop_absent_repli(self):
        self.sim.tout_allumer()
        self.sim.desktop_stop_existe = False
        etat = self.ctrl.arreter("docker", sans_progres)
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("fermeture forcée", etat.message)
        self.assertTrue(any(c[0] == "taskkill" and "Docker Desktop.exe" in c for c in self.sim.commandes))
        self.assertFalse(self.sim.docker_ouvert)

    def test_docker_desktop_introuvable(self):
        self.sim.docker_desktop_installe = False
        etat = self.ctrl.demarrer("docker", sans_progres)
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("introuvable", etat.message)

    def test_docker_trop_lent(self):
        self.sim.delai_docker = 10_000
        etat = self.ctrl.demarrer("docker", sans_progres)
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("ne répond toujours pas", etat.message)

    def test_conteneur_refuse_sans_docker(self):
        etat = self.ctrl.demarrer("openwebui", sans_progres)
        self.assertEqual(etat.code, ARRETE)
        self.assertEqual(etat.message, "Docker n'est pas lancé : Open WebUI ne peut pas démarrer")

    def test_crew_lance_par_wmi(self):
        self.sim.lms_serveur = True
        self.sim.modeles[R.MODELE_GEMMA] = 1
        self.assertEqual(self.ctrl.demarrer("crew", sans_progres).code, ACTIF)
        scripts = [c[-1] for c in self.sim.commandes if c[0] == "powershell.exe"
                   and "Invoke-CimMethod" in c[-1]]
        self.assertEqual(len(scripts), 1)
        self.assertIn("Win32_Process", scripts[0])
        self.assertIn(R.SCRIPT_CREW, scripts[0])
        self.assertIn("CurrentDirectory = 'I:\\Python\\crewai-routage'", scripts[0])

    def test_crew_demarre_avec_ancienne_api_lm_studio(self):
        self.sim.lms_serveur = True
        self.sim.api_v0_existe = False
        self.sim.modeles[R.MODELE_GEMMA] = 1
        self.assertEqual(self.ctrl.demarrer("crew", sans_progres).code, ACTIF)

    def test_crew_refuse_sans_gemma(self):
        self.sim.lms_serveur = True
        etat = self.ctrl.demarrer("crew", sans_progres)
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("gemma", etat.message)
        self.assertFalse(any("Invoke-CimMethod" in c[-1] for c in self.sim.commandes))

    def test_crew_plante_au_lancement(self):
        self.sim.lms_serveur = True
        self.sim.modeles[R.MODELE_GEMMA] = 1
        self.sim.crew_plante = True
        etat = self.ctrl.demarrer("crew", sans_progres)
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("arrêté juste après", etat.message)

    def test_crew_arret_tue_les_deux_processus(self):
        self.sim.tout_allumer()
        self.assertEqual(self.ctrl.arreter("crew", sans_progres).code, ARRETE)
        kill = [c for c in self.sim.commandes if c[0] == "taskkill" and "/PID" in c]
        self.assertEqual(kill, [["taskkill", "/F", "/PID", "101", "/PID", "102"]])

    def test_crew_deja_lance_pas_de_doublon(self):
        self.sim.tout_allumer()
        self.ctrl.demarrer("crew", sans_progres)
        self.assertFalse(any("Invoke-CimMethod" in c[-1] for c in self.sim.commandes))

    def test_echec_docker_ignore_les_conteneurs_mais_pas_le_reste(self):
        self.sim.docker_desktop_installe = False
        res = self.ctrl.tout_demarrer(sans_progres)
        self.assertEqual(res["docker"].code, ARRETE)
        self.assertIn("Ignoré : Docker Desktop", res["openwebui"].message)
        self.assertIn("Ignoré", res["kokoro"].message)
        for i in ("lmstudio", "gemma", "embeddings", "crew"):
            self.assertEqual(res[i].code, ACTIF, i)

    def test_mode_jeu_continue_malgre_une_erreur(self):
        self.sim.tout_allumer()
        vrai_executer = self.sim.executer

        def powershell_en_panne(args, delai):
            if args[0] == "powershell.exe":
                return L.Resultat(1, "", "PowerShell en panne")
            return vrai_executer(args, delai)
        self.sim.executer = powershell_en_panne
        res = self.ctrl.mode_jeu(sans_progres)
        self.assertEqual(res["crew"].code, INCONNU)
        self.assertEqual(res["docker"].code, ARRETE)
        self.assertEqual(res["gemma"].code, ARRETE)

    def test_arret_idempotent(self):
        res = self.ctrl.mode_jeu(sans_progres)       # tout est déjà éteint
        self.assertTrue(all(e.code == ARRETE for e in res.values()), res)
        self.assertFalse(any(c[0] == "taskkill" for c in self.sim.commandes))

    def test_aucune_valeur_de_cle_dans_le_journal(self):
        with self.assertLogs("panneau", level="DEBUG") as cap:
            self.ctrl.tout_demarrer(sans_progres)
            self.ctrl.verifier_cles()
            L.journal.debug("fin")
        self.assertNotIn("sk-secret", "\n".join(cap.output))


if __name__ == "__main__":
    unittest.main()
