# Autorisations « Claude et Codex dans Crew » + correction du saut de la page à la frappe

## 1. IA sur abonnement dans Crew
**Fait**
- **Écran** : Réglages de la salle Crew → sous le menu de modèles, pour Claude et ChatGPT/Codex : interrupteur « Autoriser Crew à utiliser … » (décoché par défaut), limite par jour (1 à 500, vérifiée avant envoi), « X appels utilisés aujourd'hui ». Le texte d'aide demandé est affiché. Crew arrêté : message à la place des réglages, le menu de modèles reste utilisable.
- **Confirmation** avant d'AUTORISER (dialogue court avec les trois points). Désautoriser : sans confirmation. Un changement de limite seul : sans confirmation.
- **Jamais d'envoi automatique** : le PUT ne part que sur le clic « Enregistrer » (et seulement pour ce qui a changé) ; ouvrir la salle ou les réglages, rafraîchir, lister les IA n'envoient que des GET. Annuler la confirmation n'envoie rien.
- **Liste des IA de Crew** (page Centre, « État des IA utilisées par Crew » et tkinter) : Claude et Codex apparaissent avec le libellé « abonnement » et la raison (`detail`) au lieu d'être cachés.
- **Serveur du Centre** : `GET /api/crew/autorisations` (lecture) et `PUT /api/crew/autorisations` (session obligatoire, en-tête anti-CSRF, NIP reconfirmé à distance comme les autres actions sensibles) ; la clé Crew reste côté serveur. Le Centre valide aussi nom, booléen et limite AVANT d'appeler Crew (400) ; un 400 de Crew est relayé ; Crew arrêté : 422 sans appel. Un reçu (sans secret) est écrit pour chaque changement.
- **Panneau tkinter** : ajout du mot « abonnement » dans la liste des IA (rien d'autre : l'interrupteur n'y est pas, ce n'était pas simple).
- **Faux Crew** (`panneau/simulateur.py`) : `/autorisations` (GET/PUT, 400 comme le vrai), Claude et Codex dans `/moteurs` avec `abonnement`, `etat` et `detail` (non autorisée / limite atteinte / programme introuvable).

**Supposé** (contrat lu tel que donné, non essayé contre le vrai Crew)
- `abonnement` absent de `/moteurs` = `false` ; les autres champs de `/autorisations` absents = valeurs par défaut (20 / 0 / décoché).
- Le PUT renvoie bien la liste complète (le Centre ne relit pas après).
- Le PUT envoie toujours `nom`, `autorise` et `limite_jour` (l'écran envoie la limite affichée) ; un PUT sans `limite_jour` reste possible côté serveur.
- Pas d'autre IA que `claude` et `codex` dans `/autorisations` (les autres noms sont ignorés à la lecture).

## 2. Autre correction : la page « sautait » quand on écrit
- **Cause probable** (non reproduite à l'identique ici, mais mesurée) : (a) à chaque touche, la zone de saisie était repliée puis rouverte pour mesurer sa hauteur ; (b) quand une ligne s'ajoutait, le bas d'écran grandissait et le dernier message disparaissait sous lui ; (c) avec la table ronde, tout le bas d'écran était reconstruit après chaque estimation de coût (oscillation de 2 px mesurée sur téléphone) et le texte du coût changeait de nombre de lignes ; (d) le petit texte de coût du bas pouvait passer à la ligne.
- **Correctifs** : hauteur mesurée sur un miroir invisible (la vraie zone n'est plus touchée) ; le fil reste collé en bas quand le bas d'écran change de taille ; table ronde : mise à jour du coût SUR PLACE (reconstruction seulement si une IA change de disponibilité) et 2 lignes réservées pour le coût ; petit texte de coût sur une seule ligne.
- **Mesure** (Playwright, téléphone et PC, frappe caractère par caractère) : plus d'oscillation ; quand une ligne s'ajoute, le dernier message monte avec le bas d'écran au lieu de se cacher (avant : jusqu'à 93 px cachés).
- **Correctif annexe trouvé en chemin** : un dialogue enchaîné après un formulaire (ex. confirmation) s'annulait tout seul (l'événement « close » du premier tombait sur le second). Corrigé dans `app.js` ; cela touchait aussi d'autres enchaînements de dialogues.
- **Pas essayé** sur le vrai téléphone (clavier iOS/Android) : si ça saute encore, dites-moi sur quel appareil et quelle page.

## Vérifié
Tests : Centre 380, panneau 107 (dont les nouveaux fichiers `test_autorisations_crew.py` et une classe dans `panneau/tests/test_v2.py` ; la route est ajoutée au test des actions sensibles/NIP). Écran en mode démo, largeur de téléphone : rien envoyé à l'ouverture ni à l'annulation, limite invalide refusée, confirmation puis PUT, désautorisation sans confirmation, aucun débordement, aucune erreur console.
