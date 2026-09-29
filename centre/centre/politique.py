# -*- coding: utf-8 -*-
"""
Politique de confidentialité, appliquée PAR LE SERVEUR (l'interface ne fait que l'afficher).

- Modes de Crew « econome » et « maxperf » : le nuage est permis.
- Modes « confidentiel » et « ultra » : rien ne quitte le PC. Seules les salles locales restent actives,
  et la voix est désactivée.
- Mode inconnu ou illisible : on se comporte comme en confidentiel (dans le doute, rien ne sort).
- Une conversation qui a touché du contenu PRIVÉ (mémoire zone « prive », tiroir privé) ne peut plus
  jamais être envoyée à une IA du nuage.
"""

import threading
import time

MODES_NUAGE = ("econome", "maxperf")
MODES_LOCAUX = ("confidentiel", "ultra")
DUREE_CACHE = 2.0


class Politique:
    def __init__(self, centre, horloge=time.monotonic):
        self.centre = centre
        self.horloge = horloge
        self._cache = None
        self._verrou = threading.Lock()

    def mode(self):
        """(identifiant du mode ou None, libellé)."""
        with self._verrou:
            if self._cache and self.horloge() - self._cache[0] < DUREE_CACHE:
                return self._cache[1]
        crew_actif = self.centre.etats["crew"].code == self.centre.L.ACTIF
        try:
            info = self.centre.crew.lire_mode(crew_actif=crew_actif)
            resultat = (info.actuel, info.libelle() if info.actuel else "inconnu")
        except Exception:
            resultat = (None, "inconnu")
        with self._verrou:
            self._cache = (self.horloge(), resultat)
        return resultat

    def oublier(self):
        with self._verrou:
            self._cache = None

    def nuage_autorise(self):
        """(autorisé, message)."""
        mode, libelle = self.mode()
        if mode in MODES_NUAGE:
            return True, ""
        if mode in MODES_LOCAUX:
            return False, (f"Le mode « {libelle} » est actif : rien ne doit quitter le PC. "
                           "Seules les salles locales (gemma, Crew) sont disponibles.")
        return False, ("Le mode de Crew est inconnu ou illisible : par prudence, rien ne quitte le PC. "
                       "Seules les salles locales (gemma, Crew) sont disponibles.")

    def voix_autorisee(self):
        ok, msg = self.nuage_autorise()
        if ok:
            return True, ""
        return False, msg.replace("Seules les salles locales (gemma, Crew) sont disponibles.",
                                  "La voix passe forcément par le nuage : elle est désactivée.")
