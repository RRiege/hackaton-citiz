"""Enquetes, indicateurs et contrats CSV. Aucun taux national extrapole localement."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import hashlib, html, json, shutil
import numpy as np
import pandas as pd

RESEARCH_SOURCES=[
    dict(source_id='ENA2025',title='ADEME - Enquete nationale autopartage edition 2025',
         url='https://librairie.ademe.fr/mobilite-et-transports/9344-enquete-nationale-autopartage-2025.html',
         publication='2026-05-07',scope='Plusieurs formes et operateurs, pas uniquement Citiz',
         evidence='Notice du rapport ; rapport integral non exploite'),
    dict(source_id='ADEME2025_SYNTHESE',title='ADEME Infos - enseignements ENA2025',
         url='https://infos.ademe.fr/mobilite-transports/2026/autopartage-jusqua-1-000-e-deconomies-par-an/',
         publication='2026-05',scope='Autopartage, dont autopartage en boucle',evidence='Synthese publique'),
    dict(source_id='ENA2022',title='ADEME - resultats de l enquete autopartage 2022',
         url='https://www.ademe.fr/presse/communique-national/enquete-nationale-autopartage-2022-impact-sur-les-pratiques-de-mobilite-des-francais/',
         publication='2022-09-22',scope='2768 reponses ; plusieurs operateurs, dont 12 reseaux Citiz',evidence='Communique de resultats'),
    dict(source_id='CITIZ_ORLEANS2025',title='Citiz - consultation Orleans et deploiement Centre-Val de Loire',
         url='https://www.citiz.coop/uploads/2025/11/citiz-RNTP-2025.pdf',publication='2025-10-20',
         scope='154 repondants volontaires locaux ; intentions declarees',evidence='Communique Citiz, page 2'),
    dict(source_id='CITIZ_USAGES',title='Citiz - livre blanc, usages multiples',
         url='https://www.citiz.coop/uploads/2026/01/Le-livre-blanc-de-l-autopartage-Citiz-12-2025.pdf',
         publication='2025-12',scope='Presentation du service ; pas classement statistique des motivations',
         evidence='Livre blanc Citiz, page 6')]

# Releve manuel controle dans les pages originales. Les valeurs publiees restent
# distinctes des KPI internes : aucun denominateur reconstitue depuis un pourcentage.
RESEARCH_SOURCES += [
    dict(source_id='ENA2022_RAPPORT',title='ADEME / 6t - rapport integral ENA2022',
         url='https://librairie.ademe.fr/ged/7353/enquete-autopartage-2022-rapport.pdf',
         publication='2022-09',scope='Boucle multioperateurs, dont Citiz ; enquete en ligne',
         evidence='Rapport integral, pages 11, 39, 43, 46, 48-49'),
    dict(source_id='FLEURIEU2024',title='Fleurieu-sur-Saone - bulletin municipal numero 49',
         url='https://www.mairie-fleurieusursaone.fr/wp-content/uploads/2024/12/Fleurieu-60p-n%C2%B049.pdf',
         publication='2024-12',scope='Une station Citiz a Fleurieu-sur-Saone, novembre 2023 a octobre 2024',
         evidence='Page PDF 12, tableau Citiz et texte municipal'),
    dict(source_id='ROVALTAIN2024',title='Valence Romans Agglo - rapport environnemental Rovaltain 2024',
         url='https://www.greendrome.fr/data/fm/Rapport_environnemental_rovaltain_2024_final_1.pdf',
         publication='2024',scope='Parc Rovaltain, pas ensemble des communes environnantes',
         evidence='Page PDF 10 ; periode precise de comptage non explicitee'),
    dict(source_id='CITIZ_LB2026',title='Citiz - livre blanc 2026',
         url='https://www.citiz.coop/uploads/2026/02/2026-CITIZ-livre_blanc.pdf',
         publication='2026-02',scope='Satisfaction reseau Citiz 2024 ; effectif non publie ici',
         evidence='Page PDF 13, page imprimee 12, note 14')]


def public_usage_observations():
    """Chiffres publics historiques : references contextuelles, jamais coefficients locaux."""
    rows=[]
    def add(metric,label,value,unit,source_id,page,kind,scope,period,definition,limitation,
            sample=np.nan,numerator=np.nan,denominator=np.nan,approx=False,**geo):
        rows.append(dict(observation_id=source_id+'__'+metric,metric=metric,indicateur=label,value=value,
                         unit=unit,source_id=source_id,page_pdf=page,nature=kind,territoire=scope,
                         periode=period,definition=definition,limitation=limitation,sample_n=sample,
                         numerator=numerator,denominator=denominator,approximate=approx,
                         commune_code=geo.get('commune_code',''),department=geo.get('department',''),
                         region=geo.get('region',''),scope_type=geo.get('scope_type','national'),
                         period_start=geo.get('period_start',''),period_end=geo.get('period_end',''),
                         period_precision=geo.get('period_precision','libelle_source'),
                         strict_operational_kpi=False,used_in_ranking=False))
    national=dict(period_start='2022-05-11',period_end='2022-06-13',period_precision='collecte_jour')
    for metric,label,pct,count in [
        ('motivation_entretien','Eviter les contraintes d entretien',83.,1504),
        ('motivation_cout','Moins cher qu une voiture personnelle',80.,1451),
        ('motivation_ecologie','Dimension ecologique',77.4,1403),
        ('motivation_stationnement','Eviter les problemes de stationnement',65.6,1189),
        ('motivation_pratique_tc','Plus pratique que les transports en commun',44.6,808)]:
        add(metric,label,pct,'%', 'ENA2022_RAPPORT',46,'enquete_declarative',
            'France - inscrits boucle, plusieurs operateurs','Collecte mai-juin 2022',
            'Element cite dans le choix d inscription ; plusieurs reponses possibles.',
            '1813 inscrits, dont 70 non-utilisateurs sur 12 mois ; non representatif des habitants de chaque commune.',
            sample=1813,numerator=count,denominator=1813,**national)
    for metric,label,pct,count in [
        ('declencheur_tc','Inscription en complement des TC',19.7,358),
        ('declencheur_remplacement','Besoin de remplacer une voiture',17.5,317),
        ('declencheur_velo','Inscription en complement du velo',13.6,246)]:
        add(metric,label,pct,'%','ENA2022_RAPPORT',43,'enquete_declarative',
            'France - inscrits boucle, plusieurs operateurs','Collecte mai-juin 2022',
            'Evenement declencheur de l inscription, figure 35 ; distinct des avantages cites figure 37.',
            'Enquete retrospective ; taux nationaux non appliques aux communes.',
            sample=1813,numerator=count,denominator=1813,**national)
    add('sans_voiture','Aucune voiture disponible dans le menage',73.8,'%','ENA2022_RAPPORT',39,
        'enquete_declarative','France - inscrits boucle, plusieurs operateurs','Collecte mai-juin 2022',
        'Aucune voiture a disposition dans le menage, voiture de fonction comprise, figure 29.',
        'Inscrits interroges ; ne mesure pas le nombre local de personnes ayant le permis sans vehicule.',
        sample=1813,numerator=1338,denominator=1813,**national)
    for metric,label,value in [('locations_mois_moyenne','Utilisations mensuelles, moyenne',2.8),
                               ('locations_mois_mediane','Utilisations mensuelles, mediane',2.)]:
        add(metric,label,value,'utilisations/personne/mois','ENA2022_RAPPORT',49,
            'frequence_estimee_depuis_declarations','France - utilisateurs actifs boucle','Collecte mai-juin 2022',
            'Conversion des classes de frequence declaree en utilisations mensuelles, figures 43-44.',
            '1743 utilisateurs actifs : au moins une utilisation sur 12 mois ; pas un journal de reservations.',
            sample=1743,**national)
    local=dict(commune_code='69085',department='69',region='84',scope_type='commune',
               period_start='2023-11-01',period_end='2024-10-31',period_precision='mois_source_bornes_calendaires')
    for metric,label,value,unit,definition in [
        ('locations','Locations publiees',94,'locations','Nombre de locations sur les douze mois.'),
        ('kilometres','Kilometres parcourus',8274,'km','Kilometres des deux vehicules sur la periode.'),
        ('heures_reservees','Heures reservees',999,'heures','Duree reservee publiee ; pas temps de conduite.'),
        ('vehicules','Vehicules presentes dans le bilan',2,'vehicules','Flotte presentee dans le tableau ; jours reels de service inconnus.'),
        ('stations','Station concernee',1,'station','Station Fleurieu-sur-Saone presentee dans le bilan.'),
        ('clients_actifs','Clients actifs publies',15,'clients','Le bilan indique 15 actifs ; seuil d activite non explicite.'),
        ('locations_jour_vehicule_publie','Taux de locations publie',.13,'locations/jour/vehicule',
         'Taux fourni dans le document ; denominateur et indisponibilites non documentes.'),
        ('trajet_moyen_km','Distance moyenne publiee',88,'km/location','Moyenne arrondie publiee ; pas recalculee.'),
        ('trajet_moyen_heures','Duree moyenne publiee',11,'heures/location','Environ 11 heures ; valeur approximative publiee.')]:
        add(metric,label,value,unit,'FLEURIEU2024',12,'bilan_exploitation_publie','Fleurieu-sur-Saone',
            'Novembre 2023 - octobre 2024',definition,
            'Une station historique ; aucune extrapolation nationale, aucun bonus de priorite. Jours de service non publies.',
            approx=metric in ['trajet_moyen_km','trajet_moyen_heures'],**local)
    for metric,label,value,unit in [('reservations','Reservations Citiz',409,'reservations'),
                                   ('kilometres','Kilometres Citiz',54906,'km')]:
        add(metric,label,value,unit,'ROVALTAIN2024',10,'bilan_exploitation_publie','Parc Rovaltain',
            'Bilan 2024 - fenetre exacte non explicitee','Indicateur Citiz du parc dans le rapport environnemental 2024.',
            'Perimetre de site ; ni total communal ni serie annuelle certifiee. Flotte et jours de service non publies.',
            department='26',region='84',scope_type='site')
    for metric,label,value,approx in [('usage_anterieur','Autopartage deja utilise',13,False),
                                      ('achat_evite_intention','Vehicule cede ou achat evite envisage',43,False),
                                      ('usage_intention','Intention d utiliser le service',92,False),
                                      ('besoin_hebdomadaire','Besoin hebdomadaire, pres de 20 %',20,True)]:
        add(metric,label,value,'%','CITIZ_ORLEANS2025',2,'consultation_intention',
            'Metropole d Orleans','Consultation lancee janvier 2025, publiee octobre 2025',
            'Consultation citoyenne volontaire ; pourcentage publie, pas nombre de reservations.',
            '154 repondants au total ; effectif par question non fourni. Aucun effectif deduit des pourcentages arrondis.',
            sample=154,approx=approx,department='45',region='24',scope_type='metropole')
    add('satisfaction','Utilisateurs satisfaits',92,'%','CITIZ_LB2026',13,'enquete_declarative',
        'Reseau Citiz','Enquete de satisfaction 2024, reprise dans le livre blanc 2026',
        'Satisfaction publiee avec renvoi a l enquete annuelle Citiz 2024 (note 14, page imprimee 12).',
        'Echantillon, taux de reponse et questionnaire non fournis dans ce document.')
    add('demotorisation_apres_inscription','Vehicule cede apres inscription',60,'%','ADEME2025_SYNTHESE',np.nan,
        'enquete_declarative','France - utilisateurs autopartage en boucle','ENA2025, synthese mai 2026',
        'Part des usagers en boucle declarant s etre separes d un vehicule apres inscription.',
        'Effectif de cette question absent de la synthese ; evolution retrospective non causale.')
    add('notoriete_conducteurs','Conducteurs connaissant l autopartage',59,'%','ADEME2025_SYNTHESE',np.nan,
        'enquete_declarative','France - conducteurs','ENA2025, synthese mai 2026',
        'Connaissance et comprehension de l autopartage dans le volet conducteurs representatif de 1000 personnes.',
        'Pas un taux d intention ni d activation ; nombre de reponses par question non fourni.',sample=1000)
    result=pd.DataFrame(rows)
    refs=pd.DataFrame(RESEARCH_SOURCES)[['source_id','url','publication']].rename(columns={'url':'source_url','publication':'source_publication'})
    result=result.merge(refs,on='source_id',how='left',validate='many_to_one')
    result['verification']='releve_verifie_dans_source_publique'
    result['verified_at']='2026-10-21'
    validate_public_observations(result)
    return result


def validate_public_observations(data):
    if data.observation_id.duplicated().any(): raise ValueError('Observation publique dupliquee.')
    if data.source_url.isna().any() or not data.source_url.str.startswith('https://').all(): raise ValueError('Source publique requise.')
    if (~np.isfinite(data.value)|data.value.lt(0)).any(): raise ValueError('Valeur publique invalide.')
    if (data.unit.eq('%')&data.value.gt(100)).any(): raise ValueError('Pourcentage public invalide.')
    count_pair=data.numerator.notna()&data.denominator.gt(0)
    if (abs(100*data.loc[count_pair,'numerator']/data.loc[count_pair,'denominator']-data.loc[count_pair,'value'])>.11).any():
        raise ValueError('Effectifs incoherents avec la valeur publiee arrondie.')
    if data.used_in_ranking.any() or data.strict_operational_kpi.any(): raise ValueError('Observation contextuelle confondue avec KPI local.')
    if (data.scope_type.ne('commune')&data.commune_code.ne('')).any(): raise ValueError('Rattachement communal abusif.')
    return data


def public_observations_for_scope(data,codes,regions=(),departments=()):
    """References nationales toujours visibles, locales seulement dans leur perimetre."""
    match=data.scope_type.eq('national')
    match|=data.scope_type.eq('commune')&data.commune_code.isin(codes)
    match|=data.scope_type.isin(['site','metropole'])&data.department.isin(departments)
    return data.loc[match].copy()


def research_findings():
    rows=[
        ('economie','Economie et absence de contraintes de possession','ADEME2025_SYNTHESE',np.nan,np.nan,'Motivation qualitative ; pas de coefficient local'),
        ('occasionnel','Achats, visites et sorties ; locations courtes en boucle','ENA2022',np.nan,2768,'Echantillon multioperateurs ; pas 2768 usagers Citiz'),
        ('complement_tc','Voiture occasionnelle en complement des TC et du velo','ADEME2025_SYNTHESE',np.nan,np.nan,'Le manque de TC au domicile ne suffit pas a decrire le besoin'),
        ('achat_evite','Abandon d un vehicule ou achat evite envisage','CITIZ_ORLEANS2025',43.,154,'Intention locale ; non extrapolable a la France'),
        ('hebdomadaire','Besoin hebdomadaire declare, pres de 20 pour cent','CITIZ_ORLEANS2025',np.nan,154,'Valeur approximative conservee dans le texte'),
        ('vehicule_adapte','Utilitaire, groupe ou vehicule adapte selon le besoin','CITIZ_USAGES',np.nan,np.nan,'Usages presentes par l operateur, pas frequence mesuree')]
    return pd.DataFrame(rows,columns=['theme','constat','source_id','pourcentage','effectif_total','limite'])


def metric_catalog():
    rows=[
        ('public_motivations','Motivations declarees en boucle','public_collecte','pourcentage','ADEME / 6t ENA2022 p46','1813 inscrits ; plusieurs operateurs ; choix multiples'),
        ('public_station_activity','Locations, heures et kilometres de bilans Citiz','public_collecte','comptages','Fleurieu2024 / Rovaltain2024','Observations historiques de sites ; pas une couverture nationale'),
        ('public_satisfaction','Satisfaction du reseau Citiz','public_collecte','pourcentage','Citiz livre blanc 2026, enquete2024','92 pour cent ; effectif non publie dans le document'),
        ('target_license_no_vehicle','Cible permis sans vehicule','estimation','personnes','EMP2019 + RP2022','Profil regional applique localement ; non observe au carreau'),
        ('target_gap_share','Cible eloignee des arrets publies','proxy','part','Arrets PAN + grille','Ni frequence ni trajet TC ; inventaire a auditer'),
        ('walking_access','Acces pieton reel a une station','a_collecter','minutes','Reseau pieton + stations','Les distances actuelles sont aeriennes'),
        ('tc_useful_trips','Trajets utiles difficiles en TC','a_collecter','part','GTFS horaires + destinations','Soirees, dimanche et motifs a distinguer'),
        ('usage_basket_cost','Cout de paniers d usage','a_collecter','EUR','Tarifs Citiz sources + duree + km','Pas un budget d implantation ; aucun montant suppose'),
        ('activation_30d','Premiere reservation sous 30 jours','a_collecter','pourcentage','Agregats Citiz','Inscrits ayant tous 30 jours de recul'),
        ('reuse_90d','Nouvelle reservation sous 90 jours','a_collecter','pourcentage','Agregats Citiz','Cohorte de premiers utilisateurs ayant 90 jours de recul'),
        ('unmet_search_rate','Recherches sans vehicule compatible','a_collecter','pourcentage','Recherches Citiz dedoublonnees','Pas deduit d un instantane GBFS'),
        ('bookings_per_vehicle_day','Reservations par vehicule-jour de service','a_collecter','reservations/vehicule-jour','Agregats Citiz','Jours de service reels ; pas nombre de stations'),
        ('mobility_enabled','Deplacement rendu possible','a_collecter','pourcentage','Enquete locale','Declaration de trajet auquel on aurait renonce'),
        ('demotorization_followup','Baisse de motorisation au suivi','a_collecter','pourcentage','Enquete avant/apres','Evolution declaree, pas preuve de causalite')]
    return pd.DataFrame(rows,columns=['metric','indicateur','disponibilite_initiale','unite','donnees_requises','definition'])


KPI_COLUMNS=['commune_code','period_start','period_end','metric','numerator','denominator','source','definition_version']
SURVEY_COLUMNS=['commune_code','motif','n_reponses','n_eligibles','date_debut','date_fin','source']
MOTIFS=['courses_volumineuses','visites_proches','sorties_loisirs','trajet_tardif','destination_mal_desservie',
        'accompagnement','professionnel','vehicule_adapte','achat_evite','deplacement_rendu_possible']
KPI_IDS=['activation_30d','reuse_90d','unmet_search_rate','bookings_per_vehicle_day','mobility_enabled','demotorization_followup']


def annotate_evidence(frame):
    data=frame.copy()
    valid=data.priority_score.notna()
    data['evidence_status']=np.where(valid,'limitee_modele_non_valide','insuffisante_score_absent')
    data['evidence_gaps']='horaires_TC_non_mesures;cheminement_pieton_non_calcule;usage_occasionnel_non_mesure;parking_non_verifie'
    if 'local_survey_status' not in data: data['local_survey_status']='a_collecter'
    data['feasibility_status']='parking_et_implantation_a_verifier'
    if 'cells' in data and 'imputed_cells' in data:
        data['imputed_cell_share']=(data.imputed_cells/data.cells.where(data.cells>0)).clip(0,1)
    else: data['imputed_cell_share']=np.nan
    data['license_profile_age_years']=datetime.now(timezone.utc).year-2019
    return data


def _validate_aggregate(data,columns,keys,start,end):
    missing=set(columns)-set(data.columns)
    if missing: raise ValueError('Colonnes manquantes : '+', '.join(sorted(missing)))
    if set(data.columns)-set(columns): raise ValueError('Colonnes inattendues : importer uniquement le contrat agrege.')
    data=data.copy()
    data['commune_code']=data.commune_code.astype('string')
    if not data.commune_code.str.fullmatch(r'[0-9AB]{5}',na=False).all(): raise ValueError('Code commune INSEE a 5 caracteres requis.')
    if data.source.fillna('').astype(str).str.strip().eq('').any(): raise ValueError('Source requise pour chaque agregat.')
    dates={c:pd.to_datetime(data[c],errors='coerce',utc=True) for c in [start,end]}
    if any(s.isna().any() for s in dates.values()) or (dates[start]>dates[end]).any(): raise ValueError('Dates invalides ou inversees.')
    if data.duplicated(keys).any(): raise ValueError('Agregats dupliques pour un meme perimetre et une meme periode.')
    return data


def operational_kpis(data=None):
    if data is None or data.empty:
        return pd.DataFrame([dict(commune_code='',period_start='',period_end='',metric=k,numerator=np.nan,
                                 denominator=np.nan,source='',definition_version='v1',value=np.nan,status='a_collecter') for k in KPI_IDS])
    data=_validate_aggregate(data,KPI_COLUMNS,['commune_code','period_start','period_end','metric'],'period_start','period_end')
    if not data.metric.isin(KPI_IDS).all() or not data.definition_version.eq('v1').all(): raise ValueError('Metrique ou version de definition inconnue.')
    for c in ['numerator','denominator']:
        data[c]=pd.to_numeric(data[c],errors='raise')
        if (~np.isfinite(data[c])|data[c].lt(0)).any(): raise ValueError('Effectifs finis positifs ou nuls requis.')
    rates=data.metric.ne('bookings_per_vehicle_day')
    if (rates & data.numerator.gt(data.denominator)).any(): raise ValueError('Numerateur superieur au denominateur pour un taux.')
    if data.loc[rates,['numerator','denominator']].mod(1).ne(0).any().any(): raise ValueError('Effectifs entiers requis pour les taux.')
    if (data.denominator.eq(0)&data.numerator.gt(0)).any(): raise ValueError('Numerateur positif sans exposition.')
    data['value']=data.numerator/data.denominator.where(data.denominator>0)*np.where(rates,100,1)
    data['status']=np.where(data.denominator.gt(0),'calcule_depuis_agregats_sources','denominateur_nul_non_calculable')
    return data


def survey_metrics(data=None):
    if data is None or data.empty: return pd.DataFrame(columns=SURVEY_COLUMNS+['share_pct','status'])
    data=_validate_aggregate(data,SURVEY_COLUMNS,['commune_code','motif','date_debut','date_fin'],'date_debut','date_fin')
    if not data.motif.isin(MOTIFS).all(): raise ValueError('Motif inconnu.')
    for c in ['n_reponses','n_eligibles']:
        data[c]=pd.to_numeric(data[c],errors='raise')
        if (~np.isfinite(data[c])|data[c].lt(0)|data[c].mod(1).ne(0)).any(): raise ValueError('Effectifs d enquete entiers positifs ou nuls requis.')
    if data.n_reponses.gt(data.n_eligibles).any(): raise ValueError('Reponses superieures aux repondants eligibles.')
    data['share_pct']=100*data.n_reponses/data.n_eligibles.where(data.n_eligibles>0)
    data['status']=np.where(data.n_eligibles.gt(0),'declaratif_echantillon_local_non_representativite_garantie','denominateur_nul_non_calculable')
    return data


def archive_research_sources(workdir):
    from concurrent.futures import ThreadPoolExecutor
    raw=Path(workdir)/'research_raw'; raw.mkdir(parents=True,exist_ok=True)
    def collect(source):
        ext='.pdf' if source['url'].endswith('.pdf') else '.html'
        file=raw/(source['source_id']+ext)
        record={**source,'file':file.name}
        try:
            if not file.exists():
                with urlopen(Request(source['url'],headers={'User-Agent':'CitizResearchPrototype/1.0'}),timeout=25) as response:
                    content=response.read()
                if ext=='.pdf' and not content.startswith(b'%PDF'): raise ValueError('Reponse non PDF')
                file.write_bytes(content)
            record.update(status='archive_publique',sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                          retrieved_at=datetime.fromtimestamp(file.stat().st_mtime,timezone.utc).isoformat())
        except Exception as error: record.update(status='indisponible',detail=str(error))
        return record
    with ThreadPoolExecutor(max_workers=4) as pool: records=list(pool.map(collect,RESEARCH_SOURCES))
    meta=Path(workdir)/'bronze_metadata'; meta.mkdir(exist_ok=True)
    pd.DataFrame(records).to_csv(meta/'enquetes_sources_manifest.csv',index=False,encoding='utf-8')
    return pd.DataFrame(records)


def prepare_mobility_metrics(france):
    root=Path(france['workdir']); prepared=root/'silver_metadata'; prepared.mkdir(exist_ok=True)
    output=root/'output'; output.mkdir(exist_ok=True)
    templates=root/'templates'; templates.mkdir(exist_ok=True)
    research_findings().to_csv(prepared/'enquetes_constats.csv',index=False,encoding='utf-8')
    pd.DataFrame(RESEARCH_SOURCES).to_csv(prepared/'enquetes_references.csv',index=False,encoding='utf-8')
    observations=public_usage_observations()
    manifest=root/'bronze_metadata'/'enquetes_sources_manifest.csv'
    if manifest.exists():
        provenance=pd.read_csv(manifest).reindex(columns=['source_id','status','sha256','retrieved_at'])
        observations=observations.merge(provenance.rename(columns={'status':'archive_status'}),on='source_id',how='left',validate='many_to_one')
    else:
        observations=observations.assign(archive_status='archivage_a_executer',sha256='',retrieved_at='')
    observations.to_csv(prepared/'usages_observations_publiques.csv',index=False,encoding='utf-8')
    observations.to_csv(output/'citiz_fr_usages_publics.csv',index=False,encoding='utf-8')
    metric_catalog().to_csv(output/'citiz_fr_metriques_catalogue.csv',index=False,encoding='utf-8')
    frames={}; inputs={}
    for filename,columns,calculate in [('kpi_agreges.csv',KPI_COLUMNS,operational_kpis),('enquete_agregee.csv',SURVEY_COLUMNS,survey_metrics)]:
        template=templates/filename
        if not template.exists(): pd.DataFrame(columns=columns).to_csv(template,index=False,encoding='utf-8')
        path=root/'inputs'/filename
        data=pd.read_csv(path,dtype={'commune_code':str}) if path.exists() else None
        result=calculate(data)
        inputs[filename]=(path,data)
        frames[filename]=result
    known=set(france['overview'].commune_code)
    for frame in frames.values():
        codes=set(frame.commune_code.dropna())-{''}
        if codes-known: raise ValueError('Agregat avec code commune absent du perimetre : '+', '.join(sorted(codes-known)))
    for filename,(path,data) in inputs.items():
        if data is not None and not data.empty:
            raw=root/'research_inputs'; raw.mkdir(exist_ok=True); shutil.copyfile(path,raw/filename)
            data.to_csv(prepared/filename,index=False,encoding='utf-8')
    local_codes=set(frames['enquete_agregee.csv'].loc[frames['enquete_agregee.csv'].n_eligibles.gt(0),'commune_code'])
    france['overview']['local_survey_status']=np.where(france['overview'].commune_code.isin(local_codes),
                                                      'enquete_locale_declarative','a_collecter')
    frames['kpi_agreges.csv'].to_csv(output/'citiz_fr_kpi_suivi.csv',index=False,encoding='utf-8')
    frames['enquete_agregee.csv'].to_csv(output/'citiz_fr_enquete_locale.csv',index=False,encoding='utf-8')
    questions=[
        ('age_band','Dans quelle tranche d age vous situez-vous ?','18_24;25_34;35_44;45_59;60_plus;non_reponse'),
        ('usage_actuel','Utilisez-vous actuellement un service d autopartage ?','oui;non;ancien_usager;non_reponse'),
        ('permis_B','Possedez-vous un permis B utilisable pour le vehicule propose ?','oui;non;non_reponse'),
        ('vehicule_disponible','Disposez-vous personnellement d un vehicule lorsque vous en avez besoin ?','toujours;parfois;jamais;non_reponse'),
        ('frequence','Combien de besoins occasionnels de voiture par mois ?','0;1;2_3;4_plus;non_reponse'),
        ('motifs','Pour quels motifs utiliseriez-vous une voiture partagee ? Plusieurs choix possibles.',';'.join(MOTIFS)),
        ('creneaux','A quels moments ?','semaine_jour;semaine_soir;samedi;dimanche;non_reponse'),
        ('solution_actuelle','Comment realisez-vous ces deplacements actuellement ?','TC;velo;voiture_empruntee;location;taxi;renoncement;autre;non_reponse'),
        ('marche','Quelle duree de marche accepteriez-vous pour rejoindre une voiture ?','minutes_ou_non_reponse'),
        ('freins','Quels freins a l utilisation ?','prix;distance;disponibilite;connaissance;vehicule_inadapte;autre;non_reponse'),
        ('achat_evite','Le service pourrait-il vous permettre d eviter un achat ou de ceder un vehicule ?','oui;non;incertain;non_reponse')]
    pd.DataFrame(questions,columns=['variable','question','modalites']).to_csv(templates/'questionnaire_local.csv',index=False,encoding='utf-8')
    france['mobility']={'findings':research_findings(),'references':pd.DataFrame(RESEARCH_SOURCES),'catalog':metric_catalog(),
                       'kpis':frames['kpi_agreges.csv'],'survey':frames['enquete_agregee.csv'],'public_observations':observations}
    return france['mobility']


def mobility_panel_html(france,ranked):
    mobility=prepare_mobility_metrics(france)
    esc=html.escape
    sources=''.join(f'<li><a href="{esc(r.url,quote=True)}" target="_blank" rel="noopener">{esc(r.title)}</a> — {esc(r.scope)}. {esc(r.evidence)}.</li>' for r in mobility['references'].itertuples())
    codes=set(ranked.commune_code) if 'commune_code' in ranked else set()
    kpis=mobility['kpis']; kpis=kpis.loc[kpis.commune_code.isin(codes)|kpis.commune_code.eq('')]
    survey=mobility['survey']; survey=survey.loc[survey.commune_code.isin(codes)]
    observations=public_observations_for_scope(mobility['public_observations'],codes,
        departments=set(ranked.department) if 'department' in ranked else set())
    def show_observations(frame):
        if frame.empty: return '<p>Aucune observation publique collectee dans ce perimetre.</p>'
        body=[]
        for r in frame.itertuples():
            value=('environ ' if r.approximate else '')+f'{r.value:g} '+esc(r.unit)
            sample=f'Echantillon total : {r.sample_n:g}' if pd.notna(r.sample_n) else 'Effectif non fourni'
            page=f' · PDF p. {int(r.page_pdf)}' if pd.notna(r.page_pdf) else ''
            context=esc(r.territoire)+'<br><small>'+esc(r.periode)+'<br>'+sample+'</small>'
            source=f'<a href="{esc(r.source_url,quote=True)}" target="_blank" rel="noopener">{esc(r.source_id)}</a>'+page
            body.append('<tr>'+''.join('<td style="padding:10px;border-bottom:1px solid #dce5e5;vertical-align:top;overflow-wrap:anywhere">'+s+'</td>'
                                      for s in [esc(r.indicateur),'<b>'+value+'</b>',context,source])+'</tr>')
        return ('<table style="width:100%;table-layout:fixed;border-collapse:collapse;font:12px/1.5 Segoe UI">'
                '<colgroup><col style="width:27%"><col style="width:16%"><col style="width:37%"><col style="width:20%"></colgroup>'
                '<thead style="background:#edf3f4;text-align:left"><tr><th>Indicateur</th><th>Valeur publiee</th>'
                '<th>Perimetre et periode</th><th>Source</th></tr></thead><tbody>'+''.join(body)+'</tbody></table>')
    public_panel=(f'<h3>Collecte publique : {len(mobility["public_observations"])} chiffres verifies, '
                  f'{mobility["public_observations"].source_id.nunique()} documents</h3>'
                  '<p>References nationales et historiques. Plusieurs operateurs dans ENA2022 ; seuls les bilans Citiz sont specifiques a Citiz. '
                  'Les pourcentages ne sont ni des predictions locales ni des poids de classement.</p>'
                  '<div style="padding:14px;background:#edf7f4;border-left:5px solid #087f70">'
                  '<b>Motivations en boucle, ENA2022 :</b> entretien evite 83 % · cout 80 % · stationnement 65,6 %. '
                  '1813 inscrits interroges ; plusieurs reponses possibles.</div>'
                  '<h4>Enquetes et intentions publiees</h4>'+show_observations(observations.loc[observations.nature.ne('bilan_exploitation_publie')])+
                  '<h4>Utilisation Citiz observee dans les bilans publics</h4>'+show_observations(observations.loc[observations.nature.eq('bilan_exploitation_publie')])+
                  '<p>Les bilans de sites du departement sont des references contextuelles, pas un total pour les communes filtrees. '
                  'Le taux 0,13 de Fleurieu est publie sans jours reels de service ; il ne remplit pas le KPI strict reservations/vehicule-jour. '
                  'Rovaltain : bilan 2024, fenetre exacte non explicitee. Effectifs par question inconnus conserves vides. '
                  'Definitions et limites par ligne dans citiz_fr_usages_publics.csv (Or).</p>')
    return ("<div style='width:100%;max-width:900px;overflow-x:auto;white-space:normal'><h2>Usages, enquetes et suivi</h2><p><b>Besoin occasionnel : achats, visites, sorties, accompagnement et vehicule adapte.</b> "
            "Le manque de TC au domicile est un signal partiel. La priorite TC actuelle reste un scenario de pre-evaluation, pas une prediction de reservations. "
            "Les proportions nationales et la consultation d Orleans ne sont pas appliquees aux communes.</p>"+public_panel+
            "<h3>Pourquoi utiliser l autopartage ?</h3>"+mobility['findings'].to_html(index=False,escape=True,na_rep='Non chiffre')+
            '<h3>Sources et perimetres</h3><ul>'+sources+'</ul><h3>Indicateurs et donnees necessaires</h3>'+
            mobility['catalog'].to_html(index=False,escape=True)+
            '<h3>Suivi operationnel du perimetre</h3><p>Les lignes ci-dessous restent a collecter sans agregats sources. Fenetres 30/90 jours : choix de protocole, pas resultat d enquete.</p>'+
            kpis.round(2).to_html(index=False,escape=True,na_rep='A collecter')+
            '<h3>Enquete locale</h3>'+('<p>A collecter : aucun sondage local importe pour ce perimetre.</p>' if survey.empty else survey.round(2).to_html(index=False,escape=True,na_rep='Non calculable'))+
            '<p>Modeles CSV dans Files/citiz_france/templates (Or). Deposer uniquement les agregats dans Files/citiz_france/inputs (Bronze), puis relancer le notebook. '
            'Questionnaire prepare ; aucune enquete envoyee. Multi-choix : les parts par motif peuvent depasser 100 % au total. Aucun changement automatique des poids.</p></div>')
