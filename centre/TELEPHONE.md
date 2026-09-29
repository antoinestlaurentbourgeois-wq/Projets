# Utiliser le Centre depuis votre téléphone

Le Centre reste **verrouillé sur le PC** (`127.0.0.1`). Pour le téléphone, on passe par **Tailscale Serve** : Tailscale publie le Centre en **HTTPS**,
**uniquement pour vos propres appareils** (votre réseau privé Tailscale). Rien n'est accessible sur Internet. Le HTTPS est obligatoire : sans lui, le téléphone
refuse d'utiliser le micro.

## Ce qu'il faut avoir

- Un compte **Tailscale** (gratuit) avec le **PC** et le **téléphone** connectés au même compte. (Le programme Tailscale s'installe sur C: : c'est inévitable, c'est un service Windows.)
- Le Centre installé et le verrou défini (voir `README.md`).

## Étape 1 : autoriser HTTPS dans Tailscale (une seule fois)

1. Ouvrez https://login.tailscale.com/admin/dns (console d'administration Tailscale, connectez-vous).
2. Vérifiez que **MagicDNS** est activé.
3. Dans « HTTPS Certificates », cliquez **Enable HTTPS**. (Tailscale vous prévient que le nom de votre réseau devient public dans un registre de certificats : c'est normal, seul le *nom* est visible, pas vos appareils.)

## Étape 2 : brancher le Centre sur Tailscale

1. Sur le PC, double-cliquez sur `scripts\tailscale_configurer.bat`. Il :
   - lit le nom de votre PC dans Tailscale et votre compte ;
   - les inscrit dans `I:\IA\CENTRE\donnees\reglages.json` (hôte autorisé, et **seul votre compte Tailscale** est accepté) ;
   - redémarre le Centre, puis lance `tailscale serve` ;
   - affiche l'adresse à ouvrir sur le téléphone : `https://<nom-du-pc>.<votre-reseau>.ts.net/`.
2. Double-cliquez ensuite sur `scripts\tester_telephone.bat` : **tous les tests doivent être `[OK]`** (en particulier « aucun funnel actif »).

## Étape 3 : sur le téléphone

1. Ouvrez l'application **Tailscale** et vérifiez qu'elle est **connectée**.
2. Dans Chrome (Android) ou Safari (iPhone), ouvrez l'adresse `https://…ts.net/` donnée par le script.
3. Connectez-vous avec le NIP et le mot secret.
4. **Installer comme une application :**
   - Android/Chrome : menu ⋮ → « Installer l'application » (ou « Ajouter à l'écran d'accueil »).
   - iPhone/Safari : bouton Partager → « Sur l'écran d'accueil ».
5. Page **Voix** : autorisez le micro quand le navigateur le demande.

## Ce qui change sur le téléphone

- Les actions **sensibles** demandent de **retaper le NIP** (valable 5 minutes) : Mode jeu, Tout démarrer, allumer/éteindre, ouvrir une application sur le PC,
  changer de mode, plafonds, tarifs, réglages de salle, **approbations de Claude**, suppression de conversation, passage d'un élément du tiroir en « partageable ».
- « Ouvrir Open WebUI / LM Studio / Docker » ouvre l'application **sur le PC**, pas sur le téléphone.
- Les réponses en cours continuent sur le PC même si l'écran du téléphone se met en veille : rouvrez la conversation.
- Page **Journal → Sécurité** : la liste des appareils connectés et un bouton **« Déconnecter tous les autres appareils »**.

## Couper l'accès téléphone

`scripts\tailscale_arreter.bat` retire la publication. Le Centre reste utilisable sur le PC.

## Si ça ne marche pas

| Symptôme | Piste |
|---|---|
| `tailscale_configurer` dit que HTTPS n'est pas activé | Étape 1, « Enable HTTPS ». |
| La page ne charge pas sur le téléphone | Tailscale est-il connecté sur le téléphone ? Le PC est-il allumé et le Centre lancé (raccourci du bureau) ? |
| « Accès refusé » (403) | Le téléphone n'est pas connecté avec le même compte Tailscale que celui inscrit dans `reglages.json` (clé `utilisateurs_tailscale`), ou l'adresse n'est pas celle affichée par le script. |
| « Adresse non autorisée » (421) | Le nom d'hôte n'est pas dans `hotes_autorises` : relancez `tailscale_configurer.bat`. |
| Le micro ne démarre pas | Il faut l'adresse en **https://** (pas `http://`), et autoriser le micro pour ce site dans les réglages du navigateur. |
| Connexion bloquée « Patientez… » | 5 mauvais essais : attendez, ou entrez-vous depuis le PC. |
