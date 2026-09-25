# Panneau de contrôle de l'IA locale

Une petite fenêtre Windows pour **voir** et **allumer/éteindre** votre installation d'IA locale :
Docker Desktop, Open WebUI, Kokoro, le serveur LM Studio, les modèles gemma et d'embeddings, et le serveur Crew.

| Voyant | Signification |
|---|---|
| 🟢 vert | actif |
| 🔴 rouge | arrêté (la ligne en dessous explique pourquoi) |
| 🟠 orange | en train de démarrer ou de s'arrêter |
| ⚪ gris | état inconnu (par exemple : impossible d'interroger LM Studio) |

- **Un interrupteur par composant.** Si le composant a besoin d'un autre composant éteint, le panneau
  vous propose de l'allumer d'abord. Si vous éteignez un composant dont d'autres dépendent, il vous propose
  de les éteindre aussi.
- **Mode jeu** : éteint tout, dans le bon ordre (Crew → modèles → serveur LM Studio → Open WebUI et Kokoro →
  Docker Desktop), pour libérer la carte graphique et la mémoire.
- **Tout démarrer** : rallume tout, dans l'ordre inverse.
- **Clés API** : affiche seulement « présente » ou « absente ». La valeur n'est jamais affichée ni écrite.
- Les voyants se mettent à jour tout seuls toutes les 5 secondes. La fenêtre ne gèle jamais : tout le travail
  se fait en arrière-plan.
- Le panneau ne contacte que votre PC (`localhost` / `127.0.0.1`). Rien ne sort sur Internet.
- Chaque action et chaque erreur est notée dans `panneau.log` (bouton **Journal**).

**Nouveautés de la version 2**

- **Mode de Crew** : sur la ligne « Serveur Crew », une liste déroulante affiche le mode en cours
  (Économe, MaxPerf, Confidentiel, Ultra-confidentiel…) et permet d'en changer. Le petit **i** à côté
  de chaque mode affiche son explication (au survol ou au clic).
- **État des IA** : sous la ligne de Crew, cliquez sur **▸ État des IA utilisées par Crew** pour déplier
  la liste de toutes les IA que Crew peut utiliser : voyant, nom, niveau (1 simple, 2 bon, 3 expert),
  coût relatif et une ligne d'état.
- **Noms cliquables** : **Open WebUI**, **Serveur LM Studio** et **Docker Desktop** s'ouvrent d'un clic
  sur leur nom (curseur en forme de main, nom souligné au survol). Si le composant est éteint, le panneau
  propose de l'allumer d'abord.

---

## Installation (5 minutes)

Rien n'est installé : le panneau utilise uniquement Python 3.12 et tkinter, déjà présents dans
`I:\Python\Python312`. Aucun environnement virtuel n'est nécessaire (aucune bibliothèque supplémentaire),
et rien n'est écrit sur le disque C: à part le raccourci du bureau.

1. **Récupérer les fichiers.** Sur la page GitHub du projet, choisissez la branche
   `claude/new-session-nsb4ea`, puis **Code → Download ZIP**. Enregistrez le ZIP sur le disque **I:**.
2. **Copier le dossier.** Ouvrez le ZIP et copiez le dossier `panneau` pour obtenir exactement :
   `I:\Python\crewai-routage\panneau\` (avec `panneau.pyw`, `reglages.py`, etc. directement dedans).
3. **Essayer sans risque (facultatif).** Double-cliquez sur `demo.bat` : le panneau s'ouvre en **mode démo**,
   tout est simulé, rien n'est lancé sur votre PC. Jouez avec les boutons, puis fermez la fenêtre.
4. **Créer le raccourci.** Double-cliquez sur `creer_raccourci.bat`. Une fenêtre noire s'ouvre, affiche
   « Raccourci créé », appuyez sur une touche. Un raccourci **Panneau IA locale** apparaît sur le bureau.
   *(Si Windows affiche « Windows a protégé votre ordinateur », cliquez sur « Informations complémentaires »
   puis « Exécuter quand même » : c'est le fichier que vous venez de copier.)*
5. **Lancer.** Double-cliquez sur le raccourci du bureau. Aucune fenêtre noire ne doit apparaître.

Ensuite, suivez la liste [VERIFICATIONS.md](VERIFICATIONS.md) pour tout tester une première fois.

### Mettre à jour depuis la version 1

Votre panneau v1 fonctionne : on remplace seulement certains fichiers. **Ne supprimez pas le dossier**
(votre `tests\verif_reelle.py` et votre journal y sont).

1. Fermez le panneau (croix en haut à droite).
2. Téléchargez le ZIP de la branche `claude/new-session-nsb4ea` comme la première fois (**Code → Download
   ZIP**), sur le disque **I:**.
3. Copiez depuis le dossier `panneau` du ZIP vers `I:\Python\crewai-routage\panneau\`, en acceptant de
   **remplacer** les fichiers existants :
   - nouveaux : `panneau_crew.py`, `panneau_ouvrir.py`, `panneau_widgets.py`, `tests\test_v2.py` ;
   - modifiés : `panneau.pyw`, `panneau_logique.py`, `simulateur.py`, `reglages.py`,
     `tests\test_panneau.py`, `README.md`, `VERIFICATIONS.md`, `.gitignore`.
   - `creer_raccourci.ps1` n'a pas changé : il est déjà enregistré en UTF-8 **avec BOM** (un test vérifie
     maintenant qu'il le reste). Inutile de recréer le raccourci.
4. **Si vous aviez modifié `reglages.py`** (un chemin, un délai…), refaites la même modification dans le
   nouveau fichier. La v2 ajoute seulement un bloc à la fin (« Version 2 »).
5. Double-cliquez sur `lancer_tests.bat` : la dernière ligne doit afficher `OK` (105 tests).
6. Rouvrez le panneau par le raccourci, puis suivez la partie **G** de [VERIFICATIONS.md](VERIFICATIONS.md).

### Si un chemin est différent sur votre PC

Tous les chemins et noms sont dans **`reglages.py`** (clic droit → Ouvrir avec → Bloc-notes).
Par exemple, si Docker Desktop n'est pas dans `C:\Program Files\Docker\Docker\`, corrigez la liste
`DOCKER_DESKTOP_CANDIDATS`. Enregistrez, fermez le panneau et rouvrez-le.

### Désinstaller

Supprimez le raccourci du bureau et le dossier `I:\Python\crewai-routage\panneau\`. C'est tout.

---

## Les fichiers

| Fichier | Rôle |
|---|---|
| `panneau.pyw` | La fenêtre (lancée sans console grâce à `pythonw.exe`) |
| `panneau_logique.py` | Toute la logique : dépendances, vérifications, démarrage, arrêt |
| `panneau_crew.py` | *(v2)* Mode de Crew et liste des IA (`/mode`, `/moteurs`, fichier `mode_crew.json`) |
| `panneau_ouvrir.py` | *(v2)* Ouvrir Open WebUI, LM Studio et Docker Desktop |
| `panneau_widgets.py` | *(v2)* Éléments de la fenêtre : bulle « i », liste des modes, section des IA |
| `reglages.py` | Les chemins, noms et délais — **le seul fichier à modifier** |
| `simulateur.py` | Une fausse installation, pour les tests et le mode démo |
| `tests/test_panneau.py` | Les tests automatiques de la v1 (59 tests, tout est simulé) |
| `tests/test_v2.py` | *(v2)* Les tests des nouveautés (46 tests, tout est simulé) |
| `tests/verif_reelle.py` | Votre script de vérification **réelle** (Mode jeu + Tout démarrer, avec `nvidia-smi`). Il reste sur votre PC ; il n'est pas lancé par les tests automatiques |
| `creer_raccourci.bat` / `.ps1` | Crée le raccourci sur le bureau |
| `demo.bat` | Ouvre le panneau en mode démo |
| `lancer_tests.bat` | Lance les tests automatiques |
| `panneau.log` | Le journal (créé au premier lancement, 500 Ko max) |
| `modes_crew_cache.json` | *(v2, créé tout seul)* Copie des noms et explications des modes reçus du serveur Crew, pour les afficher même quand il est éteint |

## Lancer les tests automatiques

Double-cliquez sur `lancer_tests.bat`. La dernière ligne doit être **`OK`** (105 tests).
Ces tests simulent toutes les commandes (Docker, `lms`, PowerShell…) : ils ne touchent à rien sur le PC.
Ils vérifient notamment l'ordre des dépendances, la lecture des réponses de LM Studio (`/api/v0/models`
et `lms ps`), le fait de ne jamais charger une 2ᵉ copie d'un modèle, le repli si `docker desktop stop`
n'existe pas, et l'absence des valeurs de clés dans le journal.

---

## Comment ça marche (pour les curieux)

| Composant | Voyant vert si… | Allumer | Éteindre |
|---|---|---|---|
| Docker Desktop | `docker info` réussit | ouvre `Docker Desktop.exe`, attend jusqu'à 2 min 30 | `docker desktop stop` ; sinon fermeture forcée de Docker Desktop |
| Open WebUI | `http://localhost:3000/api/version` répond 200 | `docker start open-webui`, attend que le site réponde (2 min max) | `docker stop open-webui` |
| Kokoro | `docker inspect` dit « true » | `docker start kokoro` | `docker stop kokoro` |
| Serveur LM Studio | `http://localhost:1234/v1/models` répond | `lms server start` | `lms server stop` |
| gemma / embeddings | l'API LM Studio indique `state: loaded` | `lms load …` **seulement s'il n'est pas déjà chargé** | `lms unload …` (toutes les copies) |
| Serveur Crew | `http://127.0.0.1:8765/sante` renvoie `{"ok": true}` | lancé par **WMI** (survit à la fermeture du panneau) | arrêt des processus `pythonw.exe … serveur_crew.py` |

Détails utiles :

- **Orange sur Open WebUI** : le conteneur tourne mais le site ne répond pas encore. C'est normal pendant
  30 s à 1 min après le démarrage.
- **Orange sur Crew** : les processus existent mais `/sante` ne répond pas (démarrage, ou serveur bloqué).
- **Gris sur les modèles** quand le serveur LM Studio est arrêté : le panneau ne peut plus demander à
  LM Studio ce qui est chargé. Il n'utilise pas `lms` pour les voyants automatiques, car `lms` peut
  rouvrir LM Studio en arrière-plan, ce qui gênerait vos jeux.
- **« 2 copies chargées »** : si un modèle est chargé deux fois (par exemple depuis LM Studio lui-même),
  le panneau le signale. Éteignez puis rallumez ce modèle : toutes les copies sont déchargées, puis une seule
  est rechargée.
- **Une seule action à la fois.** Pendant une action, les autres boutons sont grisés (un clic fait « bip »).
- **Un seul panneau à la fois** : si vous double-cliquez deux fois sur le raccourci, le 2ᵉ vous prévient
  que le panneau est déjà ouvert.
- Fermer le panneau **n'éteint rien** : ce qui tourne continue de tourner.

---

## Version 2 : comment ça marche

### Le mode de Crew

- **Serveur Crew allumé** : le panneau lit le mode par `GET /mode` et le change par `PUT /mode`, avec la
  clé `CREW_API_KEY` lue dans `I:\Python\crewai-routage\.env`. La clé est relue à chaque fois ; elle
  n'est jamais affichée ni écrite dans le journal.
- **Serveur Crew éteint** : le panneau affiche « Serveur Crew éteint (mode lu dans le fichier) ». Vous pouvez
  quand même changer de mode : il est écrit dans `mode_crew.json` (les autres réglages éventuels du fichier
  sont gardés), et le serveur le relira à la prochaine demande.
- **Les noms et explications des modes viennent du serveur**, jamais du panneau. Pour pouvoir les afficher
  quand le serveur est éteint, le panneau en garde une copie (`modes_crew_cache.json`). Conséquence : tant
  que le serveur Crew n'a jamais été allumé avec la v2, la liste des modes est inconnue et le mode s'affiche
  sous sa forme brute (ex. « econome »).
- Le mode est relu toutes les 5 secondes, avec les voyants (une petite requête locale).

### L'état des IA

- La liste vient de `GET /moteurs`. Une IA ajoutée à Crew (un futur GPT-6…) apparaît **sans modifier le
  panneau**.
- Voyants : `pret` = vert, `arrete` = rouge, `indisponible` = gris ; une valeur inconnue = gris.
- Pour économiser, la liste n'est demandée **que quand la section est dépliée** (toutes les 5 s, et tout
  de suite à l'ouverture). Serveur éteint : « Serveur Crew éteint », sans aucune requête.

### Les noms cliquables

| Nom | Ce qui s'ouvre |
|---|---|
| **Open WebUI** | La conversation **la plus récente qui utilise un modèle `crew-…`** (`http://localhost:3000/c/<id>`). Le panneau lit la liste des conversations avec votre clé `OPENWEBUI_API_KEY` et regarde au plus les 20 plus récentes, pendant 10 secondes au maximum. S'il n'en trouve pas (ou si la clé manque), il ouvre une **nouvelle conversation avec Crew** : `http://localhost:3000/?model=crew-normal`. |
| **Serveur LM Studio** | L'application **LM Studio**, avec un message qui indique quel modèle choisir : le plus gros modèle de conversation chargé (types `llm`/`vlm`, taille lue par `lms ps --json`). Son nom est **copié dans le presse-papiers**. Aucun modèle n'est chargé ni déchargé. |
| **Docker Desktop** | L'application Docker Desktop. |

## ⚠️ Ce que je n'ai pas pu vérifier

Je n'ai pas accès à votre PC. Tout a été testé **en simulation** (105 tests automatiques), et l'interface a
été testée sous Linux en mode démo, y compris à l'échelle 150 %. Voici ce qui reste incertain, et ce que fait
le panneau dans chaque cas :

1. **Chemin de Docker Desktop.** Le panneau essaie `C:\Program Files\Docker\Docker\Docker Desktop.exe`,
   puis deux autres emplacements. S'il ne le trouve pas, la ligne affiche « Docker Desktop.exe introuvable »
   → corrigez `DOCKER_DESKTOP_CANDIDATS` dans `reglages.py`.
2. **`docker desktop stop`.** Cette commande n'existe que dans les versions récentes de Docker Desktop
   (environ 4.37 et plus, fin 2024). Si elle n'existe pas ou échoue, le panneau **ferme de force** Docker
   Desktop (`taskkill`) et l'indique : « Arrêté par fermeture forcée ». Dans ce cas, la machine virtuelle
   WSL de Docker (`VmmemWSL` dans le Gestionnaire des tâches) peut rester en mémoire. Pour la libérer, tapez
   `wsl --shutdown` dans PowerShell (attention : cela arrête aussi vos autres distributions WSL). Je ne l'ai
   pas automatisé pour cette raison. Si vous voyez ce message, dites-le-moi.
3. **La commande `docker`** doit être accessible (normalement ajoutée au PATH par Docker Desktop). Sinon, le
   panneau essaie `C:\Program Files\Docker\Docker\resources\bin\docker.exe`.
4. **Format de l'API LM Studio** (`/api/v0/models`) : je me suis basé sur le format documenté
   (`{"data": [{"id": …, "state": "loaded"}]}`). Selon les versions, l'identifiant peut contenir ou non
   `google/`, et une copie supplémentaire s'appelle `…:2` ; le panneau accepte ces variantes. Si l'API
   n'existe pas (réponse 404), le panneau utilise `lms ps` à la place.
5. **Format de `lms ps`** : il a changé selon les versions (liste « Identifier: … », tableau, ou JSON avec
   `--json`). Le panneau gère ces trois formats, mais je n'ai pas vu la sortie de **votre** version.
6. **`lms server start` quand LM Studio est fermé** : les versions récentes relancent LM Studio en
   arrière-plan automatiquement. Si ce n'est pas le cas chez vous, ouvrez LM Studio avant.
7. **`lms server stop` ne décharge pas les modèles.** C'est pour cela que le Mode jeu décharge les modèles
   *avant* d'arrêter le serveur. En revanche, l'application LM Studio elle-même reste ouverte (elle ne
   prend presque pas de mémoire vidéo une fois les modèles déchargés).
8. **Lancement du serveur Crew par WMI** : j'ai repris exactement votre commande (les chemins sont juste mis
   entre guillemets). Le processus est retrouvé ensuite grâce à `serveur_crew.py` dans sa ligne de commande.
9. **Temps de démarrage** : les délais maximaux (2 min 30 pour Docker, 5 min pour charger gemma, etc.) sont
   des estimations. Si votre PC est plus lent, augmentez-les dans `reglages.py`.
10. **Rendu de la fenêtre sous Windows 11** : testé sous Linux uniquement. Les couleurs et les tailles
    devraient être les mêmes, mais la police Segoe UI peut légèrement changer les proportions.

### Incertitudes de la version 2

11. **Le paramètre `?model=` d'Open WebUI** : il est **documenté** par Open WebUI (page « URL
    Parameters » : `?model=` pour un modèle, `?models=` pour plusieurs). La documentation précise qu'il
    empêche le retour au modèle par défaut. Je n'ai pas pu vérifier depuis quelle version il existe :
    si Open WebUI ouvre une conversation avec un autre modèle, dites-le-moi.
12. **L'API des conversations d'Open WebUI** : d'après le code source d'Open WebUI, `GET /api/v1/chats/`
    renvoie la liste la plus récente d'abord (`updated_at`), **60 par page** (`?page=1`), avec pour chaque
    conversation `id`, `title`, `updated_at`, `created_at`. Le détail (`GET /api/v1/chats/<id>`) contient
    `chat.models` et les messages (avec leur `model`). Le panneau regarde ces trois endroits et accepte
    aussi une liste « emballée » (`{"items": […]}`). Je n'ai pas vu la réponse de **votre** version.
13. **Les liens `lmstudio://`** : j'ai cherché. Les seuls liens **documentés** par LM Studio sont
    `lmstudio://open_from_hf?model=…` (télécharger un modèle depuis Hugging Face) et
    `lmstudio://add_mcp?…` (ajouter un serveur MCP). **Aucun lien documenté n'ouvre une nouvelle
    conversation avec un modèle précis.** Conformément à votre demande, je n'en ai pas inventé : le
    panneau ouvre `LM Studio.exe`, affiche le nom du modèle à choisir et le copie dans le presse-papiers.
14. **La taille des modèles** (`sizeBytes` de `lms ps --json`) : si ce champ manque dans votre version,
    le panneau propose le premier modèle de conversation chargé (aujourd'hui, gemma de toute façon).
15. **Si LM Studio est déjà ouvert**, relancer `LM Studio.exe` devrait simplement ramener sa fenêtre au
    premier plan (comportement habituel des applications de ce type), mais je ne l'ai pas vérifié.
