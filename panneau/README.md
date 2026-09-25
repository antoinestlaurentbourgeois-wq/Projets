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
| `reglages.py` | Les chemins, noms et délais — **le seul fichier à modifier** |
| `simulateur.py` | Une fausse installation, pour les tests et le mode démo |
| `tests/test_panneau.py` | Les tests automatiques (59 tests, tout est simulé) |
| `creer_raccourci.bat` / `.ps1` | Crée le raccourci sur le bureau |
| `demo.bat` | Ouvre le panneau en mode démo |
| `lancer_tests.bat` | Lance les tests automatiques |
| `panneau.log` | Le journal (créé au premier lancement, 500 Ko max) |

## Lancer les tests automatiques

Double-cliquez sur `lancer_tests.bat`. La dernière ligne doit être **`OK`**.
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

## ⚠️ Ce que je n'ai pas pu vérifier

Je n'ai pas accès à votre PC. Tout a été testé **en simulation** (59 tests automatiques), et l'interface a
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
