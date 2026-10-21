# Usages, enquetes et metriques

Le module `mobility_metrics.py` distingue les constats d'enquete, les estimations locales, les proxys et les observations operationnelles. Les constats ADEME couvrent plusieurs operateurs : ils ne sont pas tous propres a Citiz. La consultation d'Orleans concerne 154 repondants volontaires et des intentions. Aucun taux de cette consultation n'est extrapole aux communes francaises. Les references et leurs limites sont consultables dans l'onglet **Usages · enquetes et suivi** du notebook.

La carte **Solidite des donnees** utilise le violet pour les modeles/proxys a valider et le gris pour les donnees insuffisantes. Ce statut n'est pas une probabilite de precision. Aucune note artificielle de confiance sur 100 n'est attribuee. La part de carreaux imputes compte des carreaux, pas leur population. Le besoin occasionnel, les frequences TC et les parcours pietons ne sont pas encore observes. Le classement de besoin TC conserve ses poids ; aucune correlation d'enquete n'est convertie automatiquement en coefficient.

## Couches Fabric

- Bronze `Files/citiz_france/raw/enquetes` : pages publiques et PDF d'origine, sans formulaire ni inscription. Un manifeste contient URL, date de recuperation et empreinte SHA256. La notice de l'ENA2025 n'est pas presentee comme le rapport integral.
- Bronze `Files/citiz_france/inputs` : donnees agregees sources deposees par l'equipe. Aucun identifiant individuel n'est requis.
- Argent `Files/citiz_france/prepared` : references, constats d'enquete prepares et imports d'agregats valides.
- Or `Files/citiz_france/output` : catalogue des indicateurs, KPI calcules et resultats d'enquete locale. Les donnees absentes restent vides, avec statut `a_collecter`.
- Or `Files/citiz_france/templates` : modeles CSV vides et questionnaire prepare. Aucune enquete n'est envoyee.

## Import KPI agreges

Copier le modele `kpi_agreges.csv`, le remplir avec des agregats sources et le deposer dans Bronze `inputs`. Relancer les cellules du notebook. Hors Fabric, deposer dans `<workdir>/inputs`. Ne pas ajouter de colonne personnelle ; les colonnes inattendues sont refusees.

Colonnes exactes :

```text
commune_code,period_start,period_end,metric,numerator,denominator,source,definition_version
```

Le code INSEE reste un texte de cinq caracteres (avec zero initial). Dates ISO. Une seule ligne par commune, periode et metrique. `definition_version=v1`. Les effectifs et expositions doivent etre positifs ou nuls et finis. Une source est obligatoire. Un denominateur nul produit un resultat non calculable ; un resultat reel nul exige un denominateur positif.

| Metrique | Numerateur | Denominateur | Sortie |
|---|---|---|---|
| `activation_30d` | Inscrits de la cohorte ayant une premiere reservation realisee sous 30 jours | Inscrits de la cohorte ayant tous 30 jours de recul | % |
| `reuse_90d` | Premiers utilisateurs ayant une autre reservation realisee dans les 90 jours | Premiers utilisateurs ayant tous 90 jours de recul | % |
| `unmet_search_rate` | Recherches qualifiees sans vehicule compatible | Recherches qualifiees dedoublonnees | % |
| `bookings_per_vehicle_day` | Reservations realisees | Somme des jours de service des vehicules sur la periode | reservations/vehicule-jour |
| `mobility_enabled` | Repondants declarant un trajet auquel ils auraient renonce sans le service | Repondants a cette question | % declaratif |
| `demotorization_followup` | Menages suivis dont le nombre de voitures disponibles a diminue | Menages avec observations avant/apres comparables | % declaratif, non causal |

Les fenetres 30/90 jours sont un choix de protocole. Le producteur des agregats doit assurer le recul complet, le dedoublonnage, la coherence des periodes et l'affectation geographique (domicile des usagers pour cohortes, commune de station pour reservations). Ces conditions ne peuvent pas etre certifiees a partir des seuls compteurs. `source` doit identifier l'extraction et ces conventions. Les KPI ne sont pas deduits des flux GBFS. Ne pas additionner des taux ni fusionner des periodes chevauchantes.

## Import d'enquete locale

Colonnes exactes de `enquete_agregee.csv` :

```text
commune_code,motif,n_reponses,n_eligibles,date_debut,date_fin,source
```

`n_eligibles` designe les repondants eligibles ayant repondu a la question correspondante, et non tous les habitants. Les non-reponses sont exclues du denominateur et doivent etre documentees dans la source. Le questionnaire distingue permis, disponibilite effective d'un vehicule, frequence, motifs, creneaux, solution actuelle, marche acceptable et freins. Plusieurs motifs sont possibles : la somme de leurs parts peut depasser 100 %. Les reponses sont declaratives ; aucun intervalle representatif ni conversion en reservations n'est affirme sans protocole d'echantillonnage adapte.

Les motifs acceptes sont dans le questionnaire exporte. Inclure des non-usagers et des personnes ayant le permis mais un vehicule seulement parfois disponible. Aucun numero de permis, adresse precise ni contact n'est necessaire aux imports. Le dispositif n'envoie aucun message ni formulaire.

## Reprise de session

Le notebook restaure les CSV prepares depuis OneLake au redemarrage. Les grilles departementales sont chargees a la demande. Les sources brutes et les resultats restent dans leurs couches ; les dossiers temporaires du noyau ne sont pas l'unique stockage.
