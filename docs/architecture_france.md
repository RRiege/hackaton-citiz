# Bronze → Argent → Or dans Microsoft Fabric

Tous les traitements nationaux utilisent Python natif. Les sorties de travail sont des CSV UTF-8. Les archives brutes conservent leur format d'origine.

| Couche | Lakehouse / dossier | Contenu et rôle |
|---|---|---|
| Bronze | `lh_bronze/Files/citiz_france/raw` | Archives INSEE, EMP2019, dictionnaire, catalogues, arrêts et réponses GBFS brutes. Aucun score. |
| Bronze | `lh_bronze/Files/citiz_france/metadata` | `sources_manifest.csv` : URL, état, date de récupération. |
| Argent | `lh_silver/Files/citiz_france/cells/<département>` | Carreaux habités nettoyés, coordonnées, motorisation, proximité des arrêts et couverture géographique. Aucun budget ni score de décision. |
| Argent | `lh_silver/Files/citiz_france/prepared` | Communes enrichies, stations dédoublonnées, qualité du raccordement, profils statistiques de permis. |
| Or | `lh_gold/Files/citiz_france/output` | Classement communal, composantes du score, sources et qualité pour consultation, profils agrégés, paramètres JSON et carte HTML du scénario. |
| Or | `lh_gold/Files/citiz_france/scenarios` | Exports de chaque scénario : classement, sélection, paramètres et carte. |
| Code | `lh_gold/Files/citiz_france/code` | Copie de sauvegarde des sources et du notebook. Les programmes ne sont pas des données métier. |

`acquire_france` assure l'acquisition Bronze. `prepare_france` prépare les grilles ; `attach_license_profile` calcule le croisement statistique permis/véhicule en Argent. `france_rank` et le moteur local calculent les indicateurs de décision Or. `publish_france_files` répartit les sorties entre les trois Lakehouses existants et écrit un manifeste de publication.

Un fichier Argent contient des faits nettoyés ou des variables préparées, jamais une décision budgétaire. Un fichier Or peut contenir une reprise de faits Argent pour la lecture BI, accompagnée de l'origine et des limites. Les sources ne sont pas réécrites pour faire correspondre un scénario.

Le notebook **Citiz France - Carte interactive et scenarios Python** orchestre les trois étapes. Les anciens scripts lyonnais y ont été neutralisés. L'ancien rapport Power BI V1 reste une archive distincte et ne représente pas le résultat national.

## Permis de conduire

EMP2019 (SDES) : `BPERMIS=1` désigne la possession du permis B ; `JNBVEH=0` l'absence de voiture particulière, VUL et camping-car disponibles. Le croisement est réalisé dans l'enquête anonyme, avec poids d'individu Kish et poids de ménage. Seuls des profils agrégés sont publiés en Argent/Or.

Le ratio d'adultes titulaires du permis sans véhicule disponible par ménage sans véhicule est calculé régionalement lorsque l'échantillon dépasse 50 ménages et l'effectif pondéré effectif 30, avec moins de 5 % de poids adulte sans réponse au permis. Ce sont des seuils heuristiques de prudence, pas une garantie de précision. Sinon, repli national métropolitain identifié. Le profil est appliqué aux ménages sans voiture estimés localement ; cette répartition locale est un **modèle**, pas un dénombrement observé. L'écart de définition entre RP2022 (voiture) et EMP2019 (véhicules légers disponibles) reste une limite. Les DROM sont hors champ EMP : aucune extrapolation métropolitaine présentée comme observation locale.

Sans budget, coûts, horizon et références, le besoin reste calculable mais la sélection financière reste désactivée. Les fichiers ne remplacent jamais un montant absent par un coût nul.

## Priorité de besoin et carte

Le score Or utilise la cible permis sans véhicule hors Citiz et sa part éloignée des arrêts publiés : éloignement nul à 400 m ou moins, maximal à 800 m ou plus, progression linéaire entre les deux. Ce proxy ne mesure ni fréquence ni amplitude horaire. Les composantes population/cible sont atténuées par cet éloignement ; le social et l'âge aussi, et par le volume de cible. Une pénalité ajustable de proximité des TC (35 points maximum par défaut) s'applique avant la pénalité financière éventuelle. Les poids et ancres sont des paramètres heuristiques explicites. Paris n'est pas exclue par son nom ; toutes les communes utilisent la même règle, sans bonus rural.

Les points des territoires suivent des seuils fixes de score : bleu sous 20, ambre de 20 à moins de 40, orange de 40 à moins de 60, orange fonce à partir de 60. Un rond gris creux indique des données insuffisantes. Un contour vert signale une sélection sous budget documenté. La carte affiche les centres des 250 premiers scores calculables, zero inclus, et la chaleur de la cible éloignée des TC hors Citiz. Ces points ne sont pas des emplacements de station validés.

## Enquetes et metriques d'usage

Les archives d'enquetes accessibles publiquement sont conservees en Bronze `raw/enquetes`, avec leur manifeste dans `metadata`. Les constats prepares et leurs references sont en Argent `prepared`. Les agregats locaux, s'ils sont deposes par l'equipe, arrivent en Bronze `inputs`, sont valides puis prepares en Argent. Les resultats et le catalogue de metriques sont en Or `output`, les modeles de collecte en Or `templates`. Voir [usages_metriques.md](usages_metriques.md) pour les schemas exacts. Aucune reponse individuelle ni donnee synthetique n'est necessaire a la demonstration publiee.

Le statut de solidite reste descriptif : donnees insuffisantes ou modele/proxy non valide localement. Les carreaux imputes sont signales sans convertir leur proportion en intervalle de confiance invente. Aucune prediction de reservations n'est annoncee a partir du seul score TC.

## Perimetre actif metropolitain

`run_france` applique `study_scope` apres la reprise d un ancien cache et avant les exports courants : 12 regions metropolitaines, hors Corse. Une reconstruction des grilles filtre les codes communes avant les calculs. Les anciennes partitions ultramarines ne sont pas utilisees par le moteur local, qui accepte uniquement les departements metropolitains hors Corse. `scope.json` decrit le perimetre et les effectifs. L audit de raccordement des archives historiques peut garder un perimetre national ; il ne represente pas un total de communes actives. Les flux de stations Citiz francais sont filtres sur l emprise metropolitaine pour retirer les coordonnees ultramarines ; ce filtre n est pas un raccordement administratif des stations.
