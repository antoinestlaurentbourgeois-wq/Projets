# Ce dont je ne suis pas sûr : phase 4

1. **Syntaxe de `tailscale serve`.** Le script lance `tailscale serve --bg --https=443 http://127.0.0.1:8740` (syntaxe des versions récentes, supposée). Repli indiqué si ça échoue : `tailscale serve --bg 8740`.
   Pour arrêter : `tailscale serve --https=443 off` puis `tailscale serve reset`. Si votre version diffère, envoyez-moi la sortie de `tailscale serve --help`.
2. **En-têtes ajoutés par `tailscale serve`.** J'attends `Tailscale-User-Login` (adresse du compte) et `X-Forwarded-Proto: https` sur les requêtes venant du tailnet, et l'**absence** de `Tailscale-User-Login` via `funnel`.
   C'est la base de la protection « identité exigée » : si l'en-tête porte un autre nom ou n'est pas ajouté, **tout accès distant sera refusé (403)** : le message « Accès refusé » est alors le signe. Vérifiez avec `tester_telephone.bat`, et envoyez-moi les en-têtes réels si besoin
   (`tailscale serve` peut être remplacé temporairement par `exiger_identite_tailscale: false` dans `reglages.json`, mais ne le laissez pas ainsi).
3. **Lecture de `tailscale status --json`.** Le script lit `Self.DNSName`, `Self.UserID`, `User.<id>.LoginName`, `BackendState`. Noms de champs supposés d'après les versions courantes.
4. **`tailscale funnel status`.** Je cherche le texte « Funnel on » dans les sorties de `serve status` et `funnel status` : formulation à confirmer sur votre version.
5. **Console Tailscale.** Le chemin « DNS → Enable HTTPS » et la syntaxe d'ACL `grants` sont donnés de mémoire ; vérifiez dans la documentation Tailscale en cours.
6. **Installation d'une PWA sur iPhone** : passe par « Sur l'écran d'accueil » de Safari ; le service worker est minimal. Le micro dans une PWA iOS installée peut se comporter différemment de Safari : à tester.
7. **Écran de veille sur téléphone.** `navigator.wakeLock` n'existe pas partout ; si le système verrouille l'écran, le LIVE peut se couper (la session se ferme proprement, la réponse écrite continue sur le PC).
8. **Un seul compteur de blocage** (global) pour connexion et NIP : quelqu'un du tailnet peut donc vous faire attendre quelques minutes. Choix assumé (sécurité avant confort).
9. **Nom du PC changé** dans Tailscale : relancez `tailscale_configurer.bat` (le nom d'hôte est écrit dans `reglages.json`).
