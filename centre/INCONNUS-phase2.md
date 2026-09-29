# Ce dont je ne suis pas sûr : phase 2

À vérifier sur le PC. Pour chaque point : ce que j'ai supposé, et où c'est dans le code.

## Programmes officiels (`centre/ia.py`)

1. **Claude Code, mode non interactif.** J'ai supposé : `claude -p --output-format stream-json --verbose --include-partial-messages
   --allowedTools "Read,Glob,Grep,LS" --permission-mode default --max-turns 12 [--model M] [--resume ID]`, invite envoyée par l'entrée standard, et un
   dernier message `{"type":"result", ..., "permission_denials":[{"tool_name","tool_use_id","tool_input"}], "total_cost_usd", "usage"}`.
   Les actions refusées d'avance ne s'exécutent pas ; j'affiche alors la carte d'approbation puis je **reprends la session** (`--resume`) avec
   `--allowedTools` complété du seul motif approuvé (ex. `Bash(git status)`). Si le nom d'un indicateur ou le format a changé, la salle Claude
   affichera « n'a pas répondu ». Faites `claude --help` et dites-moi ce qui diffère.
2. **Syntaxe des motifs d'autorisation** : `Bash(commande exacte)`, `WebFetch(domain:site)`, noms d'outils simples (`Write`, `Edit`). Incertain pour `WebFetch`.
3. **`ANTHROPIC_API_KEY` et abonnement.** En mode « abonnement », je retire `ANTHROPIC_API_KEY` de l'environnement du programme (une clé prendrait le pas sur l'abonnement).
4. **Codex.** J'ai supposé : `codex exec --json --skip-git-repo-check -C <atelier> -s read-only|workspace-write [-m M] -` (invite par l'entrée standard) et des
   événements JSON par ligne : `thread.started`, `item.completed` (`agent_message`), `turn.completed` (`usage`), `error`/`turn.failed`. **Pas de cartes d'approbation pour Codex** :
   lecture seule par défaut, et une case « Autoriser l'écriture (ce message) » à cocher (il n'existe pas de flux d'approbation en direct en mode `exec`, à ma connaissance).
   Codex ne diffuse pas mot à mot : la réponse arrive par blocs.
5. **Gemini CLI.** J'ai supposé : `gemini -p "<consigne>" [-m M]` avec l'invite sur l'entrée standard et la réponse en texte brut sur la sortie standard. Aucun mode « yolo ».
   Par défaut la salle Gemini utilise la clé API (plus fiable), pas le programme.
6. **Arguments et `.cmd` (Windows).** Les programmes npm sont des `.cmd` : Windows les lance via `cmd.exe`. Pour éviter toute injection, tout argument avec un caractère spécial (`& | < > ^ % ! "`)
   est refusé pour un `.cmd`/`.bat`. Les invites passent par l'entrée standard, jamais en argument.
7. **PATH du serveur.** Lancé par WMI, le serveur n'a pas forcément votre PATH d'utilisateur : je cherche aussi dans `%USERPROFILE%\.local\bin`, `%APPDATA%\npm`, `%LOCALAPPDATA%\Programs\claude`.
   Sinon : `reglages.json` (voir VERIFICATIONS-phase2.md).
8. **Connexion à l'abonnement depuis un processus lancé par WMI.** Les programmes lisent leurs jetons dans votre profil (`%USERPROFILE%\.claude`, `.codex`, `.gemini`) : cela devrait fonctionner
   puisque le serveur tourne sous votre compte, mais je n'ai pas pu le tester.

## API du nuage (`centre/salles.py`)

9. **Noms de modèles par défaut** (inventés faute de liste vérifiable) : DeepSeek `deepseek-chat`, Gemini `gemini-flash-latest`, Grok `grok-4`, OpenAI `gpt-4.1-mini`.
   Le bouton « Réglages » interroge le fournisseur (`GET /models`) et affiche les vrais noms : **choisissez-les là**. Les modèles DeepSeek « Flash » et « V4 Pro » de Crew ne sont pas ceux-ci.
10. **Adresses** : DeepSeek `https://api.deepseek.com/chat/completions`, OpenAI `https://api.openai.com/v1/chat/completions`, xAI `https://api.x.ai/v1/chat/completions`,
    Gemini (compatibilité OpenAI) `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`. Toutes supposées compatibles OpenAI avec `stream_options.include_usage`.
11. **Grok « par abonnement ».** Le cockpit GLAMMBOX n'a pas pu être lu ; conformément au retour local, Grok passe par `XAI_API_KEY` (API officielle).
12. **Tarifs au jeton** : les valeurs par défaut sont des **placeholders** non vérifiés (`PRIX_DEFAUT`). L'interface les marque « indicatif, non vérifié » jusqu'à ce que vous les régliez dans Coûts.
13. **Coût de Crew.** Crew n'expose pas ses dépenses ; j'estime d'après le nombre de caractères (ou l'usage si le serveur le renvoie) au prix indicatif « crew », sauf en modes locaux (gratuit).
    Le journal de `/travaux` (« Aiguillage … → DeepSeek Flash ») pourrait affiner ça : à ajouter côté Crew si vous voulez un champ de coût.
14. **Crew et contenu privé.** Pour un contenu privé je demande le modèle `crew-confidentiel` à `/v1/chat/completions` (jamais `crew-normal`). Je suppose que ce nom de modèle force bien le traitement 100 % local.
15. **Abonnements et plafonds.** Une salle « abonnement » compte 0 $ de dépense, mais est quand même **bloquée** quand un plafond est atteint (prudence).

## Mémoire (`centre/memoire.py`)

16. `/memoire/etat` et `/memoire/chercher` de Crew ne sont pas encore exposés : la salle affiche « pas encore exposée » (404) ; le simulateur du panneau les simule. Format supposé conforme à votre description.

## Interface

17. Flux SSE : lu avec `fetch` + `ReadableStream`. Testé avec Chromium (démo). Sur un vieux navigateur mobile, un problème de flux se verrait par un message « Connexion interrompue » ; la réponse reste alors sauvegardée sur le PC.
18. Le rendu Markdown est volontairement minimal (gras, code, blocs de code) : pas de tableaux ni de liens cliquables (sécurité).

19. **Lectures interdites à Claude.** Je passe `--disallowedTools "Read(**/.env),Read(**/.env.*),Read(**/.claude/.credentials.json),Read(**/.codex/auth.json),Read(**/.gemini/**),Read(**/verrou.json),Read(**/secrets/**),Read(**/*.pem),Read(**/id_rsa*),Read(**/id_ed25519*),Read(**/.ssh/**)"`.
    Syntaxe des motifs (`**` façon gitignore) **supposée** : à vérifier avec la documentation de Claude Code, et en demandant à Claude de lire un `.env` de test (il doit être refusé). Les règles `Read(...)` couvrent en principe aussi Grep/Glob, mais pas forcément une commande `Bash` approuvée : c'est une raison de plus de lire les cartes d'approbation.
