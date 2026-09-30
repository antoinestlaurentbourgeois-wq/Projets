# Revue de sécurité : accès par téléphone (phase 4)

Cette revue liste **tout ce qui devient accessible** quand le Centre est publié sur Tailscale, les protections en place, et ce qui reste à votre charge.
Chaque protection ci-dessous est couverte par un test automatique (`tests/test_telephone.py`, `tests/test_app.py`, `tests/test_voix.py`) ou par `scripts\tester_telephone.bat`.

## 1. Ce qui devient accessible

Avec `tailscale serve`, **tout le Centre** devient joignable, en HTTPS, depuis les appareils de votre réseau Tailscale (et **rien** depuis Internet) :

| Domaine | Ce qu'on peut faire | Protégé par |
|---|---|---|
| Pages et fichiers | Page de connexion et ses fichiers (style, icônes, manifeste) | Publics (aucune donnée) ; l'identité Tailscale est exigée même pour eux |
| Tout le reste (`/api/*`, pages, `/ws/voix`) | Piloter les services du PC, discuter avec les IA, lire l'historique et le tiroir, voix, coûts, journal | Session (NIP + mot secret) |
| Actions sensibles | Mode jeu, démarrer/éteindre, ouvrir une application sur le PC, changer le mode Crew, plafonds, tarifs, réglages de salle, approbations Claude, suppression, passage « partageable » | Session **+ NIP reconfirmé (5 min)** |

**Ce qui n'est PAS exposé :** aucun accès aux fichiers du PC, aucun terminal, aucune clé API (jamais envoyée au navigateur), aucun contenu de `verrou.json`.
Les programmes `claude`/`codex`/`gemini` ne travaillent que dans `I:\IA\ATELIER`, en lecture seule, et toute action sensible passe par une approbation (donc, à distance, par le NIP).

## 2. Couches de protection (de l'extérieur vers l'intérieur)

1. **Tailscale** : chiffrement WireGuard, appareils authentifiés par votre compte. Seuls vos appareils atteignent le service. (À votre charge : 2FA sur le compte Tailscale, ACL, voir §4.)
2. **`tailscale serve`, jamais `funnel`.** Le script ne configure que `serve`. `tester_telephone.bat` vérifie qu'aucun funnel n'est actif.
3. **Identité Tailscale exigée par le serveur** (`Tailscale-User-Login`). Pour toute requête dont l'adresse n'est pas locale, le serveur exige cet en-tête (ajouté par `serve`, **pas** par `funnel` ni par Internet) et, si configuré,
   qu'il corresponde à **votre** compte (`utilisateurs_tailscale`). Conséquence : si quelqu'un exposait le Centre publiquement par erreur, le serveur répondrait 403 à tout, y compris à la page de connexion.
4. **Nom d'hôte vérifié** (contre le « DNS rebinding ») : seuls `127.0.0.1`, `localhost` et les noms de `reglages.json` sont acceptés (sinon 421).
5. **Verrou** : NIP **et** mot secret (scrypt salé), attente croissante après 5 erreurs (30 s → 15 min), commune à la connexion et à la reconfirmation du NIP.
6. **Session** : jeton aléatoire, cookie `HttpOnly` + `Secure` (en HTTPS) + `SameSite=Strict`, 12 h. Le serveur ne garde que l'empreinte du jeton. **HSTS** pour les accès distants.
7. **Anti-CSRF** : en-tête `X-Centre` obligatoire pour toute écriture + contrôle de l'origine (`Origin` = hôte) ; pour les WebSockets, l'origine et la session sont contrôlées **avant** l'acceptation (contre le détournement de WebSocket entre sites).
8. **NIP reconfirmé pour les actions sensibles à distance** (valable 5 minutes, par session). Un téléphone volé et déverrouillé avec une session ouverte ne peut donc ni approuver une commande de Claude, ni éteindre/ouvrir des choses, ni changer un plafond, sans le NIP.
9. **Politique de contenu (CSP)** stricte (aucun script ni style en ligne, `frame-ancestors 'none'`, `connect-src 'self'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (micro autorisé pour ce site seulement), `Cross-Origin-*: same-origin`.
10. **Confidentialité appliquée par le serveur** (phases 2-3) : en modes Confidentiel/Ultra-confidentiel, aucune IA du nuage et pas de voix, même depuis le téléphone ; le contenu privé ne va jamais au nuage.
11. **Traçabilité** : reçus (`recus.jsonl`) pour connexions (réussies ou non), confirmations de NIP, actions, approbations, déconnexions ; page **Journal → Sécurité** avec les appareils connectés et « Déconnecter tous les autres appareils ».

## 3. Risques résiduels et recommandations

| Risque | Gravité | Ce qui est en place | Ce que vous devez faire |
|---|---|---|---|
| Téléphone volé, **déverrouillé**, session ouverte | Élevée | NIP requis pour les actions sensibles ; session 12 h ; « Déconnecter les autres appareils » | Verrouillage d'écran + biométrie ; déconnecter l'appareil depuis le PC (Journal → Sécurité) ; retirer l'appareil dans la console Tailscale. La **lecture** de l'historique et du tiroir reste possible tant que la session vit : ne gardez pas de secrets dans les salles du nuage. |
| Compte Tailscale compromis | Élevée | NIP + mot secret restent nécessaires ; identité limitée à votre compte | 2FA sur le compte Tailscale (fournisseur d'identité) ; expiration des clés d'appareils ; « approbation des appareils » |
| Autre appareil de votre tailnet (invité, ancien appareil) | Moyenne | Identité limitée à `utilisateurs_tailscale` ; NIP + mot secret | ACL Tailscale : n'autoriser que le téléphone → PC:443 (exemple ci-dessous) |
| Force brute sur le NIP/mot secret | Faible | scrypt + attente exponentielle (globale) | Mot secret long. *Contrepartie :* quelqu'un qui atteint le service peut vous bloquer quelques minutes (déni de service) ; le PC local reste utilisable après l'attente. |
| Programme malveillant sur le **PC** lui-même | Hors périmètre | — | Il pourrait imiter l'en-tête d'identité sur 127.0.0.1 ; il faudrait encore le NIP + mot secret. Protégez le PC. |
| Injection de consignes (pages web, fichiers, réponses d'IA) | Moyenne | Tout contenu externe est présenté aux IA comme **donnée** ; Claude/Codex/Gemini en lecture seule ; approbations par bouton (+ NIP à distance) ; les commandes complexes ne sont pas approuvables depuis l'écran | Lisez la carte d'approbation avant de valider. |
| Coûts | Moyenne | Plafonds jour/mois appliqués par le serveur (texte et voix), durée maximale et silence pour la voix | Réglez des plafonds bas au début. |
| Fuite via le presse-papiers / notifications du téléphone | Faible | — | — |
| Service Worker | Faible | Ne met **rien** en cache | — |

### ACL Tailscale recommandée (console d'administration → Access controls)

Exemple, à adapter (`votre-pc` et `votre-telephone` sont les noms de vos appareils dans Tailscale) :

```json
{
  "grants": [
    { "src": ["votre-telephone"], "dst": ["votre-pc"], "ip": ["tcp:443"] }
  ]
}
```
Le téléphone n'atteint alors que le port HTTPS du PC, rien d'autre. (Syntaxe `grants` à vérifier dans la documentation Tailscale de votre version ; les anciennes ACL `acls` équivalentes fonctionnent aussi.)

## 4. Liste de contrôle avant de considérer l'accès téléphone comme sûr

- [ ] `tester_telephone.bat` : tout `[OK]`, en particulier « Aucun funnel actif » et « Une requête sans identité Tailscale est refusée (403) ».
- [ ] 2FA activé sur le compte Tailscale.
- [ ] `utilisateurs_tailscale` contient uniquement votre compte (Journal → Sécurité l'affiche).
- [ ] ACL limitant l'accès (facultatif mais recommandé).
- [ ] Écran du téléphone verrouillé par code/biométrie.
- [ ] Depuis le téléphone : une action sensible (ex. Mode jeu) demande bien le NIP.
- [ ] Depuis un appareil **non** Tailscale (données mobiles sans Tailscale) : `https://<nom>.ts.net/` ne répond pas.
