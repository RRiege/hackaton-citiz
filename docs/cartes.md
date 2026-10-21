# Cartes et navigation Fabric

Les commandes sont alignees sur trois colonnes communes : Region / Carte, Departement / Echelle, Commune / actions. Les descriptions occupent 76 px et les lignes ont la meme hauteur ; les colonnes se replient sur un ecran etroit.

Analyse complete contient sept tables : classement detaille, decomposition des points et penalites, comparaison des regions, comparaison des departements, distribution des scores, completude et inventaire des sources. Les entetes regroupent les variables par domaine. Les deux classements affichent 50 lignes, les autres tables au plus 120 ; les CSV exportent toutes les lignes. Les comparaisons utilisent la population renseignee et des medianes/maxima de scores, jamais une somme de scores. En detail local, les totaux proviennent des carreaux dedoublonnes, pas des rayons des candidats qui se recouvrent. Les colonnes de cout ne sont ajoutees a la decomposition que lorsque des couts sont documentes.

Les sept CSV `citiz_fr_analyse_*.csv` sont publies dans la couche Or. Un export de scenario ajoute les sept tables `analyse_*.csv` correspondant aux filtres et poids courants. Aucune frequence, reservation ou disponibilite de vehicule n'est deduite de ces tableaux.

L'interface partage une seule charte : filtres alignes, surfaces blanches, accent vert petrol et fond de carte desature pour faire ressortir les donnees. Les couches sont repliees par defaut, mais restent accessibles. Trois indicateurs couvrent le besoin permis sans vehicule, l'eloignement des arrets et la population proche du Citiz connu. Les pourcentages sont ponderes par la population renseignee, les manquants ne sont pas remplaces par zero. En detail, les indicateurs utilisent les carreaux, jamais la somme des rayons de candidats qui se recouvrent.

Le volet contextuel presente les priorites, le volume de population etudie, le statut des horaires/frequences et les sources repliees. Aucune disponibilite de vehicule ou frequence de transport n'est inventee. Les tableaux et formulaires detailles suivent la meme charte en Analyse complete. L'echelle 200 m devient disponible apres le choix d'un departement.

Les messages techniques de reprise, de validation et de publication sont journalises dans `lh_gold/Files/citiz_france/diagnostics/`, sans sortie texte autour du tableau de bord. Les exceptions ne sont pas masquees. La vue simple presente la population eloignee de plus de 400 m des arrets publies (part ponderee par la population connue), sans pretendre mesurer les frequences ou les horaires. L'export CSV reste disponible dans Analyse complete ; les badges de diagnostic et le bouton de recentrage redondant sont retires.

Le bouton **Vue simple / Analyse complete** change l'habillage sans recalculer ni modifier le scenario. La vue simple presente trois indicateurs, la carte et les priorites a examiner ; aucune table de donnees n'est placee au-dessus de la carte. L'analyse complete ajoute la decomposition des scores et les controles de qualite, ainsi que les onglets Cartes, Parametres, Analyse et Usages et sources. Parametres expose les poids, les penalites, les couts et leurs sources. Analyse contient les tableaux detailles. Le retour en vue simple revient automatiquement a la carte.

Les cinq cartes se cadrent sur les coordonnees du perimetre filtre, y compris la France entiere. Le cadrage est reapplique apres le rendu Fabric ; le zoom manuel reste ensuite disponible. Le panneau de lecture est a droite de la carte et passe en dessous sur un ecran etroit. Les legendes internes sont repliables pour laisser la carte lisible. Une exportation de scenario conserve aussi l'habillage HTML et le mode choisi. Il s'agit d'une interface BI dans le notebook Fabric, pas d'un nouveau rapport Power BI.

La vue principale affiche les filtres, le choix de carte et la carte interactive. Les tableaux sont exclusivement dans Analyse ou Usages et sources : la sortie HTML est remplacee lorsque l'on change d'onglet, sans laisser une carte au-dessous d'un long tableau.

Cinq cartes utilisent les memes filtres France metropolitaine, region, departement et commune. La Corse et les territoires ultramarins sont exclus du perimetre actif :

| Carte | Variable representee | Limite |
| --- | --- | --- |
| Priorites d'implantation | Score de besoin du scenario /100 | Pre-evaluation, pas decision d'implantation ou probabilite de reservation |
| Permis et absence de vehicule | Personnes estimees avec permis B et aucun vehicule disponible, hors couverture Citiz | EMP2019 et RP2022 ; estimations, pas un registre local |
| Eloignement des arrets | Population a plus de 400 m a vol d'oiseau d'un arret publie / population de grille | Population Filosofi2021 ; inventaire PAN potentiellement incomplet, sans horaires ni frequences |
| Couverture Citiz | Population a moins de 400 m a vol d'oiseau d'une station connue / population de grille | Inventaire Citiz potentiellement incomplet, pas disponibilite instantanee ou acces pieton reel |
| Solidite des donnees | Estimations/proxys a valider ou donnees insuffisantes | Aucun score de certitude invente |

La carte des arrets est descriptive et independante des permis ou de la couverture Citiz. Elle ne represente pas la variable de manque TC du classement : celle-ci conserve son attenuateur de 400 a 800 m et sa ponderation par la cible hors Citiz. Au niveau 200 m, la carte Arrets utilise la distance du centre du carreau : 0 ou 100 %, et la carte Couverture Citiz indique la proximite du centre du carreau.

Les legendes ont des seuils fixes. La chaleur de cible utilise toutes les lignes connues et une intensite relative au perimetre. Les cartes descriptives limitent les points a 600 lignes : plus grandes cibles pour Permis, plus grandes populations pour Arrets et Citiz. Filtrer un departement ou une commune permet d'explorer les autres territoires. Les valeurs manquantes restent grises ; elles ne sont pas remplacees par zero. La carte Priorites conserve ses 250 scores calculables les plus eleves, zero inclus.

Changer de carte ne recalcule pas le classement, ne change aucun poids et ne recharge pas les donnees. Les cartes deja construites sont gardees en memoire pour le scenario courant ; modifier les filtres ou les parametres invalide ce cache. Les fiches, les couches, le plein ecran et les raccourcis Metropole sont disponibles sur chaque carte.

Le notebook publie `carte_france.html` et quatre variantes `carte_france_target.html`, `carte_france_transit.html`, `carte_france_citiz.html`, `carte_france_evidence.html` dans `lh_gold/Files/citiz_france/output`. L'export d'un scenario conserve la carte affichee, les cartes deja consultees, les parametres et les CSV. Les recalculs necessitent le notebook Python ; les HTML exportes conservent l'exploration du scenario enregistre.

Un perimetre sans valeur exploitable et geolocalisee affiche un message explicite a la place d un fond de carte vide. Le bouton Reinitialiser les filtres restaure la metropole hors Corse. Une session Python active reste necessaire aux callbacks et recalculs ; apres expiration de la session Fabric, relancer le notebook.

La chaleur utilise une transformation log(1 + volume), rapportee au 99e percentile positif du perimetre, plafonnee a 1 puis elevee a la puissance 1,35 pour renforcer le contraste visuel. Les zeros et manquants ne generent aucune chaleur. Le reglage de zoom de Leaflet est calibre a 5 pour la France et 9 pour le detail, afin de ne pas attenuer artificiellement toutes les valeurs au zoom national. Bleu, cyan clair et corail expriment une concentration relative avec accumulation des voisins ; ils ne correspondent pas aux seuils de score des points et ne sont pas comparables entre perimetres differents.

Les stations connues sont visibles sur Priorites sous forme de badges C bleu marine, regroupes au dezoom avec leur effectif. Le detail 200 m exclut tout centre a 400 m ou moins d'une station connue, y compris si ses voisins ont un besoin non couvert. La distance est recalculee depuis l'inventaire courant et exportee avec le seuil d'exclusion. Une distance inconnue ne permet pas de proposer le centre. Les habitants deja couverts restent exclus des gains. Une commune disposant de stations reste etudiee pour ses quartiers non couverts : le point national est un territoire, pas une adresse proposee. Le seuil de 400 m est heuristique, a vol d'oiseau, et l'inventaire peut etre incomplet.

## Code couleur et marqueurs

La palette distingue la concentration du besoin (degrade bleu `#2e8eb7` vers corail `#f15f63`) du potentiel d'implantation (orange `#ff9148`, puis orange fonce `#b95518`). Le corail ne represente pas une densite demographique brute : la chaleur Priorites combine la cible eloignee des arrets et le score ; la chaleur Permis represente la cible estimee. Ces deux concentrations restent relatives au perimetre. Aucun score ni aucune donnee source ne change.

Les points de priorite ont un contour blanc, une ombre legere et une taille graduee selon les quatre classes. Les points eleves sont dessines en dernier. Le survol renforce le contour ; aucune animation ne simule une evolution temporelle des donnees. Les stations existantes utilisent des badges C bleu marine pour eviter la confusion avec les ronds de besoin. Les manquants sont des ronds gris creux, distincts d'une faible valeur. La vue Solidite reste violette.

Les seuils de priorite restent fixes : faible 0 a <20 (bleu), moderee 20 a <40 (ambre), elevee 40 a <60 (orange), tres elevee 60 a 100 (orange fonce). La barre de concentration bleu-corail et les symboles sont visibles au-dessus de la carte ; les seuils detailles restent accessibles dans la legende interne.
