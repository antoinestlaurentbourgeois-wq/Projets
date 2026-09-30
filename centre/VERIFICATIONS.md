# Vérifications manuelles : phase 1

À faire sur votre PC, après l'installation. Cochez au fur et à mesure ; notez tout écart (message exact, capture d'écran).

## A. Démarrage et sécurité

- [ ] `scripts\tester_centre.bat` : toutes les lignes sont `[OK]`.
- [ ] Aucune alerte du pare-feu Windows au démarrage du serveur.
- [ ] Le raccourci du bureau démarre le serveur **sans fenêtre noire** et ouvre la page de connexion.
- [ ] Un mauvais NIP ou mot secret est refusé ; après 5 essais ratés, un message demande d'attendre.
- [ ] Bonne connexion → la page Centre s'affiche. « Se déconnecter » ramène à la connexion.
- [ ] Depuis un autre appareil du même réseau local : `http://<IP-du-PC>:8740` **ne répond pas** (le serveur est verrouillé sur le PC).
- [ ] Après `arreter_centre.bat`, la page ne répond plus ; `demarrer_centre.bat` la relance.
- [ ] Fermer la session Windows puis la rouvrir : le Centre ne se relance pas tout seul (normal) ; le raccourci le relance.

## B. Page Centre (comparer avec le panneau tkinter ouvert en même temps)

- [ ] Les voyants correspondent à ceux du panneau (Docker, Open WebUI, Kokoro, LM Studio, gemma, embeddings, Crew).
- [ ] Allumer/éteindre **Docker** avec l'interrupteur : le voyant passe à l'orange puis au vert / au rouge.
- [ ] Allumer **Crew** alors que gemma est éteint : la boîte propose d'allumer LM Studio et gemma d'abord. « Annuler » ne fait rien.
- [ ] Éteindre **LM Studio** alors que gemma et Crew sont allumés : la boîte propose de les éteindre aussi.
- [ ] **Mode jeu** : tout s'éteint, dans le bon ordre. La mémoire vidéo de la carte tombe (≈ 10,9 Go → ≈ 1,4 Go, à vérifier dans le Gestionnaire des tâches).
- [ ] **Tout démarrer** : tout se rallume (compter plusieurs minutes).
- [ ] Pendant une action, les interrupteurs sont grisés ; on ne peut pas en lancer une deuxième.
- [ ] **Mode de Crew** : la liste montre Économe, MaxPerf, Confidentiel, Ultra-confidentiel ; les « i » affichent les explications ; choisir un mode le change (vérifier dans le panneau tkinter).
- [ ] Crew éteint : le mode est quand même modifiable (message « Serveur Crew éteint »).
- [ ] « État des IA utilisées par Crew » : la liste s'affiche avec voyants, niveaux et coûts.
- [ ] Clés API : DEEPSEEK/GEMINI/OPENWEBUI affichées « présente » ou « absente » (jamais la valeur).
- [ ] Cliquer sur **Open WebUI**, **Serveur LM Studio**, **Docker Desktop** : l'application **s'ouvre sur le bureau** (voir INCONNUS n° 1).
  Si l'application est éteinte, la boîte propose de l'allumer d'abord.
- [ ] Le clic sur LM Studio copie le nom du modèle (à coller avec Ctrl+V dans LM Studio).

## C. Page Coûts

- [ ] « Solde DeepSeek » affiche un solde plausible (comparer avec la page web de DeepSeek). Message clair si Internet est coupé.
- [ ] Régler un plafond par jour de 1 $ et un par mois de 10 $ → enregistré ; recharger la page → toujours là.
- [ ] Un plafond par jour supérieur au plafond par mois est refusé avec un message.
- [ ] Les dépenses affichent 0,00 $ (normal : les salles de la phase 2 alimenteront les compteurs).

## D. Journal

- [ ] Page **Journal** : les actions faites plus haut apparaissent dans les reçus.
- [ ] Ouvrir `I:\IA\CENTRE\donnees\centre.log` et `recus.jsonl` avec le Bloc-notes : **aucune clé, aucun NIP, aucun mot secret**.
- [ ] Dans `I:\IA\CENTRE\donnees\verrou.json` : seulement de longues suites de caractères (empreintes).

## E. Application installable (PWA)

- [ ] Dans Chrome/Edge : menu ⋮ → « Installer Centre de contrôle » est proposé ; l'icône (cible bleue) apparaît.
- [ ] L'application installée s'ouvre dans sa propre fenêtre et demande la connexion.

## F. Le panneau existant

- [ ] Le panneau tkinter s'ouvre toujours et fonctionne comme avant.
- [ ] `scripts\lancer_tests.bat` : tous les tests passent (Centre + panneau).

## G. Table ronde (vrai Crew requis)
- [ ] Salle Crew : « Table ronde » activable ; cases avec coût estimé ; IA indisponibles grisées avec raison.
- [ ] Coût estimé affiché avant envoi ; confirmation au-dessus du seuil ; changer `seuil_table_ronde_usd` dans reglages.json.
- [ ] Un message → colonnes en flux avec coût réel + durée, puis synthèse de Crew.
- [ ] Question confidentielle : IA du nuage marquées « exclue : contenu confidentiel, traité en local seulement ».
- [ ] Tour de critique : surcoût affiché, 2e tour dans les colonnes.
- [ ] Crew arrêté / Mode jeu : table ronde désactivée, les autres salles marchent.
- [ ] Téléphone : colonnes repliables l'une sous l'autre.

## H. Chef d'équipe (vrai Crew + vrai LM Studio requis)
- [ ] Page « Chef d'équipe » : les modèles LLM de LM Studio sont listés (pas les embeddings), un seul interrupteur actif = le chef.
- [ ] Désactiver le chef : impossible (bulle). Activer un autre : confirmation, rien ne part avant « Changer de chef ».
- [ ] Changement : progression par étapes, puis bandeau vert avec le résultat du test ; les salles changent de couleur (une seule verte).
- [ ] Test mauvais : avertissement + « Revenir à … ». Échec de chargement : bandeau rouge, l'ancien chef est remis.
- [ ] « Tout démarrer » avec un autre chef : seul ce chef est chargé (pas de deuxième copie de gemma) ; « Mode jeu » libère la carte.
- [ ] Crew arrêté : la page lit `chef_crew.json`, interrupteurs désactivés avec la raison.
- [ ] `lms load --parallel` accepté par votre version de `lms` (sinon repli automatique).

## I. Images et pièces jointes (vrais moteurs et vraies clés requis)
- [ ] Page Images : chaque moteur disponible crée une image (OpenAI, Gemini, Grok avec leurs clés ; ComfyUI lancé) ; coût estimé affiché avant l'envoi ; confirmation au-dessus du seuil.
- [ ] Case « confidentiel » ou mode Confidentiel / Ultra-confidentiel : seul ComfyUI reste possible ; le nuage est refusé.
- [ ] Galerie : ouvrir, télécharger, réutiliser la description, supprimer ; les images sont dans le dossier `images` des données.
- [ ] Salle gemma (modèle vision) / Grok / Gemini (clé) : coller une capture d'écran, poser une question dessus ; DeepSeek refuse l'image avec une explication.
- [ ] Icône 📎 : un fichier `.txt` est rangé dans le tiroir puis joint ; un PDF est refusé avec une explication.

## J. Images depuis toutes les salles (vrai xAI, vrai ComfyUI, vrai Crew requis)
- [ ] Page Images et fenêtre 🎨 d'une salle : menu à deux groupes (Nuage / Local), prix, raisons des moteurs grisés ; xAI liste « grok-imagine-image* » sans vidéo ; Gemini grisé avec « palier gratuit ».
- [ ] Une image xAI coûte le prix RÉEL lu dans la réponse (page Coûts) ; l'image revient dans la conversation de la salle et reste à la réouverture.
- [ ] Demander « fais-moi une image de… » à une IA de chaque type de salle : une carte apparaît avec la description complète, RIEN n'est créé avant le clic sur Générer.
- [ ] Conversation privée / mode Confidentiel : seul ComfyUI est proposé.
- [ ] ComfyUI avec le chef chargé : confirmation, Crew libère la carte, l'image se crée, Crew recharge le chef (sauf Mode jeu ou « laisser la carte libre »).

## K. ComfyUI automatique (vrais scripts, vrai Crew, vrai LM Studio, vraie carte graphique requis)
- [ ] Les deux scripts sont dans `I:\IA\ComfyUI` (`demarrer_comfyui.ps1`, `arreter_comfyui.ps1`) ; ComfyUI est ARRÊTÉ au départ ; le chef de Crew est chargé.
- [ ] Page Images, moteur « ComfyUI (local) », créer une image : la fenêtre de confirmation affiche le texte « Crew libère la carte graphique, ComfyUI démarre (environ 20 à 40 s)… » ; rien ne part avant « Continuer ».
- [ ] Étapes affichées dans l'ordre : Libération de la carte → Démarrage de ComfyUI → Création de l'image → Arrêt de ComfyUI → Rechargement du chef ; puis « Chef rechargé : Crew est de nouveau disponible ». Dans le Gestionnaire des tâches : ComfyUI a disparu et le chef est de nouveau en mémoire vidéo.
- [ ] Trois demandes à la suite : UN seul cycle (une libération, un démarrage, trois images, un arrêt, une reprise).
- [ ] ComfyUI lancé à la main (`demarrer_comfyui.bat`) avant une création : le Centre ne le relance pas et ne l'arrête pas (sauf case « l'arrêter ensuite »).
- [ ] Page Centre : composant « ComfyUI » avec voyant ; Démarrer puis attendre 10 minutes sans rien faire : il s'arrête tout seul.
- [ ] « Tout démarrer » ne lance PAS ComfyUI ; « Mode jeu » l'arrête ; en Mode jeu une création locale est refusée avec une explication.
- [ ] Fermer le Centre pendant que la carte est libérée, puis le rouvrir : bandeau « La carte graphique est encore libérée. Recharger le chef ? » (aucune action automatique) ; lancer ComfyUI à la main : bandeau « ComfyUI tourne et occupe la carte graphique [Arrêter] ».
- [ ] Mettre un mauvais dossier dans `dossier_comfyui` (reglages.json) : refus clair, rien n'est lancé.

