# Vérifications manuelles : phase 2 (salles de discussion)

## Avant de commencer : ce qu'il faut préparer

| Salle | Ce qu'il faut |
|---|---|
| Crew | Serveur Crew allumé (page Centre). |
| gemma | gemma chargé dans LM Studio (page Centre). |
| DeepSeek | Clé `DEEPSEEK_API_KEY` (déjà là). |
| Gemini | Clé `GEMINI_API_KEY` (déjà là) : c'est le mode par défaut. Facultatif : programme `gemini` (voir ci-dessous). |
| Grok | Clé `XAI_API_KEY` (à ajouter dans les variables d'environnement **utilisateur**). |
| Claude | Programme officiel **Claude Code** installé, puis dans un terminal : `claude` → « Se connecter » avec votre abonnement. *Ne mettez PAS `ANTHROPIC_API_KEY` sauf si vous voulez payer à l'usage (réglages de la salle → connexion « clé API »).* |
| ChatGPT / Codex | Programme officiel **Codex CLI** : `codex login` → « Se connecter avec ChatGPT ». Facultatif : `OPENAI_API_KEY` + connexion « clé API » dans les réglages de la salle. |
| Atelier | Le dossier `I:\IA\ATELIER` est créé tout seul. Claude, Codex et Gemini n'y ont accès qu'en lecture (écriture seulement après votre bouton). |

Si un programme (`claude`, `codex`, `gemini`) n'est pas trouvé alors qu'il est installé, créez `I:\IA\CENTRE\donnees\reglages.json` avec le Bloc-notes :

```json
{ "chemins_programmes": { "claude": "C:\\Users\\boliv\\.local\\bin\\claude.exe",
                          "codex": "C:\\Users\\boliv\\AppData\\Roaming\\npm\\codex.cmd",
                          "gemini": "C:\\Users\\boliv\\AppData\\Roaming\\npm\\gemini.cmd" } }
```
(puis redémarrez le Centre : `arreter_centre.bat`, raccourci du bureau). Ce fichier n'est modifiable que par vous, sur le PC.

## A. Généralités

- [ ] Page **Salles** : 7 pastilles (Crew, Claude, ChatGPT/Codex, Gemini, Grok, DeepSeek, gemma). Une pastille grisée explique pourquoi au survol (et en bandeau une fois choisie).
- [ ] Nouvelle conversation dans **gemma** : la réponse arrive **en continu**, mise en forme correcte (gras, code, bouton « Copier le code »).
- [ ] Idem dans Crew, DeepSeek, Gemini. Le coût estimé s'affiche sous la zone de saisie **avant** l'envoi, et sur chaque réponse.
- [ ] **Arrêter** interrompt une réponse longue ; le début de la réponse reste dans l'historique (« interrompu »).
- [ ] Fermer l'onglet **pendant** une réponse, le rouvrir : la conversation montre « en cours… » puis la réponse complète (elle continue sur le PC).
- [ ] Sur le téléphone (phase 4) : mettre l'écran en veille pendant une réponse, revenir : même comportement.
- [ ] Renommer et supprimer une conversation (confirmation avant suppression). Les conversations sont des fichiers dans `I:\IA\CENTRE\donnees\conversations\`.

## B. Confidentialité (le plus important)

- [ ] Mode Crew **Confidentiel** ou **Ultra-confidentiel** (page Centre) : toutes les salles du nuage sont grisées avec « rien ne doit quitter le PC » ; gemma et Crew restent utilisables.
- [ ] Dans ce mode, ouvrir une ancienne conversation DeepSeek et essayer d'envoyer : refusé avec le même message (contrôle du **serveur**, pas seulement de l'écran).
- [ ] Ajouter au tiroir un texte **privé** (défaut). Le joindre à un message DeepSeek : refusé. Le joindre à gemma : accepté, et la conversation affiche « contenu privé : IA locales seulement ».
- [ ] Dans cette conversation privée, « Demander aussi à… » : les IA du nuage sont refusées ; Crew accepté (le serveur demande alors le modèle `crew-confidentiel`).
- [ ] « Utiliser la mémoire » avec DeepSeek : seuls des passages de la zone *partageable* sont envoyés (à vérifier quand la mémoire sera exposée par Crew ; en attendant, elle est simulée en démo).
- [ ] Passer un élément du tiroir de « privé » à « partageable » demande une confirmation et apparaît dans les reçus.

## C. Approbations (Claude)

- [ ] Demandez à Claude de lire un fichier de `I:\IA\ATELIER` : ça marche sans demande.
- [ ] Demandez-lui d'exécuter une commande (ex. « lance git status ») ou de créer un fichier : une **carte d'approbation** apparaît, avec des boutons Approuver / Refuser. Rien ne s'exécute avant votre clic.
- [ ] « Approuver » puis « Valider mes choix » : Claude poursuit et l'action est faite. « Refuser » : rien n'est fait.
- [ ] Une commande complexe (avec `&`, `|`, `>`…) ne peut pas être approuvée depuis l'écran (message explicatif).
- [ ] Cette carte fonctionne aussi depuis le téléphone (phase 4).
- [ ] Vérifier dans un terminal (`tasklist`) qu'aucun `claude` ne reste actif après « Arrêter ».

## D. Codex et Gemini

- [ ] ChatGPT/Codex (abonnement) : lecture seule par défaut. Cocher « Autoriser l'écriture dans l'atelier (ce message) » demande une confirmation et n'est valable que pour ce message.
- [ ] Gemini : essayer les deux connexions (clé API, puis programme `gemini`) dans « Réglages ».

## E. Relais, tiroir, coûts

- [ ] « Demander aussi à… » sur une réponse : une nouvelle conversation s'ouvre dans l'autre salle avec le texte prêt (modifiable).
- [ ] Page **Tiroir** : ajouter, voir, changer de zone, supprimer.
- [ ] Page **Coûts** : régler les vrais tarifs au jeton de chaque fournisseur (les valeurs « indicatives » sont des placeholders). Après quelques messages DeepSeek, les dépenses estimées apparaissent.
- [ ] Mettre un plafond par jour très bas : les salles du nuage se bloquent avec un message clair ; gemma continue.
- [ ] Le solde DeepSeek (page Coûts) baisse cohérent avec les estimations (ordre de grandeur).
