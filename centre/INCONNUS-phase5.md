# Ce dont je ne suis pas sûr : phase 5

1. **« Truth Gate » de GLAMMBOX.** Je n'ai pas pu lire le paquet : mon « Truth Gate » est **mon interprétation** (second avis d'une autre IA qui note chaque affirmation, sortie JSON, tout traité comme donnée). Si le vôtre est autre chose (règles, sources…), dites-le-moi.
   Le format JSON demandé est respecté « en général » par les modèles ; sinon la réponse brute est affichée. Une IA peut aussi confirmer une erreur : le verdict n'est pas une preuve.
2. **Planificateur de tâches.** `Register-ScheduledTask` avec un déclencheur « une fois, répété toutes les 10 min pendant 3650 jours » (`RepetitionDuration`). Sur certaines versions de Windows/PowerShell 5.1 cela peut échouer ou ne pas se répéter : vérifiez dans `taskschd.msc` que « Prochaine exécution » avance.
   Les tâches tournent **uniquement quand vous êtes connecté** (pas de mot de passe stocké) ; `-StartWhenAvailable` rattrape une exécution manquée (PC éteint à 03:00).
3. **`cache.vbs`.** Lance PowerShell sans fenêtre (`wscript //B`). Certains antivirus se méfient des `.vbs` : à surveiller.
4. **Le gardien relance le serveur par `demarrer_centre.ps1` (WMI)** depuis une tâche planifiée : je n'ai pas pu vérifier que le processus survit à la fin de la tâche (c'est le rôle de WMI ; à confirmer par le test « arrêter le Centre puis attendre »).
5. **Détection de « funnel ».** Le gardien cherche « Funnel on » dans `tailscale funnel status` : formulation à confirmer.
6. **Notifications de rappel.** Pas de notification quand l'application est fermée (il faudrait Web Push via Google/Apple, donc sortir du PC). Les notifications du navigateur n'apparaissent que page ouverte. Sur iPhone, `Notification` n'existe que pour les PWA installées (iOS 16.4+) : à tester.
7. **Sauvegarde.** Elle contient vos conversations, tiroir (y compris les éléments **privés**), rappels : ce sont vos données, sur votre disque I:. Elle n'est pas chiffrée. Le **NIP et le mot secret ne sont pas sauvegardés** : après une restauration complète, redéfinissez-les (`definir_verrou.bat`). La détection de « ressemble à une clé » est heuristique (modèles `sk-…`, `Bearer …`, `api_key=…`, `AIza…`) : un secret d'une autre forme ne serait pas reconnu.
8. **Rapport d'usage** : mêmes limites que les coûts (estimations). Les dépenses de Crew ne sont pas comptées avec précision (voir INCONNUS-phase2, n° 13).
9. **Départements** : les cinq fournis sont **génériques** (je ne connais pas votre métier au détail) ; adaptez-les ou ajoutez les vôtres.
10. **Bulletin** : composé sans IA, à partir des données locales. Les coûts de la veille viennent de `depenses.jsonl` (donc du Centre seulement, pas des autres usages).
