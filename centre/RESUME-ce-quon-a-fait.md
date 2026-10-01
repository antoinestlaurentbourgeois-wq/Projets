# Le Centre de contrôle — ce qu'on a fait ensemble

*État au 1er octobre 2026 — branche `claude/new-session-bl6q4z`. Crew n'a jamais été modifié : seuls le Centre et le panneau l'ont été.*

## En une phrase
Le **Centre** est une application web (PC et téléphone) qui fusionne le panneau de contrôle tkinter, un cockpit, des **salles de discussion avec toutes les IA** et la **voix**, le tout avec des garde-fous de sécurité et de coûts.

## Les grandes pièces

| Pièce | Ce que ça fait |
|---|---|
| **Page Centre** | Voyants et boutons Démarrer / Arrêter (Docker, Open WebUI, Kokoro, LM Studio, chef local, embeddings, Crew, ComfyUI), « Tout démarrer », « Mode jeu », choix du mode de Crew (dont Ultra-confidentiel). |
| **Salles** | Une salle par IA (Claude, ChatGPT/Codex, Gemini, Grok, DeepSeek, Crew, gemma…) : historique, tiroir de fichiers, relais « Demander aussi à… », pièces jointes 📎, images collées, coûts par message. |
| **Table ronde** | Dans la salle Crew : plusieurs IA répondent au même message (un seul appel `crew-tableronde`), avec critique et synthèse ; estimation du coût avant l'envoi. |
| **Chef d'équipe** | Choisir le modèle LM Studio qui sert de chef local de Crew (interrupteurs façon iOS, un seul actif). Une salle par modèle, une seule « verte ». |
| **Autorisations Claude/Codex dans Crew** | Cocher ou non l'usage de l'abonnement par Crew, avec limite par jour (1 à 500), confirmation avant d'autoriser. |
| **Images** | Page 🎨 Images + bouton/commande `/image` dans toutes les salles + propositions de l'IA (bloc `[[IMAGE]]`, rien n'est créé sans ton clic). Moteurs : Grok (coût réel), Gemini, OpenAI, ComfyUI local. |
| **Voix** | Conversation en direct (LIVE) avec coûts en direct. **Le rond en haut à gauche** démarre et arrête le live depuis n'importe quelle page. |
| **Téléphone** | Accès par Tailscale, NIP reconfirmé pour les actions sensibles, PWA installable. |
| **Extras** | Rappels, bulletin du matin, départements, Truth Gate, gardien, sauvegarde, rapport d'usage. |

## Ce qu'on a ajouté dans les dernières séances

1. **ComfyUI automatique** — pour une image locale : Crew libère la carte graphique → ComfyUI démarre → l'image est créée → ComfyUI s'arrête → Crew recharge son chef. Un seul clic de confirmation ; plusieurs demandes = un seul cycle ; tout est remis en ordre même en cas d'échec ; arrêt automatique après 10 minutes d'inactivité ; bandeaux de réconciliation au redémarrage (« carte encore libérée », « ComfyUI tourne »). Jamais au démarrage de Windows, jamais par « Tout démarrer », jamais en Mode jeu (qui l'arrête).
2. **« Toujours approuver » (salle Claude)** — un bouton par outil et un mode automatique (désactivé par défaut), limités à une **liste blanche stricte d'outils en lecture seule** : Read, Glob, Grep, LS, NotebookRead, WebSearch, et les outils MCP `list_…` / `get_…` / `search_…`. Refus absolu si le nom contient send, reply, forward, create, update, delete, connect, attach, write, post, publish, pay, buy, remove, draft ou invite. **Jamais** Bash, WebFetch ni modification de fichiers. La liste mémorisée est re-filtrée à chaque lecture ; elle se retire depuis l'écran.

## Règles de sécurité qui tiennent partout
- Les clés restent sur le PC (variables d'environnement Windows), jamais dans le navigateur, les fichiers ni les journaux.
- Contenu confidentiel ou mode Confidentiel / Ultra-confidentiel : moteurs **locaux seulement** (refus fait par le serveur).
- Aucune action sensible sans session, en-tête anti-CSRF et, à distance, NIP reconfirmé.
- Le Centre ne charge ni ne décharge jamais LM Studio : il passe par les adresses de Crew.
- Aucun texte d'utilisateur, d'IA ou d'image dans une commande ; aucune description d'image ni contenu dans les reçus.
- Coût estimé avant l'envoi, plafonds jour/mois, confirmation au-dessus d'un seuil.

## Comment on travaille
- Tu (ou la session locale) m'envoies des prompts ; je livre sur la branche avec des tests et un fichier `RETOUR-*.md` qui liste ce que j'ai **supposé**.
- La session locale relit, installe, et fait les essais réels (vrai Crew, vrai LM Studio, vrai ComfyUI, vraies clés). Les listes à cocher sont dans `VERIFICATIONS.md`.
- Tests : Centre 624, panneau 125 — tous avec des faux (faux Crew, faux réseau, faux scripts). **Rien n'a encore été essayé en vrai sur le PC pour les nouveautés récentes.**

## Ce qui reste ouvert
- **Carte d'autorisation d'envoi de courriel** (AgentMail) : montrer l'appel exact (boîte, À/Cc/Cci, objet, texte, pièces jointes), sans bouton « Toujours ». Dépend de `PROMPT-agentmail-claude.md` (v2), que je n'ai pas reçu.
- **« Modifier cette image »** (phase 2 des images) : en attente d'un essai réel du format de `/v1/images/edits`.
- **Essais réels** des sections G à K de `VERIFICATIONS.md` (table ronde, chef d'équipe, images, ComfyUI automatique…).
- **Décision prise :** ne pas étendre « Toujours approuver » aux modifications de fichiers.

## Où trouver quoi
- `centre/README.md` — vue d'ensemble et installation.
- `centre/VERIFICATIONS.md` — listes à cocher pour les essais réels.
- `centre/RETOUR-*.md` — les suppositions faites pour chaque livraison (table ronde, menu des modèles, autorisations, ultra-confidentiel, chef d'équipe, images, ComfyUI automatique).
- `centre/centre/` — le code du Centre ; `panneau/` — le panneau tkinter et son simulateur.
