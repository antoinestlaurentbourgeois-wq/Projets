# Vérifications manuelles : phase 5 (extras)

## A. Installation des tâches planifiées

- [ ] Double-cliquez sur `scripts\installer_taches.bat` : deux tâches sont créées. Vérifiez dans le **Planificateur de tâches** (`taskschd.msc`) : `Centre-Gardien` (toutes les 10 minutes) et `Centre-Sauvegarde` (chaque nuit à 03:00).
- [ ] Aucune fenêtre ne clignote quand le gardien tourne (il passe par `cache.vbs`).
- [ ] Après 10 à 15 minutes : `I:\IA\CENTRE\donnees\taches.log` contient des lignes « gardien : OK ». La page **Journal → Entretien** affiche « dernier passage … tout va bien ».
- [ ] **Test du gardien :** arrêtez le Centre (`arreter_centre.bat`) : au prochain passage (≤ 10 min), le gardien **le relance** tout seul (`taches.log` : « Le serveur ne répond pas : relance »).
- [ ] Le gardien signale les problèmes : (a) une clé absente (ex. `XAI_API_KEY`), (b) aucune sauvegarde, (c) moins de 5 Go libres sur I:. Ces alertes s'affichent dans Journal → Entretien.
- [ ] Si le gardien s'arrête (désactivez la tâche 35 min) : la page Journal affiche « le gardien ne s'est pas exécuté depuis plus de 30 minutes ».
- [ ] Le gardien voit un « funnel » Tailscale (si vous en activez un pour tester : `tailscale funnel 8740`, à couper aussitôt) : alerte « DANGER ».

## B. Sauvegarde de nuit

- [ ] Journal → Entretien → **Sauvegarder maintenant** : « Sauvegarde centre-….zip : N fichiers ». Le fichier apparaît dans `I:\IA\CENTRE\sauvegardes\`.
- [ ] Ouvrez le ZIP (clic droit → Extraire) : conversations, tiroir, reçus, rappels… **mais ni `verrou.json` ni aucune clé** (ouvrez `MANIFESTE.json` : liste des fichiers écartés).
- [ ] Après plusieurs jours : **7 sauvegardes au maximum**.
- [ ] Depuis le téléphone : « Sauvegarder maintenant » demande le NIP.
- [ ] **Restauration à blanc :** `scripts\restaurer_sauvegarde.bat centre-AAAAMMJJ-HHMMSS.zip I:\IA\CENTRE\restauration` extrait dans un dossier neuf (refuse un dossier non vide). Rien n'écrase vos données actuelles. Pour revenir en arrière, copiez à la main les fichiers voulus (le Centre arrêté), puis redéfinissez le NIP/mot secret si besoin (`verrou.json` n'est jamais sauvegardé).

## C. Rappels et bulletin

- [ ] Page **Rappels** : ajoutez un rappel dans 2 minutes. À l'échéance, le bandeau rouge « Rappel : … » apparaît sur **toutes les pages** (avec « Fait » et « +1 h »).
- [ ] « Activer les notifications du navigateur » : à l'échéance, une notification du navigateur apparaît (page ouverte). Pour un rappel privé, elle ne montre pas le texte.
- [ ] Rappel récurrent (quotidien, hebdomadaire, mensuel) : « Fait » le reporte à la prochaine échéance au lieu de le supprimer.
- [ ] **Bulletin du matin** : à la première ouverture de la journée, une boîte affiche le bulletin (date, services, mode de Crew, rappels du jour, coûts, actions à valider, alertes du gardien). Décocher « Afficher automatiquement » l'arrête.
- [ ] « Lire à voix haute » (clé OpenAI requise) lit le bulletin. **Un rappel privé n'est PAS lu** (seulement « Et 1 rappel privé, à voir à l'écran »).
- [ ] Mode Confidentiel/Ultra : le bulletin s'affiche encore, mais la lecture est refusée.

## D. Départements

- [ ] Page **Départements** : 5 départements. Un clic sur un démarrage rapide (ex. « Revoir une note de calcul ») ouvre la salle prévue avec le texte prêt, à compléter avant d'envoyer.
- [ ] « Chercher dans ma bibliothèque » (Bureau d'études) coche la mémoire.
- [ ] Ajoutez `I:\IA\CENTRE\donnees\departements\mon-departement.json` (même format qu'un fichier de `centre\departements\`) : il apparaît. Un fichier cassé est signalé en haut de la page, sans rien casser.

## E. Truth Gate (vérifier une réponse)

- [ ] Dans une salle, sous une réponse : **Vérifier** → choisir une autre IA → une fiche : verdict, résumé, affirmations notées (✔ confirmée / ? douteuse / ✘ fausse / … invérifiable).
- [ ] Vérifier une réponse **volontairement fausse** (ex. demandez à gemma une date historique et forcez une erreur) : l'autre IA la repère-t-elle ? (Ce n'est pas une preuve : à recouper.)
- [ ] La même IA que celle qui a répondu est refusée. Une conversation privée ne peut être vérifiée que par gemma/Crew.

## F. Rapport d'usage

- [ ] Page **Coûts → Rapport d'usage** : total, moyenne par jour, dépense par IA, messages par salle, minutes de voix, histogramme. « Télécharger en CSV » s'ouvre dans Excel (accents et virgules décimales corrects).
- [ ] Les totaux concordent avec les factures des fournisseurs à quelques centimes/pourcents près (ce sont des estimations).
