# « ultra » devient « ultra-confidentiel »

- **Menu de modèles de la salle Crew** : `crew-ultra` → `crew-ultra-confidentiel` (même explication). Un réglage déjà enregistré avec `crew-ultra` est repris automatiquement comme `crew-ultra-confidentiel` (pas de « inconnue »), et l'ancien nom est accepté à l'enregistrement.
- **Mode de Crew** : le Centre reconnaît `ultra-confidentiel` ET l'ancien `ultra` comme modes 100 % locaux (aucune IA du nuage, pas de voix, coûts nuls) : ni l'un ni l'autre ne peut ouvrir le nuage. Si le vrai Crew garde l'identifiant `ultra` pour le mode, rien à changer côté Centre.
- **Faux Crew et tests** : le mode s'appelle `ultra-confidentiel`; un test vérifie que l'ancien nom reste traité comme local.
- **Textes** : « Ultra » → « Ultra-confidentiel » dans l'écran (aide des IA sur abonnement, voix) et la documentation.
- **À confirmer avec la session de Crew** : nouveaux identifiants exacts (mode `ultra-confidentiel` ? modèle `crew-ultra-confidentiel` ?). Si Crew choisit d'autres noms, dites-les-moi : il suffit d'ajouter le nom aux listes `MODES_LOCAUX`, `MODES_CREW_LOCAUX` et `MODELES_CREW`.
- Tests : Centre 382, panneau 107.
