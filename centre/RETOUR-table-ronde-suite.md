# Table ronde — suite : alignement sur le VRAI Crew

Le Centre, le simulateur (`simulation.py` côté Centre, `panneau/simulateur.py` côté Crew simulé) et les tests reproduisent maintenant le flux du vrai Crew. Crew n'est pas modifié.

## Corrigé (points de la liste de correction)
1. **Exclusion / erreur** : lues via `"evenement": "exclu"` / `"erreur"` + `participant` + `libelle` + `message` (la raison). Plus aucun champ `statut`, `exclu`, `raison` lu dans le flux.
2. **Durée et coût** : `duree_s` lu au niveau du morceau ; coût dans `usage {entree, sortie, cout_usd}` du morceau `"evenement": "reponse"`. Plus de « dernier morceau usage ». Sans `duree_s`, la durée est mesurée entre `debut` et `reponse`.
3. **Texte** dans `choices[0].delta.content` ; `"format": "brut"` toujours envoyé dans `table_ronde` (envoi et estimation). Une réponse complète par IA, affichée dans l'ordre d'arrivée.
4. **Morceaux sans `evenement` ignorés** : premier morceau `{"role"}`, pulsations à contenu vide, `finish_reason: "stop"`, texte égaré. Seul `participant: "synthese"` (tour 0, rangé au tour 1 côté écran, sans `debut`) est la synthèse. Un morceau sans `participant` n'est plus une synthèse. Le seul morceau sans `evenement` qui compte est une erreur globale au format OpenAI (`{"error": {...}}`), affichée comme erreur de Crew.
5. **Ligne `fin`** : coût réel total (`usage.cout_usd`) utilisé pour le coût du message et le reçu ; `exclus` (une IA exclue vue seulement ici est affichée « exclue par Crew », jamais silencieuse ; pas de doublon si un `exclu` a déjà été reçu) ; `notes` (extraits de la mémoire) affichées sous les colonnes et enregistrées dans le message. Un `debut` sans `reponse` ni `erreur` devient un échec « Aucune réponse reçue ». Une IA indisponible arrive en `erreur` (pas `exclu`).
6. **Estimation** : `tous` supprimé. Disponibilité par `GET /table-ronde/participants` (les six IA, `disponible`, `raison`) ; coût par `POST /table-ronde/estimation` avec **seulement les IA cochées et disponibles** ; `total_usd` de Crew utilisé tel quel (2e tour déjà inclus, non doublé par le Centre) ; `total_incomplet` → « au moins X $ » (case, total, confirmation du seuil, tour de critique) ; `cout_estime_usd` null → « coût inconnu », jamais compté comme 0. Un message d'erreur 400 de Crew est repris tel quel.
7. **Message « Crew ne connaît pas la table ronde » (404)** retiré.
8. Conservé : `synthese: false` = pas de synthèse ; l'erreur d'un participant n'arrête pas les autres ; la synthèse est le participant `synthese`.

## Conservé (validé)
Filet du Centre en conversation privée (seule gemma), `confirme_depassement` + `seuil_table_ronde_usd` (0,10 $, avertissement et non plafond), plafonds jour/mois via `peut_utiliser("crew")`.

## Restent des suppositions (petites)
- **Forme de `GET /table-ronde/participants`** : je lis `{"participants": [{"id", "disponible", "raison"}]}` (ou directement une liste). Une IA absente de la liste est traitée comme indisponible (« Crew ne connaît pas cette IA »).
- **`exclus` dans `fin`** : liste d'ids (ou d'objets avec `participant`/`id`).
- **`notes`** : liste de chaînes (chemins d'extraits) ; tout est converti en texte.
- **Participant `erreur`/`exclu` sans `tour`** : tour 1.
- **Sans clé de participant dans l'estimation** : si `total_usd` manque, somme des coûts connus marquée « au moins ».
- Toujours non essayé par moi contre le vrai Crew : tout est validé avec le faux Crew calqué sur ce que vous décrivez (355 tests, dont le flux avec role/pulsation/stop, exclusion, erreur, critique, tarif inconnu). Vérification navigateur en mode démo, largeur de téléphone : cases, seuil, confirmation, colonnes échec/exclue/terminée, notes, sans erreur console.
