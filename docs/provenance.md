# Provenance et limites des donnees

Le projet est un outil de **pre-evaluation**, pas une validation d'implantation ni une prediction de reservations. Une source publique identifiee ne garantit ni sa completude, ni son actualite, ni la validite d'une extrapolation locale.

| Donnee | Source / millesime | Usage | Limite principale |
|---|---|---|---|
| Population et profils des carreaux 200 m | [INSEE Filosofi 2021](https://www.insee.fr/fr/statistiques/8735162) | Population et contexte des zones | Population statistique ancienne ; carreaux imputes et raccordements incomplets signales |
| Motorisation des menages | [INSEE RP 2022](https://www.insee.fr/fr/statistiques/8647012) | Part de menages sans voiture | Valeur communale appliquee aux carreaux ; pas observation individuelle |
| Permis B et vehicule disponible | [SDES EMP 2019](https://www.statistiques.developpement-durable.gouv.fr/resultats-detailles-de-lenquete-mobilite-des-personnes-de-2019) | Croisement BPERMIS / JNBVEH pondere | Profil regional ou repli national ; cible locale estimee, pas registre de permis |
| Communes et decoupage administratif | [API geo](https://geo.api.gouv.fr/decoupage-administratif/communes) | Codes, noms et rattachements | Le millesime doit etre rapproche de celui des autres sources |
| Arrets de transport | [Agregat national PAN](https://www.data.gouv.fr/datasets/arrets-de-transport-en-france) | Distance aux arrets publies | Inventaire experimental, non exhaustif ; ni horaires, ni frequences, ni cheminement pieton |
| Stations Citiz connues | [Catalogue PAN](https://transport.data.gouv.fr/datasets?type=vehicles-sharing&q=citiz) et [catalogue MobilityData](https://github.com/MobilityData/gbfs/blob/master/systems.csv) | Exclusion de proximite des stations connues | Couverture des flux a verifier ; presence d'une station distincte de disponibilite d'un vehicule |
| Motivations et observations d'usage | ADEME/6t, Citiz et bilans publics cites dans [la collecte](collecte_publique.md) | Contexte et comparaison descriptive | Enquetes declaratives ou bilans locaux ; pas extrapoles aux communes |
| Couts et budget | References renseignees par l'utilisateur | Penalite et selection financiere | Absents par defaut ; une reference saisie n'est pas automatiquement certifiee |

## Tracabilite disponible

- Les sources de collecte et leurs statuts sont exportes dans `sources_manifest.csv` en Bronze et `citiz_fr_sources.csv` en Or.
- Les documents d'enquete archives ont un manifeste avec URL, statut, date de recuperation et SHA256. La copie versionnee est `data/public/sources_collecte_manifest.csv`.
- Chacune des 29 observations de `data/public/usages_observations_publiques.csv` comporte sa source, son perimetre, sa periode, sa definition et ses limites. Six documents portent ces observations ; le manifeste contient aussi des references contextuelles.
- Une date de collecte ne remplace pas le millesime statistique. Les sources nationales n'ont pas toutes un SHA256 dans leur manifeste actuel.
- Les donnees brutes restent dans OneLake Bronze, les donnees preparees en Argent et les indicateurs calcules en Or. Le code et les petits releves publics sont versionnes dans Git.

## Precision restant a etablir

Le classement utilise des poids heuristiques et des distances a vol d'oiseau. Il n'a pas ete calibre sur les reservations Citiz. Les six KPI operationnels restent manquants sans donnees d'exploitation. Les horaires GTFS, les temps pietons, l'exhaustivite des stations et la faisabilite du stationnement doivent etre verifies avant une decision d'implantation.

Les tests controlent la coherence du programme et des releves ; ils ne certifient pas la realite terrain. Les droits de redistribution doivent etre verifies source par source avant d'ajouter des archives de tiers au depot. Aucun PDF tiers ni archive nationale n'est necessaire dans Git pour executer la collecte.
