# Citiz France — carte interactive dans Microsoft Fabric

Deux modes de lecture : **Vue simple** (indicateurs essentiels, carte et priorites) et **Analyse complete** (decomposition du score, qualite, poids, penalites, sources et tableaux). Le bouton change de mode sans modifier le scenario. Le cadrage des cartes suit automatiquement le territoire filtre. Les centres locaux a 400 m ou moins des stations Citiz connues sont exclus des propositions.

Python natif, sans Spark. Fichiers de travail et sorties nationales en **CSV UTF-8**, sans Parquet. Carte de chaleur, zoom, couches, fiches au clic, filtres géographiques et recalcul des poids en Python.

Pour reprendre le projet depuis Git : [installation et developpement](docs/developpement.md). Pour comprendre ce qui est observe, estime ou manquant : [provenance et limites des donnees](docs/provenance.md).

Le dossier [presentation](presentation/) accueillera le support PowerPoint du projet.

## Utilisation

Ouvrir `notebooks/citiz_france.ipynb` dans un notebook Fabric **Python**. Dépendances : `requirements-france.txt`. Exécuter la préparation puis l'interface. Une session active est nécessaire pour recalculer. Navigation : **Cartes**, **Parametres**, **Analyse** et **Usages et sources**. Perimetre actif : France metropolitaine hors Corse.

La vue France classe des **communes à étudier**. Les marqueurs ne sont pas des places de stationnement et aucun gain de couverture n'est attribué à une commune entière. Choisir un département puis **Détail 200 m** pour calculer des candidats locaux. Les gains marginaux portent sur les habitants du département, sans double comptage ; frontières, stationnement et chemins piétons restent à vérifier. Rayon de 400 m à vol d'oiseau.

Le perimetre actif est limite aux 12 regions metropolitaines, hors Corse. Les communes, filtres, classements, nouvelles grilles et exports actifs excluent les territoires ultramarins. Les effectifs du traitement sont enregistres dans `scope.json` avec le perimetre. Les archives brutes nationales et les anciennes partitions restent des archives : elles ne sont pas utilisees par la vue metropolitaine. Les carreaux multicommunaux ne sont pas repartis arbitrairement et certains codes anciens restent non raccordes. Les arrondissements de Paris, Lyon et Marseille sont raccordes a leur commune mere.

## Aucun montant financier supposé

**Budget, coût par site et horizon sont vides par défaut.** Le classement des besoins reste calculable. Aucune sélection financière ni pénalité chiffrée sans montants, horizon commun et références renseignées. Une référence peut être un budget validé, un devis Citiz, un tarif ou un document identifié ; sa saisie reste à vérifier, le programme ne certifie pas le document.

Les poids sont des paramètres heuristiques, pas des montants estimés. Le coefficient de pénalité s'applique au ratio coût/budget documenté. Les coûts doivent couvrir le même horizon. Le budget est fourni par l'utilisateur, jamais déduit de la population ni inventé. Sans données financières documentées, les champs monétaires et la pénalité sont manquants, pas nuls.

Coûts locaux facultatifs : `commune_cost_overrides.csv` (`commune_code,cost_total_eur,source`) ou `site_cost_overrides.csv` (`candidate_id,cost_total_eur,source`). Un coût manquant est exclu de la sélection financière. Les montants des tests sont **synthétiques et limités aux tests**.

## Signaux et limites

- Permis B observés dans l'enquête EMP2019, puis **cible locale estimée**. Le RP2022 fournit une motorisation communale appliquée aux carreaux, pas un registre actuel des permis ni une observation locale de la disponibilité réelle d'un véhicule.
- Aucun bonus rural. Priorité à une cible substantielle éloignée des arrêts, hors couverture Citiz ; coûts documentés lorsqu'ils existent.
- Bonus expérimental **25–39 ans**, plafonné à 5 points et désactivable. Les données ne décrivent pas exactement 25–35 ans.
- Quatre poids principaux normalisés sur 95 points. Vue nationale : volumes `x/(x+ancre)`, avec ancres heuristiques de 1000 adultes estimés avec permis sans véhicule hors Citiz, 500 de ces adultes éloignés des arrêts, 10000 habitants hors Citiz. Cible et population sont multipliées par la part de cible éloignée des arrêts ; social et âge aussi, avec atténuation quand la cible compte moins de 200 adultes. Une pénalité ajustable de 35 points au maximum réduit les zones déjà proches des TC. Ces paramètres sont des choix de modèle, sans exclusion d'une ville. Ce n'est pas une probabilité de réservation ou une preuve de rentabilité.
- Carte : centres des 250 territoires de score calculable les plus élevés, zero inclus. Couleurs à seuils fixes : bleu 0–<20, jaune 20–<40, orange 40–<60, rouge 60–100 ; gris pour les données insuffisantes, contour vert pour une sélection financée. La chaleur combine cible éloignée des arrêts et score ; son intensité est relative au périmètre affiché.
- TC national : **proximité des arrêts publiés**, pas fréquences, soirée ou week-end. Inventaire PAN expérimental, potentiellement ancien ou incomplet. Coordonnées dédoublonnées pour la proximité. Un arrêt non recensé ne prouve pas une absence de transport.
- Population Filosofi2021, ménages RP2022 et population légale de l'API identifiables séparément. Scores communaux et locaux à des échelles différentes, sans comparaison directe.
- Sélection gloutonne locale sans garantie d'optimum global.

## Fichiers et publication

`src/citiz_france.py` prépare les données par morceaux et les grilles CSV par département. `src/france_interactive.py` fournit l'interface et les callbacks Python. `src/france_fabric_files.py` publie dans OneLake : Gold `Files/citiz_france/output`, `/code`, `/scenarios` ; Silver `Files/citiz_france/cells` ; archives publiques Bronze `Files/citiz_france/raw`.

Le bouton d'export écrit classement et sélection CSV, paramètres JSON et carte HTML. L'HTML conserve le scénario et l'exploration ; les recalculs Python nécessitent le notebook.

Le rapport Power BI V1 existant est un **ancien prototype lyonnais avec hypothèses financières non validées**, pas le résultat national actuel. Les vues nationales Décision et Analyse sont dans le notebook Fabric. Aucune nouvelle table Delta nationale ; CSV disponibles pour un modèle Power BI en import.

`src/citiz_v1.py` conserve le moteur local et l'exemple GTFS. Ses paramètres financiers n'ont plus de valeurs par défaut. Tests dans `tests/test_france.py` et `tests/test_scoring.py`.

## Sources

- [INSEE Filosofi2021 200 m](https://www.insee.fr/fr/statistiques/8735162)
- [INSEE RP2022 Logement IRIS](https://www.insee.fr/fr/statistiques/8647012)
- [API Découpage administratif](https://geo.api.gouv.fr/decoupage-administratif/communes)
- [Arrêts nationaux PAN](https://www.data.gouv.fr/datasets/arrets-de-transport-en-france)
- [Catalogue PAN](https://transport.data.gouv.fr/api/datasets)
- [Catalogue GBFS MobilityData](https://github.com/MobilityData/gbfs/blob/master/systems.csv), flux Citiz référencés par réseau dans les sources exportées
- [OpenStreetMap](https://www.openstreetmap.org/copyright)
- [Widgets Fabric](https://learn.microsoft.com/fabric/data-engineering/author-execute-notebook#ipython-widgets)

Les PDF fournis servent au cadrage, pas de sources de prix. Dates et sources exportées. Aucun budget attribué à Citiz sans document.

## Cible permis et véhicule disponible

Le critère central utilise désormais le croisement **permis B obtenu / aucun véhicule léger disponible** de l'[enquête EMP2019 du SDES](https://www.statistiques.developpement-durable.gouv.fr/resultats-detailles-de-lenquete-mobilite-des-personnes-de-2019), variables `BPERMIS` et `JNBVEH`. Les poids d'enquête produisent des profils régionaux (repli national signalé lorsque l'échantillon régional est insuffisant). Ils servent à estimer la cible locale à partir de la motorisation des ménages ; ce n'est pas un registre géographique actuel de permis. Les DROM sont hors champ de l'enquête et conservent un statut manquant sur ce critère. Aucun permis n'est déduit uniquement de l'âge.

La carte est rendue comme sortie HTML native du notebook ; les widgets pilotent le recalcul Python et l'actualisation de cette sortie. Voir [architecture_france.md](docs/architecture_france.md) pour le rôle et le chemin de chaque couche Bronze, Argent et Or.

## Usages, enquetes et suivi

L'onglet **Usages · enquetes et suivi** presente les constats ADEME/6t 2022 et 2025, les resultats locaux de la consultation Citiz d'Orleans et les usages decrits par Citiz, avec leurs sources et limites. Aucun pourcentage national ou local n'est applique automatiquement aux communes. Le besoin occasionnel et les motivations ne sont pas presentes comme des observations locales.

La vue **Solidite des donnees** distingue les estimations/proxys a valider des donnees insuffisantes. Elle ne fournit pas de probabilite de precision et ne modifie pas les priorites. Le classement TC existant conserve ses parametres, sans bonus rural ni exclusion d'une ville par son nom.

Les calculs d'activation a 30 jours, reutilisation a 90 jours, demande non satisfaite, reservations par vehicule-jour, deplacements rendus possibles et demotorisation au suivi sont prets a lire des **agregats sources**. Les KPI restent vides tant que ces donnees ne sont pas fournies. Modeles CSV et questionnaire local prepares, sans envoi d'enquete. Contrats, formules, cohortes et chemins dans [usages_metriques.md](docs/usages_metriques.md).

Les sessions Fabric restaurent les CSV depuis OneLake ; les grilles departementales sont chargees a la demande. Les archives publiques d'enquete sont en Bronze, les constats et imports prepares en Argent, les metriques et modeles de collecte en Or.

La collecte publique contient maintenant **29 chiffres verifies issus de six documents**, dont les motivations ADEME/6t (effectifs preserves), des bilans d'utilisation Citiz, la consultation d'Orleans et la satisfaction Citiz. Export `citiz_fr_usages_publics.csv`, avec periode, perimetre et source sur chaque ligne. Les observations historiques restent distinctes des six KPI necessitant des donnees internes. Voir [collecte_publique.md](docs/collecte_publique.md).

La vue **Cartes** est allegee : cinq cartes distinctes (priorites, permis sans vehicule, eloignement des arrets, couverture Citiz, solidite des donnees), sans tableau au-dessus. **Analyse** et **Usages et sources** remplacent la carte par leurs tableaux. Les filtres sont communs et le changement de carte reutilise le classement calcule. Definitions et limites dans [cartes.md](docs/cartes.md).
