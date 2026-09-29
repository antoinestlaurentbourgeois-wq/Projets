# -*- coding: utf-8 -*-
"""
Tests de la version 2 : mode Crew, liste des IA, ouverture des applications.
Uniquement avec le simulateur : aucune vraie commande, aucun vrai réseau.

Lancer :  python -m unittest discover -s tests -v   (depuis le dossier panneau)
"""

import json
import os
import sys
import unittest

DOSSIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DOSSIER)

import reglages as R  # noqa: E402
import panneau_logique as L  # noqa: E402
import panneau_crew as C  # noqa: E402
import panneau_ouvrir as O  # noqa: E402
from panneau_logique import ACTIF, ARRETE, INCONNU  # noqa: E402
from simulateur import Simulateur  # noqa: E402

REPONSE_MODE = json.dumps({"mode": "econome", "modes": [
    {"id": "econome", "libelle": "Économe", "niveau": "normal", "performance": "econome",
     "explication": "Par défaut. gemma (local, gratuit) analyse chaque demande…"},
    {"id": "maxperf", "libelle": "MaxPerf", "explication": "…"},
    {"id": "confidentiel", "libelle": "Confidentiel", "explication": "…"},
    {"id": "ultra", "libelle": "Ultra-confidentiel", "explication": "…"}]}, ensure_ascii=False)

REPONSE_MOTEURS = json.dumps({"moteurs": [
    {"nom": "local", "libelle": "gemma (local, gratuit)", "local": True, "capacite": 1, "cout": 0,
     "forces": [], "etat": "pret", "detail": "google/gemma-4-12b-qat chargé"},
    {"nom": "gemini", "libelle": "Gemini Flash", "local": False, "capacite": 2, "cout": 1,
     "forces": ["redacteur"], "etat": "pret", "detail": "Clé GEMINI_API_KEY présente"},
    {"nom": "deepseek", "libelle": "DeepSeek Flash", "local": False, "capacite": 2, "cout": 1,
     "forces": ["executant", "lecteur"], "etat": "pret", "detail": "Clé DEEPSEEK_API_KEY présente"},
    {"nom": "deepseek-max", "libelle": "DeepSeek V4 Pro", "local": False, "capacite": 3, "cout": 4,
     "forces": ["executant", "lecteur", "redacteur"], "etat": "pret",
     "detail": "Clé DEEPSEEK_API_KEY présente"}]}, ensure_ascii=False)


def sans_progres(*_):
    pass


# ---------------------------------------------------------------------------
# 1. Analyse des réponses du serveur Crew et du fichier .env
# ---------------------------------------------------------------------------

class TestAnalyseCrew(unittest.TestCase):
    def test_mode(self):
        actuel, modes = C.analyser_mode(REPONSE_MODE)
        self.assertEqual(actuel, "econome")
        self.assertEqual([m.id for m in modes], ["econome", "maxperf", "confidentiel", "ultra"])
        self.assertEqual(modes[0].libelle, "Économe")          # accents (UTF-8) conservés
        self.assertTrue(modes[0].explication.startswith("Par défaut."))

    def test_mode_sans_libelle_utilise_l_identifiant(self):
        _, modes = C.analyser_mode('{"mode": "x", "modes": [{"id": "x"}, {"pas_d_id": 1}]}')
        self.assertEqual([(m.id, m.libelle) for m in modes], [("x", "x")])

    def test_mode_illisible(self):
        for mauvais in ("", "<html>", '{"mode": "econome"}', "[]"):
            with self.assertRaises(ValueError):
                C.analyser_mode(mauvais)

    def test_moteurs(self):
        moteurs = C.analyser_moteurs(REPONSE_MOTEURS)
        self.assertEqual([m.nom for m in moteurs], ["local", "gemini", "deepseek", "deepseek-max"])
        self.assertEqual(moteurs[3].capacite, 3)
        self.assertEqual(moteurs[3].cout, 4)
        self.assertEqual(moteurs[0].detail, "google/gemma-4-12b-qat chargé")

    def test_moteur_futur_avec_champs_nouveaux_ou_manquants(self):
        """Une IA ajoutée à Crew (ex. GPT-6) apparaît, même avec des champs inattendus."""
        corps = json.dumps({"moteurs": [{"nom": "gpt6", "libelle": "GPT-6", "etat": "bientot",
                                         "capacite": 4, "nouveau_champ": [1, 2]}, {"nom": "vide"}]})
        moteurs = C.analyser_moteurs(corps)
        self.assertEqual([m.libelle for m in moteurs], ["GPT-6", "vide"])
        self.assertEqual(C.couleur_moteur("bientot"), INCONNU)
        self.assertEqual(C.texte_capacite(4), "niveau 4")
        self.assertEqual(C.texte_cout(None), "coût ?")

    def test_couleurs_et_textes(self):
        self.assertEqual(C.couleur_moteur("pret"), ACTIF)
        self.assertEqual(C.couleur_moteur("arrete"), ARRETE)
        self.assertEqual(C.couleur_moteur("indisponible"), INCONNU)
        self.assertEqual(C.texte_capacite(1), "niveau 1 (simple)")
        self.assertEqual(C.texte_capacite(3), "niveau 3 (expert)")
        self.assertEqual(C.texte_cout(0), "gratuit")
        self.assertEqual(C.texte_cout(4), "coût relatif 4")
        self.assertEqual(C.texte_cout(0.5), "coût relatif 0.5")

    def test_env(self):
        texte = ("﻿# commentaire\nAUTRE=1\nexport CREW_API_KEY = \"abc 123\"  \n"
                 "CREW_API_KEY_BIS=non\n")
        self.assertEqual(C.analyser_env(texte, "CREW_API_KEY"), "abc 123")
        self.assertEqual(C.analyser_env("CREW_API_KEY=xyz # note", "CREW_API_KEY"), "xyz")
        self.assertEqual(C.analyser_env("CREW_API_KEY='a#b'", "CREW_API_KEY"), "a#b")
        self.assertIsNone(C.analyser_env("CREW_API_KEY=", "CREW_API_KEY"))
        self.assertIsNone(C.analyser_env("#CREW_API_KEY=abc", "CREW_API_KEY"))
        self.assertIsNone(C.analyser_env(None, "CREW_API_KEY"))


# ---------------------------------------------------------------------------
# 2. Mode Crew : API quand le serveur tourne, fichier quand il est éteint
# ---------------------------------------------------------------------------

class TestModeCrew(unittest.TestCase):
    def setUp(self):
        self.sim = Simulateur()
        self.crew = C.CrewDistant(self.sim)

    def test_lire_par_api_avec_la_cle(self):
        self.sim.tout_allumer()
        info = self.crew.lire_mode(crew_actif=True)
        self.assertTrue(info.serveur_actif)
        self.assertEqual(info.actuel, "econome")
        self.assertEqual(info.libelle(), "Économe")
        self.assertEqual(len(info.modes), 4)
        self.assertEqual(self.sim.requetes[-1], ("GET", R.URL_CREW_MODE, True))

    def test_changer_par_api(self):
        self.sim.tout_allumer()
        info = self.crew.changer_mode("maxperf")
        self.assertEqual(info.actuel, "maxperf")
        self.assertIn(("PUT", R.URL_CREW_MODE, True), self.sim.requetes)
        self.assertEqual(self.crew.lire_mode().actuel, "maxperf")

    def test_mode_inconnu_refuse_par_le_serveur(self):
        self.sim.tout_allumer()
        with self.assertRaises(C.ErreurCrew) as ctx:
            self.crew.changer_mode("turbo")
        self.assertIn("turbo", str(ctx.exception))

    def test_serveur_eteint_lit_le_fichier(self):
        self.sim.fichiers[R.FICHIER_MODE_CREW] = '{"mode": "confidentiel"}'
        info = self.crew.lire_mode(crew_actif=False)
        self.assertFalse(info.serveur_actif)
        self.assertEqual(info.actuel, "confidentiel")
        self.assertEqual(info.message, "Serveur Crew éteint")
        self.assertEqual(self.sim.requetes, [])        # aucune requête inutile

    def test_serveur_eteint_change_le_fichier_en_gardant_le_reste(self):
        self.sim.fichiers[R.FICHIER_MODE_CREW] = '{"mode": "econome", "autre": 42}'
        info = self.crew.changer_mode("ultra")
        self.assertEqual(info.actuel, "ultra")
        self.assertEqual(json.loads(self.sim.fichiers[R.FICHIER_MODE_CREW]), {"mode": "ultra", "autre": 42})

    def test_fichier_absent_ou_abime(self):
        del self.sim.fichiers[R.FICHIER_MODE_CREW]
        self.assertIsNone(self.crew.lire_mode(crew_actif=False).actuel)
        self.sim.fichiers[R.FICHIER_MODE_CREW] = "{abîmé"
        self.assertIsNone(self.crew.lire_mode(crew_actif=False).actuel)
        info = self.crew.changer_mode("econome")             # recrée un fichier propre
        self.assertEqual(json.loads(self.sim.fichiers[R.FICHIER_MODE_CREW]), {"mode": "econome"})
        self.assertEqual(info.actuel, "econome")

    def test_libelles_gardes_pour_quand_le_serveur_est_eteint(self):
        self.sim.tout_allumer()
        self.crew.lire_mode()                              # le serveur donne les libellés
        self.assertIn(R.FICHIER_CACHE_MODES, self.sim.fichiers)
        self.sim.crew_pids = []                            # le serveur s'arrête
        nouveau = C.CrewDistant(self.sim)                  # panneau relancé entre-temps
        info = nouveau.lire_mode(crew_actif=False)
        self.assertEqual([m.libelle for m in info.modes],
                         ["Économe", "MaxPerf", "Confidentiel", "Ultra-confidentiel"])
        self.assertIn("gemma", info.modes[0].explication)
        with self.assertRaises(C.ErreurCrew):
            nouveau.changer_mode("inexistant")             # vérifié avec la copie locale

    def test_cache_pas_reecrit_a_chaque_verification(self):
        self.sim.tout_allumer()
        self.crew.lire_mode()
        self.sim.fichiers[R.FICHIER_CACHE_MODES] = "marqueur"
        self.crew.lire_mode()
        self.assertEqual(self.sim.fichiers[R.FICHIER_CACHE_MODES], "marqueur")

    def test_serveur_qui_s_arrete_entre_deux(self):
        """Le voyant disait « actif » mais le serveur ne répond plus : repli sur le fichier."""
        info = self.crew.lire_mode(crew_actif=True)
        self.assertFalse(info.serveur_actif)
        self.assertEqual(info.actuel, "econome")

    def test_cle_absente_ou_refusee(self):
        self.sim.tout_allumer()
        self.sim.fichiers[R.FICHIER_ENV_CREW] = "AUTRE=1\n"
        info = self.crew.lire_mode()
        self.assertIn("introuvable", info.message)
        self.assertFalse(info.modifiable)
        self.sim.fichiers[R.FICHIER_ENV_CREW] = "CREW_API_KEY=mauvaise\n"
        info = self.crew.lire_mode()
        self.assertIn("refusée", info.message)
        self.assertEqual(self.crew.lire_moteurs().moteurs, None)

    def test_la_cle_n_apparait_nulle_part(self):
        self.sim.tout_allumer()
        with self.assertLogs("panneau", level="DEBUG") as cap:
            info = self.crew.lire_mode()
            self.crew.changer_mode("maxperf")
            moteurs = self.crew.lire_moteurs()
            C.journal.debug("fin")
        tout = "\n".join(cap.output) + repr(info) + repr(moteurs) + repr(self.sim.fichiers.get(R.FICHIER_CACHE_MODES))
        self.assertNotIn("cle-crew-secrete", tout)


# ---------------------------------------------------------------------------
# 3. Liste des IA (/moteurs)
# ---------------------------------------------------------------------------

class TestMoteurs(unittest.TestCase):
    def setUp(self):
        self.sim = Simulateur()
        self.crew = C.CrewDistant(self.sim)

    def test_serveur_eteint(self):
        info = self.crew.lire_moteurs(crew_actif=False)
        self.assertIsNone(info.moteurs)
        self.assertEqual(info.message, "Serveur Crew éteint")
        self.assertEqual(self.sim.requetes, [])

    def test_liste_avec_etats(self):
        self.sim.tout_allumer()
        info = self.crew.lire_moteurs()
        self.assertEqual([m.libelle for m in info.moteurs],
                         ["gemma (local, gratuit)", "Gemini Flash", "DeepSeek Flash", "DeepSeek V4 Pro"])
        self.assertEqual(info.moteurs[0].etat, "pret")
        self.assertEqual(info.moteurs[1].etat, "indisponible")   # pas de clé Gemini dans le simulateur

    def test_nouvelle_ia_apparait_sans_modifier_le_panneau(self):
        self.sim.tout_allumer()
        self.sim.moteurs_crew_supplementaires = [
            {"nom": "gpt6", "libelle": "GPT-6", "local": False, "capacite": 3, "cout": 8,
             "forces": [], "etat": "pret", "detail": "Clé OPENAI_API_KEY présente"}]
        info = self.crew.lire_moteurs()
        self.assertEqual(info.moteurs[-1].libelle, "GPT-6")


# ---------------------------------------------------------------------------
# 4. Choix du modèle le plus puissant (LM Studio)
# ---------------------------------------------------------------------------

class TestModelePuissant(unittest.TestCase):
    API = json.dumps({"data": [
        {"id": "google/gemma-4-12b-qat", "type": "vlm", "state": "loaded", "quantization": "Q4_0",
         "max_context_length": 262144, "loaded_context_length": 32000},
        {"id": "text-embedding-nomic-embed-text-v1.5", "type": "embeddings", "state": "loaded"},
        {"id": "qwen3-32b", "type": "llm", "state": "not-loaded"},
        {"id": "petit-llm", "type": "llm", "state": "loaded"}]})
    PS = json.dumps([
        {"identifier": "google/gemma-4-12b-qat", "modelKey": "google/gemma-4-12b-qat", "type": "llm",
         "sizeBytes": 7150000000},
        {"identifier": "text-embedding-nomic-embed-text-v1.5", "type": "embedding", "sizeBytes": 84000000},
        {"identifier": "petit-llm", "modelKey": "petit-llm", "type": "llm", "sizeBytes": 2000000000}])

    def test_le_plus_gros_des_llm_vlm_charges(self):
        self.assertEqual(O.choisir_modele_puissant(self.API, self.PS), "google/gemma-4-12b-qat")

    def test_embeddings_et_non_charges_ignores(self):
        api = json.dumps({"data": [
            {"id": "text-embedding-nomic-embed-text-v1.5", "type": "embeddings", "state": "loaded"},
            {"id": "qwen3-32b", "type": "llm", "state": "not-loaded"}]})
        self.assertIsNone(O.choisir_modele_puissant(api, self.PS))

    def test_sans_taille_on_garde_le_premier(self):
        self.assertEqual(O.choisir_modele_puissant(self.API, None), "google/gemma-4-12b-qat")
        self.assertEqual(O.choisir_modele_puissant(self.API, "pas du json"), "google/gemma-4-12b-qat")

    def test_copie_supplementaire(self):
        api = json.dumps({"data": [{"id": "gros:2", "type": "llm", "state": "loaded"},
                                   {"id": "moyen", "type": "llm", "state": "loaded"}]})
        ps = json.dumps([{"identifier": "gros:2", "modelKey": "gros", "sizeBytes": 9e9},
                         {"identifier": "moyen", "modelKey": "moyen", "sizeBytes": 5e9}])
        self.assertEqual(O.choisir_modele_puissant(api, ps), "gros")

    def test_sans_api_on_utilise_lms_ps(self):
        self.assertEqual(O.choisir_modele_puissant(None, self.PS), "google/gemma-4-12b-qat")

    def test_rien_de_charge(self):
        self.assertIsNone(O.choisir_modele_puissant(json.dumps({"data": []}), "[]"))
        self.assertIsNone(O.choisir_modele_puissant(None, None))


# ---------------------------------------------------------------------------
# 5. Conversations Open WebUI
# ---------------------------------------------------------------------------

class TestAnalyseConversations(unittest.TestCase):
    def test_liste_triee_du_plus_recent(self):
        corps = json.dumps([{"id": "a", "updated_at": 100}, {"id": "b", "updated_at": 300},
                            {"id": "c", "updated_at": 200}])
        self.assertEqual(O.analyser_liste_conversations(corps), ["b", "c", "a"])

    def test_liste_format_items_et_ids_douteux(self):
        corps = json.dumps({"items": [{"id": "ok-1", "updated_at": 1},
                                      {"id": "../../admin", "updated_at": 9}, {"titre": "sans id"}]})
        self.assertEqual(O.analyser_liste_conversations(corps), ["ok-1"])

    def test_liste_illisible(self):
        with self.assertRaises(ValueError):
            O.analyser_liste_conversations("<html>")

    def test_modeles_d_une_conversation(self):
        detail = json.dumps({"id": "x", "chat": {
            "models": ["crew-normal"],
            "messages": [{"role": "user"}, {"role": "assistant", "model": "gemma"}],
            "history": {"messages": {"m1": {"model": "crew-ultra"}}}}})
        self.assertEqual(O.modeles_de_conversation(detail), {"crew-normal", "gemma", "crew-ultra"})
        self.assertTrue(O.utilise_crew({"gemma", "crew-maxperf"}))
        self.assertFalse(O.utilise_crew({"gemma", "mon-crew"}))
        self.assertEqual(O.modeles_de_conversation("pas du json"), set())


class TestOuvrir(unittest.TestCase):
    def setUp(self):
        self.sim = Simulateur()
        self.sim.tout_allumer()
        self.sim.cles["OPENWEBUI_API_KEY"] = "cle-webui-secrete"
        self.ctrl = L.Controleur(self.sim)
        self.ouvreur = O.Ouvreur(self.sim, self.ctrl)

    def conv(self, ident, date, modeles=(), modeles_messages=()):
        self.sim.conversations.append({"id": ident, "updated_at": date, "models": list(modeles),
                                       "models_messages": list(modeles_messages)})

    def test_derniere_conversation_crew(self):
        self.conv("ancienne-crew", 100, ["crew-normal"])
        self.conv("recente-crew", 200, ["crew-maxperf"])
        self.conv("tres-recente-gemma", 300, ["google/gemma-4-12b-qat"])
        o = self.ouvreur.preparer("openwebui")
        self.assertEqual(o.cible, "http://localhost:3000/c/recente-crew")
        self.assertEqual(o.message, "")
        self.assertTrue(all(a for _m, _u, a in self.sim.requetes if "/api/v1/chats" in _u))

    def test_modele_crew_seulement_dans_les_messages(self):
        self.conv("conv", 100, ["gemma"], ["crew-confidentiel"])
        self.assertEqual(self.ouvreur.preparer("openwebui").cible, "http://localhost:3000/c/conv")

    def test_format_items(self):
        self.sim.webui_liste_format = "items"
        self.conv("conv", 100, ["crew-normal"])
        self.assertEqual(self.ouvreur.preparer("openwebui").cible, "http://localhost:3000/c/conv")

    def test_aucune_conversation_crew(self):
        self.conv("autre", 100, ["gemma"])
        o = self.ouvreur.preparer("openwebui")
        self.assertEqual(o.cible, "http://localhost:3000/?model=crew-normal")
        self.assertIn("nouvelle conversation", o.message)

    def test_cle_absente_ou_refusee(self):
        self.conv("conv", 100, ["crew-normal"])
        self.sim.cles["OPENWEBUI_API_KEY"] = "mauvaise"
        o = self.ouvreur.preparer("openwebui")
        self.assertEqual(o.cible, R.URL_WEBUI_NOUVELLE_CREW)
        self.assertIn("clé refusée", o.message)
        del self.sim.cles["OPENWEBUI_API_KEY"]
        o = self.ouvreur.preparer("openwebui")
        self.assertEqual(o.cible, R.URL_WEBUI_NOUVELLE_CREW)
        self.assertIn("absente", o.message)

    def test_recherche_limitee(self):
        for n in range(50):
            self.conv(f"c{n}", 1000 - n, ["gemma"])
        self.conv("vieille-crew", 1, ["crew-normal"])
        o = self.ouvreur.preparer("openwebui")
        self.assertEqual(o.cible, R.URL_WEBUI_NOUVELLE_CREW)
        details = [u for _m, u, _a in self.sim.requetes if "/api/v1/chats/c" in u or "vieille" in u]
        self.assertEqual(len(details), R.CONVERSATIONS_EXAMINEES)

    def test_ouverture_url_locale_seulement(self):
        self.ouvreur.executer(O.Ouverture("url", "http://localhost:3000/c/x"))
        self.assertEqual(self.sim.ouvertures[-1], "http://localhost:3000/c/x")
        with self.assertRaises(ValueError):
            self.ouvreur.executer(O.Ouverture("url", "https://example.com"))

    def test_lmstudio_sans_charger_de_modele(self):
        self.sim.autres_modeles_charges = [("qwen3-32b", "llm", 19_000_000_000)]
        avant = dict(self.sim.modeles)
        o = self.ouvreur.preparer("lmstudio")
        self.assertEqual(o.genre, "programme")
        self.assertEqual(o.cible, R.LMSTUDIO_EXE_CANDIDATS[0])
        self.assertEqual(o.presse_papiers, "qwen3-32b")
        self.assertIn("qwen3-32b", o.message)
        self.assertEqual(self.sim.modeles, avant)
        self.assertFalse([c for c in self.sim.commandes if c[1:2] in (["load"], ["unload"])])

    def test_lmstudio_gemma_est_le_plus_gros_par_defaut(self):
        self.assertEqual(self.ouvreur.preparer("lmstudio").presse_papiers, R.MODELE_GEMMA)

    def test_lmstudio_aucun_modele(self):
        self.sim.modeles = {k: 0 for k in self.sim.modeles}
        o = self.ouvreur.preparer("lmstudio")
        self.assertIsNone(o.presse_papiers)
        self.assertIn("Aucun modèle", o.message)

    def test_lmstudio_introuvable(self):
        self.sim.lmstudio_installe = False
        with self.assertRaises(L.ErreurAction):
            self.ouvreur.preparer("lmstudio")

    def test_docker(self):
        o = self.ouvreur.preparer("docker")
        self.assertEqual((o.genre, o.cible), ("programme", R.DOCKER_DESKTOP_CANDIDATS[0]))

    def test_la_cle_webui_n_apparait_nulle_part(self):
        self.conv("conv", 100, ["crew-normal"])
        with self.assertLogs("panneau", level="DEBUG") as cap:
            o = self.ouvreur.preparer("openwebui")
            self.ouvreur.executer(o)
        self.assertNotIn("cle-webui-secrete", "\n".join(cap.output) + repr(o))


# ---------------------------------------------------------------------------
# 6. Fichiers livrés
# ---------------------------------------------------------------------------

class TestFichiers(unittest.TestCase):
    def test_script_raccourci_en_utf8_avec_bom(self):
        """Sans BOM, PowerShell 5.1 abîme les accents de la description du raccourci."""
        with open(os.path.join(DOSSIER, "creer_raccourci.ps1"), "rb") as f:
            debut = f.read(3)
        self.assertEqual(debut, b"\xef\xbb\xbf")

    def test_nouvelles_adresses_locales(self):
        for url in (R.URL_CREW_MODE, R.URL_CREW_MOTEURS, R.URL_WEBUI_CONVERSATIONS,
                    R.URL_WEBUI_NOUVELLE_CREW, R.URL_WEBUI_CONVERSATION.format(id="x")):
            self.assertTrue(L.url_est_locale(url), url)


if __name__ == "__main__":
    unittest.main()
