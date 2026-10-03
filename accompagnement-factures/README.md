# Mes factures — facturation des services d'accompagnement aux aînés

Application **iPhone** (SwiftUI, iOS 17+, testée pour iPhone 16) qui transforme les visites inscrites dans le **calendrier Apple** en factures PDF professionnelles.

## Ce que fait l'app

| Besoin | Réalisation |
|---|---|
| Lire le calendrier | Lecture **directe** du calendrier de l'iPhone (EventKit) — aucun export, aucune importation. Tous les calendriers (iCloud, Outlook/Hotmail, Gmail…) déjà configurés dans l'iPhone sont lus ; on peut en exclure dans Réglages. |
| Bonne facture au bon client | Chaque client a des **mots-clés** (ex. « Tremblay, Lise »). Tout événement dont le titre ou le lieu contient un de ces mots est facturé à ce client. Les événements non reconnus sont listés avec un bouton **Associer** (l'app s'en souvient ensuite). Un client peut être limité à un calendrier précis. |
| Produire | Durée de l'événement × taux horaire du client ; arrondi (exact / ¼ h / ½ h), durée minimale par visite, frais de déplacement par jour, TPS/TVQ facultatives, numérotation `AAAA-001`. Une visite n'est **jamais facturée deux fois**. |
| Organiser | Onglet **Factures** : Brouillon / Envoyée / Payée, modification des lignes, notes, suppression (les visites redeviennent facturables). |
| Planifier | Onglet **À facturer** : mois dernier, ce mois-ci ou dates au choix. **Automatisation** : à partir du jour choisi (le 1ᵉʳ par défaut), à l'ouverture de l'app, les visites du mois précédent deviennent des factures brouillons, une par client, et un **rappel** mensuel est planifié. |
| Envoyer | Courriel **prérempli** (destinataires, objet, message, PDF joint) via l'app Mail. On touche *Envoyer* ou on garde en brouillon. « Envoyer les brouillons » enchaîne tous les courriels un par un. Si Mail n'a pas de compte, la feuille de partage iOS (Outlook, Gmail…) prend le relais. |
| Enregistrer dans les dossiers du téléphone | Chaque PDF est enregistré **automatiquement** dans *Fichiers › Sur mon iPhone › Mes factures › AAAA › Nom du client*. Le bouton « Enregistrer dans Fichiers… » permet aussi de choisir un autre dossier (iCloud Drive, etc.). |
| Modèle PDF | Format Lettre, en-tête avec nom/entreprise et slogan, bloc « De / Facturé à » (le payeur peut être un enfant adulte, avec la mention « Services rendus à »), bande date/échéance/période, tableau daté avec plages horaires, totaux, modalités de paiement, pied de page avec NEQ/TPS/TVQ et pagination. 4 styles de couleur. Exemples : [`docs/exemple-facture.pdf`](docs/exemple-facture.pdf) et [`docs/exemple-facture-longue.pdf`](docs/exemple-facture-longue.pdf) (générés par les tests). |

### Limite d'iOS à connaître
iOS **interdit à une app d'envoyer un courriel sans action de l'utilisateur**. L'envoi est donc « préparé à 100 % » (un seul toucher sur *Envoyer*), mais pas totalement silencieux. L'automatisation complète nécessiterait un serveur de courriel externe, ce qui n'a pas été retenu ici pour garder les données de santé/clients uniquement sur le téléphone.

## Installer sur l'iPhone

L'app n'est pas dans l'App Store. Trois façons de l'installer :

1. **Avec un Mac et Xcode (gratuit)** : ouvrir `MesFactures.xcodeproj` (ou lancer `xcodegen generate`), choisir son compte Apple dans *Signing & Capabilities*, brancher l'iPhone, ▶︎. Avec un compte gratuit, l'app doit être réinstallée tous les 7 jours.
2. **Sans Mac (Windows)** : télécharger `MesFactures-non-signee.ipa` (artefact de l'onglet *Actions* du dépôt, exécution « Mes factures (iOS) ») et l'installer avec **Sideloadly** ou **AltStore** et un Apple ID gratuit (même limite de 7 jours).
3. **Durable** : compte Apple Developer (≈ 135 $/an) → TestFlight, valide 90 jours et se renouvelle sans câble.

Au premier lancement, accepter l'accès au calendrier (« Accès complet »), puis :
1. **Réglages** : coordonnées, adresse Interac/instructions de paiement, taxes si applicable, style du PDF (bouton « Voir un exemple »).
2. **Clients** : nom, courriel de facturation, mots-clés du calendrier, taux horaire.
3. **À facturer** : choisir la période, décocher ce qui ne doit pas être facturé, *Créer la facture* ou *Tout créer*.
4. **Factures** : ouvrir, vérifier, *Envoyer par courriel*.

Astuce : nommer les rendez-vous « Tremblay – épicerie » ; le nom du client est retiré et « épicerie » devient le détail de la ligne (« Accompagnement – épicerie »).

## Développement

```
Sources/Core   modèles, formats français, calcul et association des événements (sans UIKit)
Sources/App    SwiftUI, EventKit, rendu PDF (UIGraphicsPDFRenderer), Mail, Fichiers, rappels
Tests          XCTest : association, arrondis, totaux, formats, numérotation, PDF multi-pages
project.yml    projet XcodeGen
```

Le workflow `.github/workflows/factures-ios.yml` (runner macOS) génère le projet, exécute les tests sur simulateur iPhone 16, compile l'app pour iPhone (non signée), puis publie les PDF d'exemple et le projet Xcode.

Les données (clients, factures, réglages) sont un fichier JSON local ; **Réglages › Exporter une sauvegarde** crée une copie à garder dans iCloud Drive.
