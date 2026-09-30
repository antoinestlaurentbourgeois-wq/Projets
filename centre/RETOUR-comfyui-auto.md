# ComfyUI automatique — ce qui a été fait et ce qui a été supposé

Branche `claude/new-session-bl6q4z`. Crew n'a pas été touché. Tout est validé avec des faux (faux Crew, faux scripts, faux ComfyUI) : **rien n'a été essayé avec les vrais scripts, le vrai Crew ni la vraie carte graphique.** La session locale doit faire l'essai réel complet (libération, démarrage, image, arrêt, reprise) avec l'accord d'Antoine (section K de `VERIFICATIONS.md`).

## Ce que fait le Centre

**Cycle d'une création locale** (un seul clic de confirmation, dans la fenêtre existante, avec le texte demandé) :
1. contrôles : Mode jeu refusé (explication) ; ComfyUI doit être installé (les deux scripts présents) ; Crew occupé → 409 affiché tel quel ;
2. `POST /chef/liberer` si le chef est chargé, puis suivi de `GET /chef` jusqu'à la fin ; Crew arrêté : on saute ;
3. `demarrer_comfyui.ps1` (délai 120 s), puis vérification que le port 8188 répond ;
4. création (code existant) ;
5. `arreter_comfyui.ps1`, attente que le port 8188 soit fermé (30 s max), pause de 3 s ;
6. `POST /chef/reprendre`, suivi de `GET /chef`, puis « Chef rechargé : Crew est de nouveau disponible. ».

Étapes affichées : « Libération de la carte graphique par Crew… / Démarrage de ComfyUI… / Création de l'image k sur n… / Arrêt de ComfyUI… / Rechargement du chef… ».

**« finally »** (`Images._clore_cycle`, appelé après CHAQUE création locale, succès, échec ou annulation) : arrête ComfyUI si c'est le Centre qui l'a lancé, puis recharge le chef — sauf Mode jeu, Crew arrêté, case « laisser la carte libre ensuite », ou autre création locale en attente (on garde alors ComfyUI et la carte : **un seul cycle** pour plusieurs demandes). Un échec de démarrage donne « ComfyUI n'a pas démarré. Journal : <dossier>\comfyui.log » (jamais de trace brute) et le chef revient quand même.

**ComfyUI lancé à la main** : jamais démarré ni arrêté par le Centre, sauf case « ComfyUI tourne déjà : l'arrêter ensuite » (champ `arreter_comfyui`). Dans ce cas le Centre lui fait seulement rendre la mémoire (`/free`) avant de recharger le chef. L'état du travail porte `demarre_par_le_centre`.

**Sécurité mémoire** : ComfyUI lancé par le Centre (cycle ou bouton Démarrer) est arrêté après 10 minutes d'inactivité (vérifié par la boucle de fond ; repoussé si `/queue` montre du travail ou si une création est en cours).

**Réconciliation** (`GET /api/comfyui`, jamais d'action automatique) : bandeau « La carte graphique est encore libérée. Recharger le chef ? » [Recharger le chef] si `libere` est vrai, sans création en cours, hors Mode jeu et ComfyUI arrêté ; bandeau « ComfyUI tourne et occupe la carte graphique [Arrêter] » s'il répond sans création en cours. Affichés sur la page Centre et la page Images. Routes `POST /api/comfyui/arreter` et `POST /api/comfyui/reprendre-chef` : session, anti-CSRF et NIP reconfirmé à distance.

**Mode jeu** : refuse une création locale ; arrête ComfyUI (il est le premier de la séquence d'arrêt) ; il reste « en vigueur » après la séquence tant que ni LM Studio ni Crew n'ont été rallumés (sinon le chef aurait été rechargé derrière lui par la création en cours). **« Tout démarrer » ne lance jamais ComfyUI** (composant marqué `tout_demarrer=False`).

**Panneau et page Centre** : composant « ComfyUI (images locales) » (voyant vert/rouge selon 127.0.0.1:8188, Démarrer / Arrêter à la main, avertissement sur la carte partagée ; confirmation avant Démarrer dans le Centre). Mêmes deux scripts.

**Sécurité** : dossier fixe `I:\IA\ComfyUI`, clé facultative `dossier_comfyui` de `reglages.json` ; le dossier est validé (chemin absolu, pas de « .. » ni de caractère étrange) et les DEUX scripts doivent y être, sinon refus. Appel `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <script>` en liste d'arguments, sans aucun autre argument, avec un délai ; aucun texte d'utilisateur, d'IA ou d'image dans une commande. Jamais de démarrage avec Windows ni de tâche planifiée. Le Centre ne touche jamais à LM Studio (seulement les adresses de Crew). Aucune description d'image dans les journaux ni les reçus (vérifié par un test).

## Ce que j'ai supposé (à vérifier sur le PC)
1. **`GET /chef` expose `libere`** (booléen) : lu par `analyser_chef` (absent = faux). C'est ce qui déclenche le bandeau de réconciliation.
2. **`POST /chef/reprendre`** : 202 puis suivi par `GET /chef` (`changement`) ; si `changement` est déjà vide, on considère le chef rechargé. Les 404 / 409 / 503 sont traduits en messages.
3. **Arrêt** : `arreter_comfyui.ps1` rend la main avant que le port soit fermé ; le Centre attend jusqu'à 30 s puis patiente 3 s. Si le port reste ouvert, le chef est quand même rechargé mais un message dit que ComfyUI ne s'est pas arrêté.
4. **Démarrage** : sortie 0 du script = ComfyUI répond ; le Centre revérifie quand même le port (10 s). `/queue` de ComfyUI (file de travail) est supposé présent ; s'il ne répond pas, on considère que ComfyUI est inutilisé.
5. **Modèles ComfyUI** : le menu liste les derniers modèles vus (mémorisés dans `images_checkpoints.json`) quand ComfyUI est arrêté ; s'il n'y en a encore aucun, le modèle est choisi après le démarrage (le premier de la liste si le demandé n'existe pas).
6. **Confirmation** : demandée aussi quand le chef n'est pas chargé mais que ComfyUI doit être démarré (texte court, sans la partie Crew). Pas de confirmation si ComfyUI tourne déjà et que le chef n'est pas chargé.
7. **Moteur par défaut** : ComfyUI seulement s'il répond déjà ; sinon xAI si disponible ; sinon ComfyUI (il démarrera à la demande).
8. **Mode jeu « en vigueur »** est une déduction du Centre (il ne peut pas savoir si vous jouez encore) : levé dès que LM Studio ou Crew répondent, ou après « Tout démarrer » / un démarrage de composant.
9. **Arrêt par inactivité** : ne concerne que ComfyUI lancé par le Centre ; un ComfyUI lancé à la main n'est jamais arrêté tout seul.

## Non fait / limites
- Les scripts `.ps1` ne sont pas dans ce dépôt (ils sont sur le PC, fournis par la session locale).
- Si le Centre est fermé pendant un cycle, ComfyUI et/ou le chef peuvent rester dans l'état intermédiaire : c'est le rôle des bandeaux de réconciliation au redémarrage.
