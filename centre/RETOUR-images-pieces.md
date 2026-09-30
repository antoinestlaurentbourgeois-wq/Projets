# Menu « 🎨 Images » et pièces jointes des salles (📎 + images collées)

## Menu « 🎨 Images » (nouvelle page)
- **Moteurs** : OpenAI (`gpt-image-1`, clé `OPENAI_API_KEY`), Gemini (`gemini-2.5-flash-image`, `GEMINI_API_KEY`), Grok/xAI (`grok-2-image`, `XAI_API_KEY`) et **local : ComfyUI** sur `127.0.0.1:8188`. Un moteur est grisé avec sa raison (clé absente, ComfyUI éteint, mode confidentiel, plafond atteint).
- **Formulaire** : moteur, description (4 000 caractères au plus), format (carré / portrait / paysage), nombre (1 à 4), modèle ComfyUI (liste lue dans ComfyUI), case « Contenu confidentiel : moteur local seulement ».
- **Coût avant l'envoi** (estimation indicative, marquée comme telle) ; au-dessus de `seuil_image_usd` (reglages.json, 0,10 $ par défaut) une confirmation est demandée ; plafonds jour/mois respectés ; dépense rangée sous « Images (nuage) » (estimée) dans la page Coûts.
- **Confidentialité** : case cochée ou mode Confidentiel / Ultra-confidentiel → nuage refusé par le SERVEUR (403), ComfyUI reste possible. Le texte de la demande n'est jamais écrit dans les journaux ni les reçus (seulement dans la galerie, sur le PC, à côté de l'image). Clés côté serveur seulement ; clé Gemini dans un en-tête (jamais dans l'adresse).
- **Création en arrière-plan** (une à la fois), progression « image k sur n », puis **galerie** (dossier `images/` des données) : ouvrir, télécharger, réutiliser la description, supprimer (confirmation, NIP à distance). Type réel vérifié sur les octets (PNG, JPEG, WebP), jamais d'après le serveur ; identifiants aléatoires ; galerie limitée à 500 images.
- **API** : `GET /api/images/options`, `POST /api/images/estimation`, `POST /api/images` (NIP à distance), `GET /api/images/jobs/<id>`, `GET /api/images`, `GET /api/images/<id>/fichier`, `DELETE /api/images/<id>`.

## Pièces jointes des salles
- **Icône 📎** à gauche du champ de saisie (et le bouton du tiroir devient « 🗄 Tiroir »). Elle ouvre le sélecteur de fichiers :
  - **fichier texte ou code** (txt, md, csv, json, py, js, html, xml, yaml, log…, 200 Ko et 20 000 caractères au plus) : rangé dans le **tiroir** (zone privé par défaut, choisie dans une petite fenêtre) puis joint au prochain message. En zone privée, un IA du nuage le refuse comme avant (le fichier reste alors dans le tiroir, non joint, avec un message clair) ;
  - **image** : jointe au message (voir ci-dessous) ;
  - autre format (PDF, Word…) : refusé avec une explication (non lus pour l'instant).
- **Coller une image** (capture d'écran, image copiée) dans le champ de saisie, ou la glisser-déposer : elle apparaît en vignette au-dessus du champ (✕ pour retirer), jusqu'à **4 par message**. Le navigateur la réduit à 1 600 px (plus léger, données cachées effacées) avant l'envoi. Les vignettes restent dans le message affiché.
- **Qui lit les images** : salles locales (LM Studio : seulement si le modèle sait lire les images), Grok, Gemini et ChatGPT **par clé API**. Refusées avec la raison : DeepSeek (texte seulement), Crew (non vérifié), Claude et les programmes officiels (Codex, Gemini CLI), et la table ronde. Le refus est fait par le serveur avant tout envoi.
- **Confidentialité** : conversation privée → jamais d'image vers le nuage (règle existante). Seule l'image du message en cours est envoyée ; les anciennes ne sont pas renvoyées (un repère « [image jointe : nom] » reste dans l'historique). Supprimer une conversation supprime ses images ; les images téléversées puis jamais envoyées sont effacées après un jour.
- **Stockage** : dossier `pieces/` des données du Centre ; nom de fichier = identifiant aléatoire (aucun chemin fourni par l'utilisateur) ; type réel vérifié (PNG, JPEG, WebP, GIF), 6 Mo au plus.

## Supposé (à vérifier sur votre PC)
- **ComfyUI** : adresse `127.0.0.1:8188` (non réglable), graphe standard (chargeur de modèle, deux textes, image vide, KSampler 25 pas, décodeur, enregistrement) ; tailles 768², 640×960, 960×640 (pensées pour un modèle SD 1.5/SDXL ordinaire, à ajuster si votre modèle veut autre chose) ; le modèle choisi est celui de la liste, sinon le premier.
- **OpenAI / xAI / Gemini** : adresses, noms de modèles et format de réponse (`data[0].b64_json` ; `inlineData` pour Gemini) d'après leur documentation actuelle, **non essayés avec de vraies clés**. Un appel par image.
- **Coûts par image** : 0,042 $ (OpenAI), 0,039 $ (Gemini), 0,07 $ (xAI) = marques de substitution, à vérifier ; l'écran dit « estimation indicative ».
- **Images vers Grok / Gemini / ChatGPT par clé** : envoyées au format OpenAI (`image_url` en data URL) ; Gemini passe par son adresse compatible OpenAI déjà utilisée ; non essayé en vrai. LM Studio : si le modèle n'est pas un modèle « vision », LM Studio répondra par une erreur affichée telle quelle.
- **Crew** : refuse les images faute de savoir s'il les transmet (à ouvrir si le vrai Crew le permet).

## Vérifié
Tests : Centre 473 (nouveaux : `test_pieces.py` 28, `test_images.py` 33), panneau 114. Écran en mode démo, téléphone et PC : collage d'une image (refus dans DeepSeek, vignette dans gemma), fichier texte via 📎 (fenêtre de zone, puce dans le tiroir), PDF refusé, envoi avec vignette dans la bulle, page Images (création de 2 images, galerie, case confidentiel → local, confirmation au-dessus du seuil, suppression), aucun débordement, aucune erreur console. **Pas essayé avec de vrais moteurs d'images.**
