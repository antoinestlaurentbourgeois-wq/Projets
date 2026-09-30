> **Remplacé par `RETOUR-table-ronde-suite.md`** : le contrat ci-dessous (provisoire) a été corrigé d'après le vrai Crew.

# Table ronde — ce qui a été supposé sur le contrat avec Crew

Le contrat fourni dans le prompt est **provisoire**. Voici tout ce que le Centre suppose. À vérifier avec le vrai Crew avant de considérer la table ronde comme validée.

## Ce qui vient du prompt (repris tel quel)
- Envoi : `POST http://127.0.0.1:8765/v1/chat/completions`, `model: "crew-tableronde"`, `stream: true`, `table_ronde: {participants, critique, synthese}`. **Un seul appel** par message.
- Estimation : `POST http://127.0.0.1:8765/table-ronde/estimation` (même corps) → `{"participants":[{"id","cout_estime_usd","disponible","raison"}],"total_usd":0.0}`.
- Chaque morceau du flux porte `participant` et `tour` ; le dernier morceau de chaque participant porte `usage`. La synthèse est le participant `"synthese"`.
- Ids des participants : `claude`, `codex`, `gemini`, `grok`, `deepseek`, `gemma`.

## Ce que j'ai dû supposer (non précisé)
1. **Exclusion (contenu confidentiel)** : un morceau avec `participant` + `statut: "exclu"` (ou `exclu: true`) et une `raison` optionnelle. Le Centre affiche « exclue : contenu confidentiel, traité en local seulement » et ne tente rien d'autre.
2. **Échec d'un participant** : un morceau avec `statut: "erreur"` (ou un champ `erreur`). Les autres colonnes continuent.
3. **Durée** : `usage.duree_s` si présent ; sinon le Centre mesure lui-même du premier morceau au dernier.
4. **Coût réel** : `usage.cout_usd` par participant. Sans bloc `usage`, la colonne se termine avec un coût inconnu (affiché « — »).
5. **Morceau sans `participant`** : traité comme la synthèse.
6. **`tour` invalide ou absent** : ramené à 1. Ids inconnus : ignorés.
7. **Estimation** : Crew renvoie une ligne par participant demandé. Le Centre interroge Crew sur les six IA (`tous: true`) pour pouvoir griser les indisponibles, puis **additionne lui-même** seulement les cochées et disponibles (`total_usd` de Crew n'est pas utilisé tel quel). Avec `critique: true`, l'estimation de Crew doit déjà inclure le 2e tour (le simulateur double).
8. **Sans synthèse** : `synthese: false` = Crew ne produit pas de synthèse (interprétation de la case « Sans synthèse »).
9. **Crew arrêté ou Mode jeu** : détecté par l'état des services du Centre (pas par une erreur de Crew). Message : « Crew est arrêté (ou en Mode jeu)… Les salles individuelles fonctionnent toujours. » Une 404 sur l'estimation = Crew ne connaît pas encore la table ronde (message dédié).
10. **Salle** : `codex` correspond à la salle `chatgpt` pour les compteurs de coût ; les coûts réels sont rangés sous chaque IA (`estime=False`) et comptent dans les plafonds.

## Déviations volontaires (à valider)
- **Filet côté Centre en conversation privée** : si la conversation est marquée privée, seule `gemma` est acceptée comme participant, même si Crew ferait déjà son tri. Le prompt dit que le Centre ne décide jamais quelle IA voit quoi ; ce filet est plus strict et ne fait que **refuser** l'envoi (jamais élargir). À retirer si Crew doit être seul juge.
- **`confirme_depassement`** : champ ajouté côté Centre (pas envoyé à Crew). Au-dessus du seuil (`seuil_table_ronde_usd`, défaut 0,10 $), le navigateur redemande confirmation avec une estimation fraîche ; le serveur refuse sinon (`code: "depassement"`).
- **Plafonds jour/mois** : la table ronde est bloquée si le plafond de Crew est atteint (`peut_utiliser("crew")`).

## Ce qui n'a PAS été testé
- Aucun essai contre le vrai Crew ni sur le PC : tout est validé avec le faux Crew (`simulateur.py`, `simulation.py`, `tests/test_tableronde.py`).
- Comportement réel des paliers de confidentialité de Crew, format exact des morceaux d'exclusion/erreur, coûts réels.
