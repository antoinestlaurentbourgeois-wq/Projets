# Vérifications manuelles sur votre PC

Faites-les une fois après l'installation, dans l'ordre. Cochez au fur et à mesure.
Comptez environ **30 minutes** (le chargement de gemma et le démarrage de Docker prennent du temps).

**Si quelque chose ne correspond pas au « Résultat attendu »** : notez le numéro de l'étape, cliquez sur
le bouton **Journal** du panneau et copiez les dernières lignes. Avec ces deux informations, je pourrai
corriger le problème.

> Astuce : gardez le **Gestionnaire des tâches** ouvert (Ctrl + Maj + Échap), onglet **Performances → GPU**,
> pour voir la mémoire vidéo utilisée (« Mémoire GPU dédiée »).

---

## A. Avant de commencer

- [ ] **A1. Tests automatiques.** Double-cliquez sur `lancer_tests.bat`.
  *Résultat attendu :* la dernière ligne affiche `OK` (59 tests).
- [ ] **A2. Mode démo.** Double-cliquez sur `demo.bat`, cliquez sur **Tout démarrer**, puis sur **Mode jeu**.
  *Résultat attendu :* les voyants passent à l'orange puis au vert, puis au rouge. Rien ne se passe
  réellement sur le PC (Docker et LM Studio ne bougent pas). Fermez la fenêtre de démo.
- [ ] **A3.** Démarrez votre installation comme d'habitude (tout allumé), **sans** passer par le panneau.

## B. Ouverture et voyants

- [ ] **B1.** Double-cliquez sur le raccourci **Panneau IA locale** du bureau.
  *Attendu :* la fenêtre s'ouvre en quelques secondes, **sans fenêtre noire**, même brièvement.
- [ ] **B2.** Attendez 10 secondes.
  *Attendu :* les 7 voyants sont **verts**, sans message rouge en dessous.
- [ ] **B3. Clés API.**
  *Attendu :* `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `OPENWEBUI_API_KEY` affichent « présente » pour celles
  que vous avez définies, « absente » sinon. **Aucune valeur de clé n'apparaît.**
- [ ] **B4. Vérification croisée.** Ouvrez http://localhost:3000 dans votre navigateur.
  *Attendu :* Open WebUI s'affiche (cohérent avec le voyant vert).
- [ ] **B5. Pas de console qui clignote.** Observez l'écran pendant 30 secondes.
  *Attendu :* aucune fenêtre noire n'apparaît, même furtivement (les vérifications ont lieu toutes les 5 s).
- [ ] **B6. Un seul panneau.** Double-cliquez à nouveau sur le raccourci.
  *Attendu :* un message « Le panneau est déjà ouvert ».

## C. Chaque interrupteur, un par un

Pour chaque test : cliquez sur l'interrupteur, observez le voyant (**orange** pendant l'action, puis
**rouge** ou **vert**), puis rallumez.

- [ ] **C1. Serveur Crew — éteindre.**
  *Attendu :* orange puis rouge en quelques secondes. Dans le Gestionnaire des tâches (onglet **Détails**),
  plus aucun `pythonw.exe` lié à Crew (vous pouvez ajouter la colonne « Ligne de commande » par un clic droit
  sur l'en-tête des colonnes).
- [ ] **C2. Serveur Crew — rallumer.**
  *Attendu :* orange puis vert (jusqu'à ~1 min). Deux `pythonw.exe` avec `serveur_crew.py` réapparaissent.
- [ ] **C3. Crew survit à la fermeture du panneau** (le test le plus important pour WMI).
  Fermez le panneau (croix), attendez 10 s, rouvrez-le.
  *Attendu :* le Serveur Crew est toujours **vert**.
- [ ] **C4. Modèle d'embeddings — éteindre puis rallumer.**
  *Attendu :* rouge « Non chargé », puis vert. Dans LM Studio (onglet des modèles chargés),
  **une seule** copie de nomic-embed.
- [ ] **C5. Modèle gemma — éteindre.**
  *Attendu :* une question « Serveur Crew dépend de Modèle gemma… Les éteindre aussi ? ».
  Répondez **Non** → rien ne change. Recommencez et répondez **Oui** → Crew s'éteint, puis gemma.
  La mémoire GPU dédiée baisse d'environ 7 Go.
- [ ] **C6. Modèle gemma — rallumer.**
  *Attendu :* orange « Chargement en mémoire vidéo… » (1 à 3 min), puis vert, **sans** message
  « 2 copies ». Dans LM Studio : **un seul** gemma chargé, avec un contexte de 32 000.
- [ ] **C7. Serveur Crew — rallumer** (gemma est chargé). *Attendu :* vert.
- [ ] **C8. Serveur LM Studio — éteindre.**
  *Attendu :* une question proposant d'éteindre aussi Crew, gemma et embeddings. Répondez **Oui**.
  Tous passent au rouge dans l'ordre Crew → embeddings → gemma → serveur. Les modèles affichent
  « Non chargé (serveur LM Studio arrêté) ».
- [ ] **C9. Serveur Crew — allumer alors que tout LM Studio est éteint.**
  *Attendu :* une question « Serveur Crew a besoin de : Serveur LM Studio, Modèle gemma. Les allumer
  d'abord ? ». Répondez **Oui** → serveur, puis gemma, puis Crew passent au vert. Rallumez ensuite les
  embeddings.
- [ ] **C10. Kokoro — éteindre puis rallumer.** *Attendu :* rouge « Conteneur arrêté », puis vert.
- [ ] **C11. Open WebUI — éteindre puis rallumer.**
  *Attendu :* rouge, puis orange « Open WebUI démarre… » (jusqu'à 1-2 min), puis vert.
- [ ] **C12. Docker Desktop — éteindre.**
  *Attendu :* une question proposant d'éteindre Kokoro et Open WebUI. **Oui** → les trois passent au rouge.
  Open WebUI et Kokoro affichent « Docker n'est pas lancé : … ne peut pas démarrer ».
  **Notez le message sous Docker** : s'il indique « Arrêté par fermeture forcée », c'est que
  `docker desktop stop` n'existe pas dans votre version (dites-le-moi).
- [ ] **C13. Open WebUI — allumer alors que Docker est éteint.**
  *Attendu :* question « Open WebUI a besoin de : Docker Desktop… ». **Oui** → Docker démarre
  (jusqu'à 2 min), puis Open WebUI. Rallumez ensuite Kokoro.

## D. Mode jeu

- [ ] **D1.** Tout est vert. Cliquez sur **Mode jeu**, confirmez.
  *Attendu :* les voyants passent au rouge dans l'ordre : Crew, embeddings, gemma, serveur LM Studio,
  Kokoro, Open WebUI, Docker. En bas : « Mode jeu : tout est éteint. Bon jeu ! ».
- [ ] **D2. Mémoire libérée.** Dans le Gestionnaire des tâches :
  - la **mémoire GPU dédiée** a baissé d'environ 7 Go ou plus ;
  - l'onglet **Processus** ne montre plus `Docker Desktop` ; `VmmemWSL` a disparu ou fortement diminué
    (sinon, voir le point 2 du README) ;
  - il n'y a plus de `pythonw.exe` du serveur Crew.
- [ ] **D3. Le panneau ne rallume rien tout seul.** Laissez le panneau ouvert 2 minutes.
  *Attendu :* tout reste rouge, LM Studio et Docker ne se relancent pas.

## E. Tout démarrer

- [ ] **E1.** Cliquez sur **Tout démarrer**.
  *Attendu :* dans l'ordre Docker → Open WebUI → Kokoro → serveur LM Studio → gemma → embeddings → Crew.
  Au bout de 3 à 5 minutes, tout est vert, et en bas : « Tout démarrer : terminé. ».
- [ ] **E2. La fenêtre ne gèle pas.** Pendant **Tout démarrer**, déplacez et redimensionnez la fenêtre.
  *Attendu :* elle réagit normalement. Un clic sur un interrupteur fait « bip » (une action à la fois).
- [ ] **E3. Pas de doublon.** Cliquez à nouveau sur **Tout démarrer** alors que tout est vert.
  *Attendu :* tout reste vert, rien n'est rechargé. Dans LM Studio : toujours **un seul** gemma.
- [ ] **E4.** Ouvrez http://localhost:3000 et posez une question qui utilise gemma, puis testez la voix
  (Kokoro) et vos agents Crew comme d'habitude.

## F. Journal

- [ ] **F1.** Cliquez sur **Journal**.
  *Attendu :* `panneau.log` s'ouvre dans le Bloc-notes, avec les actions (« Démarrage de … : terminé »).
- [ ] **F2.** Dans le Bloc-notes, faites Ctrl + F et cherchez le début de l'une de vos clés API.
  *Attendu :* **aucun résultat.**

---

**Tout est coché ?** Le panneau est prêt. Sinon, envoyez-moi le numéro de l'étape et les dernières lignes
du journal.
