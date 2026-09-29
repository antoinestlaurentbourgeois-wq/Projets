# Vérifications manuelles : phase 4 (téléphone)

Suivez d'abord `TELEPHONE.md` (étapes 1 à 3), puis :

## A. Exposition (sur le PC)

- [ ] `scripts\tester_telephone.bat` : toutes les lignes `[OK]`. Notez le texte exact de celles qui échouent.
- [ ] Dans un terminal : `tailscale serve status` montre `https://<nom>.ts.net` → `http://127.0.0.1:8740`, et **pas** « Funnel on ».
- [ ] `tailscale funnel status` : rien d'actif.
- [ ] Depuis l'extérieur du réseau (téléphone en données mobiles, **Tailscale désactivé**) : l'adresse `https://<nom>.ts.net/` ne répond pas.
- [ ] Depuis l'extérieur, `http://<IP-du-PC>:8740` (réseau local) ne répond pas.

## B. Sur le téléphone

- [ ] Tailscale connecté → `https://<nom>.ts.net/` affiche la page de connexion (cadenas HTTPS valide).
- [ ] Connexion avec le NIP et le mot secret ; les 6 pages s'affichent sans défilement horizontal (Centre, Salles, Voix, Tiroir, Coûts, Journal). Les boutons sont assez grands pour le doigt.
- [ ] Installation « comme une application » : icône (cible bleue), ouverture plein écran, demande la connexion.
- [ ] Centre : les voyants s'actualisent. Un interrupteur (ex. Kokoro) demande **le NIP** ; après confirmation, ça s'exécute. Une seconde action dans les 5 min ne redemande pas le NIP.
- [ ] Mode jeu / Tout démarrer : demandent la confirmation habituelle **et** le NIP.
- [ ] Salles : discussion avec chaque IA ; réponse en continu ; mettre l'écran en veille pendant une réponse, revenir : la réponse est complète.
- [ ] **Approbation de Claude depuis le téléphone** : la carte apparaît ; « Valider mes choix » demande le NIP.
- [ ] Voix LIVE : le micro est demandé (HTTPS) ; on peut converser ; l'écran reste allumé ; le compteur de coût s'affiche.
- [ ] Talkie-walkie : maintenir le bouton, parler, relâcher : ça transcrit, répond, lit. (Sur iPhone : format `audio/mp4`.)
- [ ] « Ouvrir Open WebUI » depuis le téléphone : le message précise que l'application s'ouvre sur le PC ; elle s'ouvre bien sur le PC.
- [ ] Journal → Sécurité : le téléphone apparaît (« à distance »). « Déconnecter tous les autres appareils » depuis le PC déconnecte le téléphone.

## C. Refus attendus

- [ ] Avec un **autre** compte Tailscale (ou un appareil invité) : 403 « Accès refusé ».
- [ ] 5 mauvais NIP/mots secrets : message « Patientez… ».
- [ ] Dans `reglages.json`, retirer le nom d'hôte, redémarrer : le téléphone reçoit « Adresse non autorisée » (421).
