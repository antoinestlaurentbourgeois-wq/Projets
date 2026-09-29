# Ce dont je ne suis pas sûr : phase 1

Rien de ce qui suit n'a pu être testé sans votre PC. À vérifier, et à me renvoyer si ça ne marche pas.

1. **Ouverture des applications depuis le serveur.** Le serveur est lancé par WMI (`Win32_Process.Create`), comme votre serveur Crew.
   Je ne sais pas si un programme lancé ainsi peut afficher des fenêtres sur **votre bureau** (`os.startfile` pour Open WebUI, LM Studio, Docker).
   S'il ne le peut pas, les clics sur les noms ne feront rien de visible. Repli possible : lancer le Centre par une tâche planifiée « à l'ouverture de session »
   (session interactive), ou par `scripts\serveur_visible.bat`.
2. **Paquet GLAMMBOX non téléchargé.** Le téléchargement a été refusé par le système de permissions de cette session, donc l'empreinte SHA-256 n'a **pas**
   été vérifiée et **rien** n'a été repris de GLAMMBOX. Le verrou (scrypt, session HttpOnly 12 h), la PWA et les protections ont été écrits de zéro.
   Si vous voulez toujours la reprise (client vocal, sessions temps réel, tiroir, etc. : phases 3 et 5), il faudra soit autoriser le téléchargement,
   soit me fournir le fichier ; je vérifierai l'empreinte avant tout usage.
3. **Format de la réponse de DeepSeek** `GET https://api.deepseek.com/user/balance` : j'attends
   `{"is_available": true, "balance_infos": [{"currency", "total_balance", "granted_balance", "topped_up_balance"}]}` (montants en texte).
   L'analyse est tolérante et affiche un message clair si le format diffère ; à confirmer avec votre vrai solde.
4. **Dépenses de Crew.** Le Centre ne connaît que ses propres compteurs. Je ne sais pas si le serveur Crew expose ses coûts ; en attendant,
   les dépenses de Crew ne seront pas comptées tant que la phase 2 ne les estime pas côté Centre. Idem pour les usages faits en dehors du Centre
   (Open WebUI direct, etc.) : le solde DeepSeek de la page Coûts, lui, est réel.
5. **Plafonds et Crew.** Crew est considéré « payant » sauf en modes Confidentiel et Ultra. C'est prudent, mais en mode Économe Crew peut n'utiliser que gemma (gratuit) : il sera quand même bloqué au plafond.
6. **Installabilité PWA.** Chrome/Edge exigent un manifeste, un service worker et des icônes PNG : c'est fourni, mais je n'ai pu tester qu'avec Chromium sans installation réelle.
   Sur un téléphone, l'installation exige HTTPS (phase 4, Tailscale Serve).
7. **`pythonw` et uvicorn.** Sans console, `sys.stdout` vaut `None` ; je redirige vers `console.log`. Testé par simulation seulement.
8. **Versions.** Développé et testé avec Python 3.11 ici ; vous avez 3.12. Starlette/uvicorn : dernières versions (`requirements.txt` ne fixe qu'un minimum).
   Les tests de l'interface HTTP utilisent `starlette.testclient` (qui demande `httpx`, installé par `lancer_tests.bat`).
9. **Adresse `/memoire/*` de Crew** : non utilisée avant la phase 3 (voix + mémoire).
