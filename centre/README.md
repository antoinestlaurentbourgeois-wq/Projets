# Centre de contrôle

Une seule application, dans votre navigateur (et plus tard sur votre téléphone), pour piloter toute votre IA.
**Phase 1 :** le socle, la page **Centre** (tout ce que fait le panneau « Mon IA locale ») et la page **Coûts**.
**Phase 2 :** les **Salles** (une par IA : Crew, Claude, ChatGPT/Codex, Gemini, Grok, DeepSeek, gemma) et le **Tiroir** partagé.
**Phase 3 :** la **Voix** : conversation en direct (OpenAI Realtime ou Grok Voice, voix du nuage) avec outils pour consulter toutes les salles et la mémoire,
et talkie-walkie (appuyer pour parler). Coût en direct, coupure automatique au plafond, désactivée en modes Confidentiel/Ultra-confidentiel.
**Phase 4 :** l'**accès téléphone** par Tailscale Serve (HTTPS, réseau privé seulement) : voir `TELEPHONE.md` et la revue `SECURITE-TELEPHONE.md`.
**Phase 5 :** les extras : **Rappels** et **bulletin du matin**, **Départements** (démarrages rapides), **Vérifier** une réponse par une autre IA (Truth Gate),
**gardien** (santé toutes les 10 minutes), **sauvegarde de nuit** sans secrets, **rapport d'usage**.

Le panneau tkinter reste en place et fonctionne toujours : c'est votre solution de secours.

## Ce que ça fait aujourd'hui

- **Verrou** : NIP (6 chiffres ou plus) **et** mot secret (10 caractères ou plus). Session de 12 h. Après 5 erreurs de suite,
  le verrou impose une attente (30 s, puis 1 min, 2 min… jusqu'à 15 min).
- **Centre** : voyants et interrupteurs (Docker, Open WebUI, Kokoro, LM Studio, gemma, embeddings, Crew), **Mode jeu**,
  **Tout démarrer**, mode de Crew avec les « i » d'explication, « État des IA utilisées par Crew », clés API (présente/absente),
  et clic sur le nom d'Open WebUI, LM Studio ou Docker pour les ouvrir sur le PC.
- **Coûts** : dépenses estimées par IA (aujourd'hui, ce mois-ci), solde DeepSeek, **plafonds par jour et par mois** que vous réglez.
  Au plafond, les IA payantes seront refusées avec un message clair (les salles de la phase 2 s'y brancheront ; les IA locales ne sont jamais bloquées).
- **Salles** : discussion écrite avec chaque IA, réponses en continu, historique sur le PC, bouton **« Demander aussi à… »** (deuxième avis),
  mémoire de Crew, tiroir partagé, coût estimé avant chaque envoi. **La confidentialité est appliquée par le serveur** : en mode Confidentiel/Ultra-confidentiel
  seules gemma et Crew répondent, et un contenu privé ne va jamais à une IA du nuage. Claude, Codex et Gemini (programmes officiels, votre abonnement)
  travaillent dans `I:\IA\ATELIER`, en lecture seule ; toute action sensible passe par un **bouton d'approbation**. Jamais de `--dangerously-skip-permissions`.
  Voir `VERIFICATIONS-phase2.md` et `INCONNUS-phase2.md`.
- **Voix** : LIVE (le serveur du PC parle au fournisseur : votre clé ne quitte pas le PC, le coût est compté en direct, coupure au plafond, durée maximale,
  fermeture après silence) et **talkie-walkie**. Voir `VERIFICATIONS-phase3.md` et `INCONNUS-phase3.md`. `scripts\demo.bat` permet d'essayer sans clé ni dépense.
- **Journal** : les « reçus » (qui a fait quoi, quand) et le journal du serveur. Aucune clé n'y apparaît jamais.
- **Application installable** (PWA) : dans Chrome ou Edge, menu ⋮ → « Installer l'application ».

## Sécurité (résumé)

- Le serveur n'écoute **que sur `127.0.0.1:8740`** (ce n'est pas réglable). Aucune alerte du pare-feu Windows ne doit apparaître.
- Chaque adresse exige une session, sauf la page de connexion et ses fichiers.
- Vos clés (DeepSeek, Crew…) ne sont lues que par le serveur, sur le PC : jamais envoyées au navigateur, jamais écrites dans un journal.
- Le NIP et le mot secret ne sont jamais gardés : seulement une empreinte (scrypt avec sel).
- Protection contre les attaques par un autre site web (en-tête obligatoire, vérification de l'origine, cookie `SameSite=Strict`) et contre le « DNS rebinding » (l'adresse demandée est vérifiée).

## Installation (10 minutes)

Rien n'est installé sur C: (à part le raccourci du bureau).

1. **Récupérer les fichiers.** Sur GitHub, branche `claude/new-session-bl6q4z` → **Code → Download ZIP**, sur le disque **I:**.
2. **Copier le dossier `centre`** pour obtenir `I:\Python\centre\` (avec `requirements.txt`, `centre\`, `scripts\` directement dedans).
   Le dossier du panneau doit rester à `I:\Python\crewai-routage\panneau\` (il est réutilisé, pas recopié).
3. **Double-cliquez sur `scripts\installer.bat`.** Il crée l'environnement Python dans `I:\Python\centre\.venv` et installe Starlette et uvicorn.
4. **Double-cliquez sur `scripts\definir_verrou.bat`** : choisissez votre NIP et votre mot secret (rien ne s'affiche pendant la saisie, c'est normal).
5. **Essayer sans risque (facultatif) :** `scripts\demo.bat` ouvre le Centre avec un PC **simulé** (NIP `123456`, mot secret `motsecret-demo`).
   Allez sur http://127.0.0.1:8740 . Fermez la fenêtre pour arrêter.
6. **Double-cliquez sur `scripts\creer_raccourci.bat`** : un raccourci « Centre de contrôle » apparaît sur le bureau.
   Il démarre le serveur sans fenêtre (s'il ne tourne pas) puis ouvre le navigateur.
7. **Vérification automatique :** `scripts\tester_centre.bat` (après avoir démarré le Centre).
8. **Gardien et sauvegarde de nuit :** `scripts\installer_taches.bat` (deux tâches du Planificateur de tâches Windows).
9. **Téléphone (facultatif) :** suivez `TELEPHONE.md`.

Puis suivez `VERIFICATIONS.md`, `VERIFICATIONS-phase2.md` … `VERIFICATIONS-phase5.md` (les listes à cocher), et lisez les `INCONNUS-phase*.md` (ce que je n'ai pas pu vérifier).

## Au quotidien

| Je veux… | Je fais… |
|---|---|
| Ouvrir le Centre | Raccourci du bureau (ou http://127.0.0.1:8740) |
| Voir les erreurs du serveur | `scripts\serveur_visible.bat` (après `arreter_centre.bat`), ou page **Journal**, ou `I:\IA\CENTRE\donnees\centre.log` |
| Arrêter le serveur | `scripts\arreter_centre.bat` |
| Changer NIP / mot secret | `scripts\definir_verrou.bat` (déconnecte toutes les sessions) |
| Mot de passe oublié | Relancez `definir_verrou.bat` : il remplace l'ancien |

## Où sont les données

`I:\IA\CENTRE\donnees\` : `verrou.json` (empreintes), `centre.log`, `recus.jsonl`, `depenses.jsonl`, `plafonds.json`, `tarifs.json`, `salles.json`,
`conversations\`, `tiroir.json`, `rappels.json`, `gardien.json`, `taches.log`, `reglages.json` (à éditer à la main : hôtes Tailscale, chemins des programmes…),
`departements\` (vos départements). Sauvegardes : `I:\IA\CENTRE\sauvegardes\`. Aucune clé n'y est en clair.

## Pour les curieux

- Serveur : Python 3.12, Starlette, uvicorn. Interface : HTML/CSS/JavaScript simples, sans compilation.
- `centre/service.py` réutilise `Controleur`, `CrewDistant` et `Ouvreur` du panneau : la logique n'est pas réécrite.
- Tests : `scripts\lancer_tests.bat` (tous avec simulateur, aucune vraie commande, aucun vrai réseau).
- Réglages : variables d'environnement `CENTRE_PANNEAU` (dossier du panneau), `CENTRE_DONNEES` (dossier des données),
  `CENTRE_HOTES` (noms d'hôte supplémentaires acceptés, pour Tailscale en phase 4).
- **Licence GLAMMBOX :** aucun code de GLAMMBOX n'est utilisé en phase 1 (voir `INCONNUS.md`).

**Crew :** le coût de la salle Crew est le coût **réel** renvoyé par Crew (`usage.cout_usd`). Crew consulte lui-même la mémoire avant chaque tâche : la case « Utiliser la mémoire » n'ajoute donc rien dans la salle Crew. La première recherche en mémoire peut prendre ~10 s (chargement des modèles).

## L'interface (refonte inspirée du cockpit GLAMMBOX)

Un seul écran : **Salles** est l'accueil. En haut, le **noyau** animé indique l'état (prêt, à l'écoute, réflexion, je parle), puis les pages en pastilles
(Salles, Centre, Voix, Tiroir, Rappels, Départements, Coûts, Journal) et une barre d'état (voyants Docker / LM Studio / gemma / Crew, mode de Crew, dépense du jour).
En bas de la page Salles : le grand bouton **MAINTENIR POUR PARLER** (transcription → envoi → lecture de la réponse si « 🔊 Voix » est activé), la saisie
(une conversation se crée toute seule au premier message) et les bascules **Live**, **Mémoire**, **Voix**, **Tiroir**, **Écriture** (Codex) et **Stop**.
Thème sombre par défaut (clair si votre système le demande). Les autres pages s'ouvrent comme des fiches, avec « ‹ Retour aux salles ».

## Table ronde (salle Crew)

Dans la salle Crew, l'interrupteur « 🎯 Table ronde » ouvre une liste d'IA à cocher (par défaut : gemma, Gemini, DeepSeek ; les indisponibles sont grisées avec la raison). Le coût estimé total s'affiche **avant** l'envoi ; au-dessus du seuil (`seuil_table_ronde_usd` dans `reglages.json`, 0,10 $ par défaut) une confirmation est demandée. Le message part en un seul appel vers Crew, les réponses arrivent en colonnes (l'une sous l'autre sur téléphone), la synthèse de Crew en dernier. Option « tour de critique » : 2e tour, surcoût affiché avant activation. Les IA exclues par Crew (contenu confidentiel) sont marquées comme telles, jamais contournées. Contrat avec Crew : voir `RETOUR-table-ronde-suite.md` (aligné sur le vrai Crew).

## Chef d'équipe (page « 🧠 Chef d'équipe »)
Choisit le modèle LM Studio qui sert de chef local à Crew (gemma par défaut). Un seul interrupteur actif ; Crew fait le changement (PUT /chef). Chaque modèle a sa salle, une seule est verte (le chef). Voir `RETOUR-chef-crew.md`.
