# Deux pages Power BI sur un moteur commun

## Modèle

Créer un modèle sémantique depuis `lh_gold`, tables préfixées `citiz_v1_`.
La table `citiz_v1_commune_kpis` a une ligne par commune ; relier `commune_code` en 1→* vers `citiz_v1_candidates`, `citiz_v1_selection` et `citiz_v1_coverage_cells`. Filtrage simple depuis la dimension. Conserver les stations et sources comme tables de diagnostic indépendantes.

Les champs géographiques sont `latitude` et `longitude`, catégories Latitude/Longitude, **Ne pas résumer**. Ajouter `candidate_id` comme identifiant de détail pour préserver les sites.

## Page Décision

- Azure Maps : carte de chaleur pondérée par `need_heat_weight`, latitude/longitude de `citiz_v1_coverage_cells`.
- Deuxième carte ou couche dédiée : points `citiz_v1_selection`, taille `new_population`, info-bulle commune, score marginal, coût, bonus d'âge et pénalité.
- Cartes KPI : nombre de stations sélectionnées, somme de `new_population`, somme de `cost_total_eur`.
- Tableau : `selection_order`, commune, score, habitants supplémentaires, ménages sans voiture (proxy), coût supposé et points à vérifier.
- Slicer commune et bouton de navigation vers Analyse.

La sélection est pré-calculée globalement : filtrer une commune ne relance pas l'optimisation dans cette commune. Changer un budget, un coût ou un bonus dans Python, recalculer et actualiser le modèle. Ne pas présenter un slicer comme un moteur Python temps réel.

## Page Analyse

- Tableau détaillé des candidats et composantes du score.
- Nuage de points coût total / habitants nouvellement proches, taille selon le proxy de ménages sans voiture.
- Distribution du déficit TC et comparaison couverture avant/après.
- Table des dates de service, données manquantes, imputations INSEE et sources.
- Afficher le scénario de coût et le proxy d'âge 25–39 sans les confondre avec des observations.

## Mesures DAX de départ

```dax
Habitants = SUM(citiz_v1_commune_kpis[population])
Habitants proches de Citiz = SUM(citiz_v1_commune_kpis[population_covered])
Habitants supplementaires = SUM(citiz_v1_selection[new_population])
Cout scenario = SUM(citiz_v1_selection[cost_total_eur])
Stations proposees = COUNTROWS(citiz_v1_selection)
Couverture actuelle = DIVIDE([Habitants proches de Citiz], [Habitants])
Cout par habitant supplementaire = DIVIDE([Cout scenario], [Habitants supplementaires])
```

Les populations de plusieurs stations existantes peuvent se chevaucher : ne pas additionner leurs `nearby_population`. Utiliser les carreaux ou les KPI communaux pour les totaux uniques.

## Ressources creees dans Fabric

- Modele semantique : [Citiz V1 - Decision et Analyse](https://app.fabric.microsoft.com/groups/0532a204-3933-4804-9064-1224447ebbb3/modeling/fc05e1ee-4d3d-48a4-a03f-c807c6e951b2/modelView?experience=fabric-developer).
- Notebook execute : [nb_01_bronze_ingestion](https://app.fabric.microsoft.com/groups/0532a204-3933-4804-9064-1224447ebbb3/synapsenotebooks/4f7343ea-2f15-44be-97d3-79b6aa2e44a5?experience=fabric-developer).
- Code et notebook portable dans `lh_gold/Files/citiz_v1/code`.

Validation du premier calcul : 7 880 carreaux, 200 stations existantes, 7 418 secteurs candidats ; scenario de quatre stations, 244 000 EUR supposes sur trois ans et 11 954 habitants nouvellement proches (rayon aerien 400 m). Ne pas interpreter ce dernier chiffre comme des clients prevus.

Rapport enregistre : [Citiz V1 - Carte des besoins et analyse](https://app.fabric.microsoft.com/groups/0532a204-3933-4804-9064-1224447ebbb3/reports/0a9e319c-d397-4c97-9b32-a951d19d7d5d/349a449eac9628389cf8?experience=fabric-developer). Deux pages : Decision (Azure Maps, chaleur ponderee, coordonnees non agregees) et Analyse (candidats, rang croissant, composantes, couts, totaux desactives). Canevas 1280 x 720. Les selections sous budget sont detaillees dans le notebook et la table Gold dediee.
