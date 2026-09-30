# -*- coding: utf-8 -*-
"""
ComfyUI (images locales) dans le panneau : deux scripts fixes, jamais lancé par « Tout démarrer », arrêté par « Mode jeu ».
Uniquement avec le simulateur : aucune vraie commande.
"""

import os
import sys
import unittest

DOSSIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DOSSIER)

import reglages as R  # noqa: E402
import panneau_logique as L  # noqa: E402
from panneau_logique import ACTIF, ARRETE  # noqa: E402
from simulateur import Simulateur  # noqa: E402


def sans(*a, **k):
    pass


class TestComfyUI(unittest.TestCase):
    def setUp(self):
        self.sim = Simulateur()
        self.ctrl = L.Controleur(self.sim)

    def test_composant_present_sans_dependance_et_hors_tout_demarrer(self):
        c = L.PAR_ID["comfyui"]
        self.assertEqual(c.dependances, ())
        self.assertFalse(c.tout_demarrer)
        self.assertIn("comfyui", L.ordre_demarrage())
        self.assertNotIn("comfyui", L.ordre_tout_demarrer())
        self.assertEqual(L.ordre_arret()[0], "comfyui")
        self.assertIn("carte graphique", c.description)

    def test_voyant_selon_le_port_8188(self):
        self.assertEqual(self.ctrl.verifier("comfyui").code, ARRETE)
        self.sim.comfy_actif = True
        self.assertEqual(self.ctrl.verifier("comfyui").code, ACTIF)
        self.assertEqual(L.R.URL_COMFYUI, "http://127.0.0.1:8188/system_stats")

    def test_demarrer_appelle_le_script_en_liste_d_arguments(self):
        etat = self.ctrl.demarrer("comfyui", sans)
        self.assertEqual(etat.code, ACTIF)
        sens, script, args = self.sim.comfy_scripts[0]
        self.assertEqual(sens, "demarrer")
        self.assertEqual(script, R.DOSSIER_COMFYUI + "\\demarrer_comfyui.ps1")
        self.assertEqual(args[1:6], ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script])
        self.assertEqual(len(args), 6)                                   # aucun autre argument
        self.assertTrue(args[0].lower().endswith("powershell.exe"))

    def test_deja_demarre_ne_relance_rien(self):
        self.sim.comfy_actif = True
        self.assertEqual(self.ctrl.demarrer("comfyui", sans).code, ACTIF)
        self.assertEqual(self.sim.comfy_scripts, [])

    def test_arreter(self):
        self.sim.comfy_actif = True
        self.assertEqual(self.ctrl.arreter("comfyui", sans).code, ARRETE)
        self.assertEqual([s[0] for s in self.sim.comfy_scripts], ["arreter"])
        self.assertFalse(self.sim.comfy_actif)

    def test_echec_de_demarrage_indique_le_journal(self):
        self.sim.comfy_echec_demarrage = True
        etat = self.ctrl.demarrer("comfyui", sans)
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("comfyui.log", etat.message)
        self.assertNotIn("Traceback", etat.message)

    def test_scripts_absents_refus_clair(self):
        self.sim.comfy_installe = False
        etat = self.ctrl.demarrer("comfyui", sans)
        self.assertEqual(etat.code, ARRETE)
        self.assertIn("introuvable", etat.message)
        self.assertEqual(self.sim.comfy_scripts, [])

    def test_dossiers_refuses(self):
        for mauvais in ("", "relatif\\dossier", "I:\\IA\\..\\autre", "I:\\IA\\Comfy\"UI", "I:\\IA\\x\ny", None, 12, "I:\\IA\\a|b"):
            with self.assertRaises(L.ErreurAction, msg=repr(mauvais)):
                L.scripts_comfyui(self.sim, mauvais)
        self.ctrl.dossier_comfyui = "I:\\IA\\..\\autre"
        self.assertEqual(self.ctrl.demarrer("comfyui", sans).code, ARRETE)
        self.assertEqual(self.sim.comfy_scripts, [])

    def test_dossier_valide_autre(self):
        d, a = L.scripts_comfyui(self.sim, "D:\\Outils\\ComfyUI")
        self.assertEqual((d, a), ("D:\\Outils\\ComfyUI\\demarrer_comfyui.ps1", "D:\\Outils\\ComfyUI\\arreter_comfyui.ps1"))

    def test_tout_demarrer_ne_lance_jamais_comfyui(self):
        self.ctrl.tout_demarrer(sans)
        self.assertEqual(self.sim.comfy_scripts, [])
        self.assertFalse(self.sim.comfy_actif)

    def test_mode_jeu_arrete_comfyui_en_premier(self):
        self.sim.tout_allumer()
        self.sim.comfy_actif = True
        ev = []
        self.ctrl.mode_jeu(lambda i, e, f: ev.append(i) if f else None)
        self.assertEqual(ev[0], "comfyui")
        self.assertFalse(self.sim.comfy_actif)
        self.assertEqual(self.ctrl.verifier("comfyui").code, ARRETE)


if __name__ == "__main__":
    unittest.main()
