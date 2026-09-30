# Menu de modèles de la salle Crew

**Fait** : dans Réglages de la salle Crew, le champ texte est remplacé par un menu déroulant.

- **Liste fixe** (`MODELES_CREW` dans `centre/salles.py`), sans rien demander à Crew : le menu marche même Crew arrêté.
  - `crew-normal` (par défaut) : Suit le mode choisi dans le panneau (Économe par défaut)
  - `crew-maxperf` : Équipe complète avec les modèles les plus puissants (plus cher)
  - `crew-confidentiel` : Tout reste en local (gemma)
  - `crew-ultra` : Tout est local, orchestration comprise
  - Pas de `crew-tableronde` : la table ronde garde son bouton et ses cases à cocher.
- **Explication du choix courant** affichée sous le menu, mise à jour quand on change de choix (le formulaire commun accepte maintenant `explications` sur un menu).
- **Valeur enregistrée hors liste** (ancienne valeur, faute de frappe) : affichée quand même, marquée « — inconnue », avec un avertissement, et `crew-normal` est proposé « pour remplacer ». Rien n'est supprimé en silence. Pour la ré-enregistrer telle quelle, c'est permis.
- **Ajout côté serveur (non demandé)** : pour Crew, une NOUVELLE valeur hors liste est refusée à l'enregistrement (« Modèle Crew inconnu… »), pour éviter la faute de frappe à la source. Les autres salles gardent le texte libre.
- L'API `GET /api/salles/crew/modeles` renvoie aussi `explications` et `defaut` (les autres salles : inchangé).

**Non touché** : `_defaut_modele` / ChatGPT sans `-m` en abonnement (test ajouté), table ronde.

**Vérifié** : 362 tests (7 nouveaux dans `tests/test_menu_modeles_crew.py` : liste, aucune requête réseau, valeur inconnue conservée et remplaçable, autres salles inchangées) ; écran en mode démo à largeur de téléphone (iPhone 13) : un seul menu, aucun champ texte, explication qui change, valeur inconnue signalée, aucun débordement, aucune erreur console. Pas essayé sur le PC.
