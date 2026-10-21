# Collecte publique des usages Citiz et de l'autopartage

Releve verifie le 21 octobre 2026. Les 29 observations proviennent de six documents : rapport integral ADEME/6t ENA2022, synthese ADEME ENA2025, consultation Citiz Orleans, livre blanc Citiz 2026, bulletin municipal Fleurieu-sur-Saone 2024 et bilan environnemental Rovaltain 2024. URL, page PDF, periode, definition et limites figurent sur chaque ligne du CSV.

Les motivations 2022 sont des choix multiples parmi 1813 inscrits a plusieurs services d'autopartage en boucle, dont Citiz. Le rapport fournit les effectifs exacts : entretien 1504, cout 1451, ecologie 1403, stationnement 1189 et praticite face aux TC 808. Les pourcentages publies arrondis sont conserves ; ils ne sont pas additionnes en un taux global. Les 1813 inscrits comprennent 70 personnes sans utilisation dans les douze derniers mois. Les frequences mensuelles concernent les 1743 utilisateurs actifs et sont estimees depuis des classes de frequence declarees, pas extraites de reservations.

La figure 35 (declencheur d'inscription) est distincte de la figure 37 (avantages cites). Les 73,8 % sans voiture disponible concernent le menage des inscrits interroges ; cela ne remplace pas l'estimation locale permis/vehicule issue de l'EMP2019.

Fleurieu-sur-Saone (INSEE 69085) : 94 locations, 8274 km, 999 heures reservees, deux vehicules, une station et 15 clients actifs publies pour novembre 2023 a octobre 2024. Le taux publie de 0,13 location/jour/vehicule est conserve comme tel. Les jours reels de service, les indisponibilites et la definition d'un client actif sont inconnus. Aucun taux d'occupation ou KPI strict par vehicule-jour n'est reconstitue. Les dates journalieres d'export sont les bornes calendaires des mois publies, ce qui est signale dans `period_precision`.

Rovaltain : 409 reservations et 54906 km dans le bilan 2024 du parc ; la fenetre exacte de comptage n'est pas explicitee. Le parc ne correspond pas a une commune. Orleans : 154 repondants volontaires au total, pourcentages publies par question sans effectif par question. Le besoin hebdomadaire est indique « pres de 20 % » : `approximate=True`. Les intentions ne sont pas des reservations realisees. La satisfaction Citiz de 92 % concerne l'enquete 2024 citee dans le livre blanc 2026 ; son effectif n'est pas fourni. Les chiffres ADEME ENA2025 ont leur propre millesime ; ils ne sont pas fusionnes avec ceux de 2022.

Les observations nationales restent des references dans tous les filtres. Les observations communales sont visibles lorsque cette commune figure dans le perimetre ; les bilans de site/metropole peuvent etre presentes comme contexte du departement, avec leur territoire explicite. Ils ne sont pas joints aux habitants ou aux scores communaux. Aucun changement automatique des poids. Aucun montant financier introduit.

## Stockage Fabric

- Bronze : `lh_bronze/Files/citiz_france/raw/enquetes/` contient les originaux accessibles. `metadata/enquetes_sources_manifest.csv` donne URL, date de recuperation, statut et SHA256. Un echec d'archivage reste explicite ; la disponibilite via un navigateur ne garantit pas celle du serveur Fabric.
- Argent : `lh_silver/Files/citiz_france/prepared/usages_observations_publiques.csv` contient les releves controles.
- Or : `lh_gold/Files/citiz_france/output/citiz_fr_usages_publics.csv` fournit ces observations et leur provenance pour analyse/BI. Aucun Parquet.

Relancer le notebook reexporte les observations. La cellule de publication archive les documents et actualise le manifeste avant publication. Le script local `scripts/collect_usages_publics.py --workdir <dossier>` effectue aussi la collecte et les exports CSV. La copie locale des chiffres verifies se trouve dans `data/public/usages_observations_publiques.csv`.

## Ce qui necessite toujours les donnees de l'operateur

L'activation a 30 jours et la reutilisation a 90 jours demandent des cohortes integralement observees. La demande non satisfaite demande les recherches qualifiees, y compris celles sans reservation. Le ratio reservations/vehicule-jour demande les jours de service reels. Les deplacements rendus possibles et la demotorisation au suivi demandent des questions/observations comparables. Ces six KPI restent manquants sans leurs agregats ; les chiffres publics ne leur sont pas substitues.
