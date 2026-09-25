# MécaCalc — Calculateur d'ingénierie mécanique

Application web autonome (un seul fichier `index.html`, aucune dépendance ni compilation) qui regroupe cinq calculateurs :

| Module | Contenu |
|---|---|
| **Poutres** | 5 cas (appuyée, console, bi-encastrée ; charge ponctuelle ou répartie), réactions, V, M, σ, τ, flèche, diagrammes V/M/déformée, sections rect./rond/tube/HSS/personnalisée |
| **Assemblages boulonnés** | ISO métrique et UNC, classes 4.6–12.9 / SAE 2-5-8, précharge, couple, rigidités (Wileman), constante C, séparation, glissement, von Mises, diagramme du joint |
| **Colonnes / flambage** | Euler + Johnson, conditions d'appui (K théorique ou recommandé AISC), élancement, facteur de sécurité, courbe σcr–λ |
| **Hydraulique** | Force de vérin (sortie/rentrée), pression requise, débit, puissance, volumes, diamètres de conduites, graphique F–p |
| **Soudures** | Bout à bout (pénétration complète) et cordon d'angle, admissibles AISC/AWS, taille min. AWS D1.1, longueur et taille requises |

Fonctionnalités : unités métriques / impériales (bascule globale), calcul instantané, vérifications colorées et taux d'utilisation, graphiques interactifs, hypothèses et formules affichées dans chaque module, historique local (localStorage) avec rechargement et export CSV, thème clair/sombre, mise en page adaptée au mobile.

## Utilisation

Ouvrir `index.html` dans un navigateur. Aucune installation requise (fonctionne hors ligne ; la police Inter est chargée depuis Google Fonts si disponible).

> Outil d'aide au calcul préliminaire : les résultats doivent être validés selon les normes applicables.
