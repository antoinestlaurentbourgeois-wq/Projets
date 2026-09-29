# Ce dont je ne suis pas sûr : phase 3 (voix)

**Rien de la voix n'a été testé contre un vrai service** : ni OpenAI, ni xAI. Ce qui a été testé : toute la logique du serveur avec un faux fournisseur (WebSocket
simulée), un vrai serveur `uvicorn`, un vrai client WebSocket, et l'interface dans Chromium avec un micro factice (démo). À vous de confirmer avec de vraies clés.

## Choix d'architecture (différent de GLAMMBOX, faute de pouvoir le lire)

1. **Un seul transport : WebSocket navigateur ↔ serveur ↔ fournisseur** (pas de WebRTC). Avantages : la clé ne quitte jamais le PC, le serveur voit tous les événements
   (coût en direct exact, coupure au plafond, outils exécutés côté serveur, aucune session vocale « orpheline »). Inconvénient : latence un peu supérieure à WebRTC.
   Le mode WebRTC de GLAMMBOX n'est pas repris.

## OpenAI Realtime (`centre/voix.py`)

2. **Adresse et authentification** supposées : `wss://api.openai.com/v1/realtime?model=<modèle>` avec `Authorization: Bearer <clé>` (interface « GA », sans en-tête bêta).
3. **Message `session.update`** (format GA supposé) : `session.type = "realtime"`, `output_modalities = ["audio"]`, `audio.input.format = {type: audio/pcm, rate: 24000}`,
   `audio.input.transcription = {model: gpt-4o-mini-transcribe, language: fr}`, `audio.input.turn_detection = {type: server_vad, create_response, interrupt_response}`,
   `audio.output = {format, voice}`, `tools`, `tool_choice`. Si le fournisseur refuse un champ, vous verrez « Service vocal : <message> » à l'écran : dites-moi le message exact.
4. **Noms d'événements** gérés : `response.output_audio.delta` **et** `response.audio.delta` ; `response.output_audio_transcript.delta/done` **et** `response.audio_transcript.delta/done` ;
   `conversation.item.input_audio_transcription.completed` ; `input_audio_buffer.speech_started/stopped` ; `response.function_call_arguments.done` ; `response.done` (avec `usage`) ; `error`.
5. **Noms de modèles** : `gpt-realtime-mini` et `gpt-realtime-2` (donnés dans votre demande). Voix proposées : `marin`, `cedar`, `alloy`, `echo`, `shimmer` (liste supposée).
6. **Calcul du coût** : à chaque `response.done`, jetons audio × tarif audio (10/20 $ par million pour mini, 32/64 pour realtime-2 : **vos chiffres**) + jetons texte × tarif texte
   (**placeholders** : 0,60/2,40 $ mini, 4/16 $ realtime-2) ; le cache d'invites est ignoré (surestimation, donc prudent). Si l'événement n'a pas de détail, tout est facturé au tarif audio.
   L'estimation « par minute » avant démarrage repose sur une hypothèse (10 jetons/s entrants, 20 jetons/s sortants) : le coût réel **augmente** au fil de la conversation (le contexte grossit).
7. **Coupure au plafond** : le serveur coupe quand `coût de la session ≥ reste avant plafond`, ou quand le plafond global est atteint (dépenses enregistrées chaque minute). Il ne peut pas empêcher
   les jetons déjà facturés d'une réponse en cours : le dépassement possible est de l'ordre d'une réponse.

## Grok Voice (xAI)

8. **Tout est supposé** : `wss://api.x.ai/v1/realtime?model=grok-voice-think-fast`, même protocole que OpenAI Realtime (JSON), voix `eve, ara, rex, sal, leo`. Je n'ai aucune documentation vérifiée de ce service.
   Facturation calculée **à la durée** (0,08 $/min, votre chiffre), pas aux jetons. S'il ne marche pas, l'erreur s'affichera : envoyez-la-moi ; il faudra peut-être adapter `_session_update` et les noms d'événements pour xAI.

## Talkie-walkie

9. **OpenAI** : transcription `POST https://api.openai.com/v1/audio/transcriptions` (multipart, modèle `gpt-4o-mini-transcribe`, `language=fr`) ; lecture `POST https://api.openai.com/v1/audio/speech`
   (modèle `gpt-4o-mini-tts`, format mp3, voix par défaut `alloy`). Tarifs de ces deux services : **placeholders** (0,003 $/min ; 12 $ par million de caractères).
10. **xAI** : transcription `POST https://api.x.ai/v1/stt` et synthèse `POST https://api.x.ai/v1/tts` : **adresses et formats de corps supposés**. Tarifs : 0,10 $/h et 15 $ par million de caractères (vos chiffres).
    Pour la synthèse xAI j'envoie `{"input", "text", "voice", "response_format": "mp3"}` (les deux clés de texte, faute de connaître la bonne).
11. **Formats audio du navigateur** : `MediaRecorder` en `audio/webm;codecs=opus` (Chrome/Edge/Firefox) ou `audio/mp4` (Safari). Acceptés côté serveur : webm, ogg, mp4, wav, mpeg, m4a.
12. **Durée d'enregistrement** : envoyée par le navigateur pour estimer le coût de transcription ; non vérifiée (simple estimation).

## Interface

13. **AudioWorklet** : `audioWorklet.addModule("/s/worklet-micro.js")` (protégé par la session). Contexte audio à 24 000 Hz (le navigateur rééchantillonne le micro) : supporté par Chrome/Edge/Safari récents ; Firefox : à vérifier.
14. **Écho** : `echoCancellation` activé ; sans casque, un retour de la voix dans le micro peut couper l'IA par erreur.
15. **Écran allumé** : `navigator.wakeLock` (non disponible partout). Si le téléphone verrouille l'écran, le navigateur peut couper le micro : la session se ferme alors avec un message.
16. **Politique de sécurité (CSP)** : j'y ai ajouté `media-src 'self' blob:` (lecture des réponses) après avoir vu le blocage en test réel.
17. **Sur le téléphone**, le micro exige HTTPS (phase 4, Tailscale Serve).
