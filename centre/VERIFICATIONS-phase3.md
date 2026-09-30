# Vérifications manuelles : phase 3 (la voix)

## Avant de commencer

| Besoin | Détail |
|---|---|
| Clé OpenAI | Variable **utilisateur** `OPENAI_API_KEY` (sert au LIVE `gpt-realtime-*`, à la transcription et à la voix de lecture OpenAI). |
| Clé xAI | `XAI_API_KEY` (Grok Voice, transcription et voix xAI). |
| Dépendance | `websockets` (déjà dans `requirements.txt` : relancez `scripts\installer.bat` pour l'installer dans le venv). |
| Micro | Autorisez le micro dans le navigateur. Sur PC, `http://127.0.0.1:8740` compte comme « sécurisé » : le micro fonctionne sans HTTPS. |
| Casque | Recommandé au début (sans casque, la voix de l'IA peut se réentendre dans le micro). |

**Mode démo :** `scripts\demo.bat` simule tout (voix, transcription, lecture) : essayez l'interface sans clé ni dépense.
Vous pouvez donc faire une première passe sans rien payer, puis une passe réelle.

## A. Sécurité et confidentialité (à faire en premier)

- [ ] Mode Crew **Confidentiel** ou **Ultra** : page **Voix** → bandeau rouge « désactivée », tous les boutons grisés. Le talkie-walkie aussi.
- [ ] En mode Confidentiel, dans la console du navigateur (F12), tenter `new WebSocket("ws://127.0.0.1:8740/ws/voix")` puis envoyer `{"t":"demarrer"}` : le serveur répond « désactivée » (contrôle serveur).
- [ ] Ouvrir une session vocale, puis passer Crew en Confidentiel dans la page Centre : la session se coupe toute seule en quelques secondes (« mode confidentiel »).
- [ ] Plafond : régler un plafond du jour très bas (ex. 0,05 $). Démarrer le LIVE : il se coupe **tout seul** quand le compteur atteint le plafond, avec un message.
- [ ] Une conversation contenant du contenu privé (page Salles, badge « privé ») ne peut pas être lue par la voix (le serveur refuse : « message privé »).
- [ ] Dans `I:\IA\CENTRE\donnees\` (journal, reçus, conversations) : aucune clé.

## B. LIVE (conversation en direct)

- [ ] Page **Voix** → LIVE : le coût estimé par minute s'affiche **avant** de démarrer, et de nouveau dans la boîte de confirmation.
- [ ] `gpt-realtime-mini` (par défaut) : « Bonjour » → l'assistant répond en français, à voix haute. Le **compteur de coût** grimpe en direct (coût, minutes, reste avant plafond).
- [ ] **Interruption** : parler pendant que l'IA parle → elle se tait immédiatement.
- [ ] Fin de phrase détectée toute seule (pas besoin de bouton).
- [ ] **« Terminer »** ferme tout ; le micro est libéré (le témoin du navigateur s'éteint).
- [ ] Comparer le coût affiché avec le tableau de bord OpenAI (ordre de grandeur, à quelques centimes près).
- [ ] Tester `gpt-realtime-2` et **Grok Voice** (facturé à la durée : ~0,08 $/min).
- [ ] Silence prolongé (3 min) : la session se ferme d'elle-même. Durée maximale (30 min) idem.
- [ ] Sur le téléphone : l'écran reste allumé pendant la session.

## C. Outils de l'agent vocal

- [ ] « Demande à DeepSeek ce qu'est un couple de serrage » : l'assistant annonce la consultation, puis **lit la réponse**. Une conversation « Vocal : … » apparaît dans la salle DeepSeek.
- [ ] Idem avec Claude, ChatGPT, Gemini, Grok, gemma, Crew. (Pour gemma et Crew, ils doivent être allumés.)
- [ ] « Demande à Claude de lancer une commande » : l'assistant dit que l'approbation est nécessaire ; la **carte d'approbation** apparaît dans la salle Claude.
- [ ] « Cherche dans ma mémoire … » : ne renvoie **jamais** de passage de la zone `prive` (à vérifier dès que Crew expose la mémoire).
- [ ] Si l'IA consultée échoue (clé absente…), l'assistant le dit simplement.

## D. Talkie-walkie

- [ ] Maintenir le bouton, parler, relâcher : la question transcrite s'affiche, la salle répond en écrit, la réponse est **lue**.
- [ ] Essayer plusieurs salles (Crew, gemma, DeepSeek, Claude…). Essayer les deux fournisseurs de voix (OpenAI, xAI).
- [ ] Décocher « Lire la réponse » : seule la transcription et la réponse écrite.
- [ ] Une réponse très longue n'est lue que dans sa première partie (message « lecture limitée »).
- [ ] Les coûts de transcription et de lecture apparaissent dans la page Coûts (IA « Voix (nuage) »).
- [ ] Sur téléphone (Safari/iPhone : format `audio/mp4`) : l'enregistrement fonctionne.

## E. Page Coûts

- [ ] Après quelques essais : les dépenses « Voix (nuage) » s'affichent (aujourd'hui / ce mois-ci).
- [ ] Le plafond bloque aussi le talkie-walkie (transcription/lecture) avec un message clair.

## G. Grok Voice (clé officielle, méthode GLAMMBOX)

- [ ] Avec `XAI_API_KEY` : page Voix → modèle « Grok Voice (xAI) », voix `leo` en premier. Démarrer : la session s'ouvre (le serveur a créé un jeton de session de 5 minutes).
- [ ] Demandez « cherche sur le web… » puis « regarde sur X… » : les recherches natives répondent.
- [ ] « Demande à Claude/DeepSeek… » : l'outil `consulter_salle` fonctionne aussi avec Grok.
- [ ] Talkie-walkie avec le fournisseur xAI : lecture de la réponse avec la voix `leo`.
- [ ] Si la connexion échoue : notez le message exact (adresse WebSocket ou en-tête à corriger, voir INCONNUS-phase3 n° 8).
