# Page « Chef d'équipe » et salles par modèle LM Studio

**À installer ENSEMBLE** : cette version du Centre ET la partie Crew (`GET/PUT /chef`, fichier `chef_crew.json`). Sans la partie Crew, la page s'affiche avec le chef lu dans le fichier (ou gemma) et les interrupteurs désactivés.

## Fait
- **Page « 🧠 Chef d'équipe »** (menu, lisible sur téléphone) : une ligne par modèle de `GET /chef` (nom, Go, paramètres, quantification, « chargé », avertissement). Interrupteur à glissière façon iOS (vrai `<button role="switch" aria-checked>`, focus visible, zone tactile 56 × 44 px). UN SEUL actif = le chef actuel ; le désactiver est impossible (bulle « Activez un autre modèle pour changer de chef »). Activer un autre : confirmation « Crew sera indisponible environ 30 secondes… » + avertissement du modèle ; rien ne part avant « Changer de chef ». Pendant le changement : interrupteurs désactivés, barre de progression + étape, lecture toutes les 2 s. Fin : bandeau vert (résultat du test) ou rouge (message d'échec + « Crew a remis … »). Test mauvais : bandeau d'avertissement « Ce modèle suit mal les consignes de Crew » + bouton « Revenir à <ancien chef> » (un nouveau PUT, toujours sur clic).
- **Crew arrêté / Mode jeu / LM Studio arrêté** : la page reste lisible, chef lu dans `chef_crew.json` (jamais modifié), interrupteurs désactivés avec la raison ; les modèles déjà vus restent listés (mémorisés dans `salles_lm.json`).
- **Relais Centre** : `GET /api/crew/chef` (lecture) et `PUT /api/crew/chef` (session, NIP à distance, anti-CSRF ; clé Crew côté serveur ; 400/409/503 de Crew relayés en français ; reçu `chef_crew` ok/refuse/erreur, sans secret ni NIP). Le PUT ne part que sur clic ; Crew arrêté : refusé sans appel.
- **Une salle par modèle** : la salle « gemma » garde son identifiant (modèle `google/gemma-4-12b-qat`) ; les autres modèles ont une salle `lm-<court nom>-<4 signes>` (sûre, stable). Une seule est verte (le chef, seul modèle chargé) ; les autres sont grisées (« Ce modèle n'est pas le chef d'équipe : activez-le dans la page Chef d'équipe » + bouton vers la page), leurs anciennes conversations restent lisibles, l'envoi est refusé par le serveur. Modèle disparu de LM Studio : salle visible en lecture seule (« modèle absent »). Nouveau modèle : sa salle apparaît à la prochaine lecture de `/chef`. Toutes ces salles sont LOCALES : sûres pour le privé, coût nul, jamais de nuage, utilisables en Confidentiel et Ultra-confidentiel.
- **Alignement sur le chef** : panneau et Centre lisent le chef (GET /chef, sinon fichier, sinon gemma). « Tout démarrer », « Mode jeu », voyants, arrêt/démarrage chargent et déchargent le CHEF ACTUEL avec SES réglages (`lms load <chef> --context-length N --parallel M`) après vérification de ce qui est déjà chargé : gemma n'est plus chargé en dur. Le voyant s'appelle « Chef local ».
- **Table ronde** : le participant `gemma` (identifiant du contrat inchangé) s'affiche « Chef local (<modèle>) » ; les autres modèles LM Studio n'y sont pas proposés.
- **Panneau tkinter** : même logique de chef (Controleur), libellé « Chef local ». Pas de page « Chef d'équipe » dans tkinter.

## Supposé (à confirmer avec la partie Crew)
- `GET /chef` est fiable quand Crew répond ; `changement` reste renvoyé après la fin (le Centre n'affiche le bandeau de résultat que pour un changement suivi ou de moins de 10 minutes).
- **`lms load --parallel`** : je l'ajoute avec le chef ; si la version de `lms` ne connaît pas l'option, le Centre/panneau recharge automatiquement avec le seul `--context-length`. À vérifier sur votre `lms`.
- Les réglages de chargement (contexte, parallèle) viennent de la ligne du chef dans `GET /chef.modeles`, sinon de `chef_crew.json`, sinon 32000 / 4.
- Identifiants de modèle : lettres, chiffres et `. _ : / @ + -`, sans `..`, sans tiret ni barre au début, 200 signes max ; sinon gemma (fichier) ou refus 400 (PUT).
- « Revenir à <ancien> » n'est proposé que si le Centre connaît l'ancien chef (mémorisé depuis le PUT ; perdu au redémarrage du Centre).
- Le Centre filtre aussi les modèles d'embeddings (`embed` dans l'id ou l'architecture) par prudence.
- Libellé des salles de modèles : le `libelle` donné par Crew ; salle « gemma » : toujours « gemma (local) ».
- Un modèle absent de `GET /chef` alors que LM Studio répond = « absent ». Si Crew ne liste pas gemma, la salle « gemma » n'est pas marquée absente tant qu'on ne l'a jamais vue dans la liste.

## Vérifié
Tests : Centre 409 (dont `tests/test_chef_crew.py`, 25), panneau 114 (chef, fichier, « Tout démarrer » sans gemma, mode jeu, `--parallel`). Écran en mode démo, largeur de téléphone : interrupteurs, bulle, confirmation/annulation (aucun PUT avant le clic), progression, bandeaux vert / rouge / avertissement + « Revenir », salles grisées et verte, aucun débordement, aucune erreur console. **Pas essayé avec le vrai Crew ni un vrai LM Studio.**
