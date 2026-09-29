# Rapport de la nuit : Centre de contrôle, phases 2 à 5

Branche `claude/new-session-bl6q4z`, dossier `centre/` (plus deux petits ajouts dans `panneau/`). **308 tests du Centre + 105 du panneau passent**, tous avec simulateurs.
Rien de ce qui touche un service réel (OpenAI, xAI, Claude Code, Codex, Gemini CLI, Tailscale, Planificateur de tâches) n'a pu être testé ici : c'est le travail de la session locale.

## Ce qui a été fait

| Phase | Commit | Contenu |
|---|---|---|
| Corrections du retour | `09c9ec8` | `127.0.0.1` partout (panneau compris), tests indépendants de l'emplacement du panneau, démo sur I:, versions fixées |
| 2 : Salles | `9e81279` | 7 salles (Crew, Claude, ChatGPT/Codex, Gemini, Grok, DeepSeek, gemma), réponses en continu (reprenables), historique, tiroir, mémoire (simulée), « Demander aussi à… », coûts estimés avant envoi, approbations par bouton |
| 3 : Voix | `2e3a183` | LIVE (WebSocket navigateur ↔ serveur ↔ OpenAI Realtime / Grok Voice), outils vocaux côté serveur, talkie-walkie, coût en direct, coupure au plafond |
| 4 : Téléphone | `806b13b` | Tailscale Serve, identité Tailscale exigée, NIP reconfirmé, appareils connectés, interface tactile, revue de sécurité |
| 5 : Extras | `d2b091f` | Rappels, bulletin, départements, Truth Gate, gardien, sauvegarde de nuit, rapport d'usage |

## À préparer sur le PC (récapitulatif)

**Clés** (variables d'environnement *utilisateur*) : déjà présentes `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `OPENWEBUI_API_KEY`. À ajouter : **`OPENAI_API_KEY`** (voix LIVE OpenAI, transcription, lecture ; salle ChatGPT en mode clé) et **`XAI_API_KEY`** (Grok, Grok Voice).
`ANTHROPIC_API_KEY` : **seulement** si vous voulez payer Claude à l'usage (sinon **ne la mettez pas** : elle passerait avant l'abonnement).
**Connexions (abonnements)** : `claude` (Claude Code, « Se connecter »), `codex login` (« Se connecter avec ChatGPT »), `gemini` (compte Google) : une fois dans un terminal. Grok : clé xAI.
**Installer** : `installer.bat` (installe aussi `websockets`), `definir_verrou.bat`, `creer_raccourci.bat`, `installer_taches.bat`. Téléphone : `TELEPHONE.md`.
**Tarifs** : régler les vrais tarifs au jeton dans **Coûts** (les valeurs affichées « indicatives » sont des placeholders).

## Par où commencer (ordre conseillé pour la session locale)

1. `pytest` (Centre) puis `installer.bat` : vérifier que `websockets` s'installe (version testée ici : 17.1) et que le démarrage par WMI marche encore.
2. Salles **sans clé** : gemma et Crew (le plus simple) ; puis DeepSeek. Vérifier la **confidentialité** (`VERIFICATIONS-phase2.md` § B) avant tout le reste.
3. **Claude Code** : format de sortie et carte d'approbation (`INCONNUS-phase2.md` n° 1-3). Puis Codex, Gemini CLI.
4. **Voix** : d'abord OpenAI (`gpt-realtime-mini`) ; les noms d'événements et le `session.update` sont les points les plus fragiles (`INCONNUS-phase3.md` n° 2-4). Grok Voice est entièrement supposé.
5. **Tailscale** : `tailscale_configurer.bat` puis `tester_telephone.bat` ; surtout l'en-tête `Tailscale-User-Login` (`INCONNUS-phase4.md` n° 2). *Si cet en-tête n'existe pas, l'accès distant est refusé (403) : c'est sans danger mais bloquant.*
6. Tâches planifiées, gardien, sauvegarde (`VERIFICATIONS-phase5.md` § A-B).

## Ce que j'ai décidé sans vous demander (à confirmer ou corriger)

- **Un seul transport pour la voix** (WebSocket via le serveur), pas de WebRTC : plus simple, clés jamais exposées, coût exact ; latence un peu supérieure.
- **Confidentialité prudente** : mode inconnu = comme Confidentiel ; un contenu privé rend toute la conversation « locale seulement » ; Crew reçoit le modèle `crew-confidentiel` pour le privé ; la zone par défaut du tiroir et des rappels est **privée**.
- **Approbations** : Claude en lecture seule + carte d'approbation (reprise de session avec l'outil approuvé seulement) ; Codex : lecture seule + case « autoriser l'écriture (ce message) » ; commandes complexes non approuvables depuis l'écran.
- **Abonnements = 0 $ de dépense**, mais bloqués quand même au plafond.
- **Accès distant** : identité Tailscale exigée, NIP reconfirmé (5 min) pour toute action sensible.
- **Sauvegarde** : sans `verrou.json` : après une restauration complète, il faut redéfinir le NIP et le mot secret.
- **Limites de sécurité** fixées par moi : 30 min de voix max, 3 min de silence, 30 appels d'outils par session, lecture vocale limitée à 3000 caractères.

## Ce dont j'ai besoin de vous / de la session locale

- Le **paquet GLAMMBOX** n'a pas été téléchargé (refus de permission dans cette session). La session locale l'a audité et dit qu'on peut le reprendre : si vous voulez le client vocal, les sessions temps réel, le tiroir ou le Truth Gate **d'origine**, autorisez le téléchargement à cette session, ou fournissez le fichier. Sinon tout reste écrit de zéro (c'est le cas actuellement).
- Les **coûts de Crew** : ajouter un champ de coût estimé dans les réponses de `/travaux` et de `/v1/chat/completions` (`usage`) permettrait de compter Crew exactement (aujourd'hui : estimation d'après la longueur).
- Les adresses `/memoire/etat` et `/memoire/chercher` de Crew, quand elles seront exposées : la salle et les outils vocaux les utilisent déjà (simulées pour l'instant).

## Index des documents

`README.md` (installation), `TELEPHONE.md`, `SECURITE-TELEPHONE.md`, `VERIFICATIONS.md` + `-phase2` … `-phase5` (listes à cocher), `INCONNUS.md` + `-phase2` … `-phase5` (incertitudes détaillées).
