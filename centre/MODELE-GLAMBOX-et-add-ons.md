# Le modèle GLAMBOX — en bref, et les add-ons à prévoir

*Basé sur le paquet GLAMMBOX (cockpit + GLAMMBRAIN, licence MIT) et sur le Centre tel qu'il est aujourd'hui. Je n'ai pas vu l'architecture préparée par ChatGPT : la section 4 donne une grille pour la comparer.*

## 1. Le modèle GLAMBOX en 6 lignes
1. **Un cockpit unique** (page web + PWA téléphone) devant **plusieurs IA** : chaque IA a un *adaptateur* (Claude, Codex, Gemini, Grok, Ollama…).
2. **Une mémoire locale** (GLAMMBRAIN) : le dossier de fichiers est la **source de vérité** ; les index (Qdrant = sens, BM25 = mots exacts, reranker = tri final, Neo4j = liens, optionnel) se **reconstruisent** depuis lui, jamais l'inverse.
3. **Chaque réponse a un reçu** : source (fichier + extrait) derrière chaque résultat.
4. **Des départements** (images, vidéo, sites, jeux, avatars, marque) : des démarrages rapides, pas des programmes séparés.
5. **Sécurité par défaut** : verrou NIP + mot secret, serveur sur `127.0.0.1`, aucune clé dans le navigateur, approbation humaine pour les actions sensibles.
6. **Honnêteté** : le paquet est livré *vide* ; rien n'est « magique » ni « sans installation » ; les promesses se limitent à ce qui tourne réellement.

## 2. Où en est le Centre par rapport à ce modèle

| Brique GLAMBOX | Dans le Centre |
|---|---|
| Cockpit + PWA | fait (PC et téléphone, Tailscale) |
| Adaptateurs d'IA | fait (`ia.py`, `salles.py`) + table ronde |
| Verrou, session, CSRF, NIP à distance | fait (`verrou.py`, garde ASGI) |
| Voix (LIVE, push-to-talk, bulletin) | fait (`voix.py`, `bulletin.py`) |
| Tiroir, rappels, départements, Truth Gate, gardien, sauvegarde, rapport | fait |
| Images (moteurs nuage + ComfyUI local) | fait, avec cycle GPU automatique |
| Approbations | fait, avec « Toujours approuver » en liste blanche lecture seule |
| **Mémoire hybride GLAMMBRAIN** (Qdrant + BM25 + reranker) | **partiel** : `memoire.py` appelle la mémoire de Crew ; pas encore de pile locale propre au Centre |
| Graphe (Neo4j) | non |
| Vidéo, avatars, sites, jeux | départements = démarrages rapides seulement |

## 3. Architecture cible (couches, un seul sens de dépendance)

```
Interface (web/PWA)         pages : Centre · Salles · Chef · Images · Voix · Coûts · (add-ons)
        │
API du Centre (Starlette)   garde : session + CSRF + NIP à distance + reçus
        │
Services                    salles · images · voix · mémoire · approbations · coûts · comfyui
        │
Adaptateurs  (un fichier par fournisseur, même interface)
        │
Fournisseurs                Crew · LM Studio · ComfyUI · API nuage · Qdrant/BM25/reranker (futur)
```

**Règle d'or des add-ons** : un add-on = un *module* + une *page* + des *routes protégées* + des *tests avec faux* + un `RETOUR-*.md`. Il ne touche ni au verrou, ni à la politique de confidentialité, ni aux plafonds de coûts : il les **appelle**.

## 4. Grille pour comparer avec l'architecture de ChatGPT
Garder ce qui la respecte, écarter ce qui la viole :
- [ ] Le serveur n'écoute que sur `127.0.0.1` ; accès distant seulement par Tailscale.
- [ ] Aucune clé dans le navigateur, les fichiers ou les journaux.
- [ ] Le dossier source reste la vérité ; les index sont reconstructibles.
- [ ] Chaque résultat de mémoire cite sa source.
- [ ] Un contenu confidentiel ne peut aller que vers un moteur **local** (refus côté serveur).
- [ ] Aucune action sensible sans approbation humaine ; jamais `--dangerously-skip-permissions`.
- [ ] Pas de compilation JS imposée, Windows natif, pas de WSL/systemd obligatoire.
- [ ] Les promesses du texte correspondent à ce qui tourne (pas de « tout reste local » sans condition).

## 5. Add-ons futurs (prévus, pas commencés)

| # | Add-on | Accroche dans le Centre | Garde-fous à prévoir |
|---|---|---|---|
| 1 | **Mémoire GLAMMBRAIN locale** (Qdrant + embeddinggemma via Ollama + BM25 + reranker) | `memoire.py` : nouveau fournisseur à côté de celui de Crew | dossier source en lecture seule ; zones « partageable » / « privé » ; reçu fichier + extrait |
| 2 | **Graphe de relations** (Neo4j, optionnel) | page « Liens » alimentée par la mémoire | outil séparé, jamais requis ; mot de passe hors fichiers |
| 3 | **Courriel (AgentMail)** : lire, rédiger, envoyer | outils MCP en salle Claude | lecture en liste blanche ; **carte d'autorisation par envoi** (boîte, À/Cc/Cci, objet, texte, pièces jointes) ; jamais de « Toujours » sur un envoi ; suppression et comptes refusés |
| 4 | **Modifier cette image** (image → image) | `images.py` phase 2 (xAI `/v1/images/edits`, ComfyUI img2img) | essai réel du format avant ; même file d'attente et mêmes coûts |
| 5 | **Vidéo** (génération / montage) | département + moteur dans `images.py` ou module `video.py` | coût estimé avant ; confirmation ; GPU arbitré comme ComfyUI |
| 6 | **Avatars / personas** | `personas/` + consigne de salle | données locales ; aucun envoi de photo sans clic |
| 7 | **Sites et jeux** (départements actifs) | démarrages rapides → modèles de projet dans l'atelier | écriture seulement dans le dossier de travail, approbation par action |
| 8 | **Planificateur** (tâches récurrentes de l'IA) | `rappels.py` + gardien | liste blanche d'actions ; plafond de coût par tâche ; reçu à chaque exécution |
| 9 | **Autres fournisseurs** (nouvel adaptateur) | `ia.py` : une classe, une salle | même politique de confidentialité, mêmes plafonds |
| 10 | **Tableau de bord d'usage** (coûts par IA, par jour, par salle) | `rapport.py` + page Coûts | aucune donnée de contenu, seulement des totaux |
| 11 | **Export / sauvegarde chiffrée** | `sauvegarde.py` | sans les secrets ; 7 dernières copies ; test de restauration |
| 12 | **Mode multi-utilisateur** (famille / équipe) | identité Tailscale déjà lue | droits par utilisateur ; aucune salle partagée par défaut |

## 6. Ordre conseillé
1. **Courriel avec cartes d'autorisation** (le besoin le plus concret, et les règles sont déjà décidées).
2. **Mémoire GLAMMBRAIN locale** (la vraie valeur du modèle GLAMBOX).
3. **Modifier cette image**, puis **vidéo**.
4. Le reste selon l'usage réel.

Chaque étape : prompt court → livraison sur la branche avec tests → relecture et essai réel par la session locale (listes dans `VERIFICATIONS.md`).
