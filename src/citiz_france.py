"""France: ingestion par morceaux, pre-evaluation communale, sans Spark.

Une commune est un territoire a etudier, jamais une station ni un gain de
couverture. Les grilles detaillees restent partitionnees par departement.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen, Request
from datetime import datetime, timezone
import json, zipfile, re, hashlib, html, shutil
import tempfile
import unicodedata
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from pyproj import Transformer
try:
    from mobility_metrics import annotate_evidence, prepare_mobility_metrics
except ImportError:
    pass  # definitions chargees directement dans le notebook portable

FR_SOURCES = {
    'communes.json': 'https://geo.api.gouv.fr/communes?fields=nom,code,codeDepartement,codeRegion,population,centre,surface&format=json',
    'departements.json': 'https://geo.api.gouv.fr/departements',
    'regions.json': 'https://geo.api.gouv.fr/regions',
    'systems.csv': 'https://raw.githubusercontent.com/MobilityData/gbfs/master/systems.csv',
    'transport_catalog.json': 'https://transport.data.gouv.fr/api/datasets',
    'stops_catalog.json': 'https://www.data.gouv.fr/api/1/datasets/arrets-de-transport-en-france/',
    'population.zip': 'https://www.insee.fr/fr/statistiques/fichier/8735162/Filosofi2021_carreaux_200m_csv.zip',
    'logement.zip': 'https://www.insee.fr/fr/statistiques/fichier/8647012/base-ic-logement-2022_csv.zip',
    'emp2019.zip': 'https://www.statistiques.developpement-durable.gouv.fr/media/5052/download?inline=',
    'emp2019_dictionary.xlsx': 'https://www.statistiques.developpement-durable.gouv.fr/media/5051/download?inline=',
}

MUNICIPAL_PARENTS={**{str(69380+i):'69123' for i in range(1,10)},
                   **{str(75100+i):'75056' for i in range(1,21)},
                   **{str(13200+i):'13055' for i in range(1,17)}}

METROPOLITAN_REGIONS=frozenset(['11','24','27','28','32','44','52','53','75','76','84','93','94'])
METROPOLITAN_DEPARTMENTS=frozenset([f'{i:02d}' for i in range(1,96) if i!=20]+['2A','2B'])
STUDY_REGIONS=METROPOLITAN_REGIONS-{'94'}
STUDY_DEPARTMENTS=METROPOLITAN_DEPARTMENTS-{'2A','2B'}


def study_scope(result):
    """Perimetre actif demande : France metropolitaine hors Corse."""
    data=result['overview']
    result['overview']=data.loc[data.region.astype(str).isin(STUDY_REGIONS)].copy()
    # Flux de reseaux Citiz francais : retrait des coordonnees ultramarines.
    # Cette emprise ne constitue pas un raccordement administratif des stations.
    stations=result['stations']
    result['stations']=stations.loc[stations.latitude.between(42.2,51.3)&stations.longitude.between(-5.3,8.3)].copy()
    if 'license_profiles' in result:
        result['license_profiles']=result['license_profiles'].loc[result['license_profiles'].region_key.ne('corse')].copy()
    result['scope']=dict(name='France metropolitaine hors Corse',regions=sorted(STUDY_REGIONS),
                         stations_filter='reseaux_Citiz_francais_emprise_continentale',
                         communes=len(result['overview']),cells=int(result['overview'].cells.sum()) if 'cells' in result['overview'] else None)
    return result

@dataclass
class FranceScenario:
    budget_eur: float | None = None
    site_cost_eur: float | None = None
    budget_source: str = ''
    cost_source: str = ''
    horizon_years: int | None = None
    max_sites: int = 20
    no_car_weight: float = 35
    transit_weight: float = 35
    population_weight: float = 20
    equity_weight: float = 5
    age_bonus: float = 5
    cost_penalty_weight: float = 25
    transit_coverage_penalty: float = 35
    region: str = ''
    department: str = ''
    search: str = ''
    def validate(self):
        values = [self.no_car_weight,
                  self.transit_weight, self.population_weight, self.equity_weight,
                  self.age_bonus, self.cost_penalty_weight, self.transit_coverage_penalty]
        if not all(np.isfinite(x) and x >= 0 for x in values):
            raise ValueError('Parametres negatifs ou non finis.')
        for value in [self.budget_eur,self.site_cost_eur]:
            if value is not None and (not np.isfinite(value) or value < 0):
                raise ValueError('Montant negatif ou non fini.')
        if self.horizon_years is not None and (self.horizon_years<1 or int(self.horizon_years)!=self.horizon_years):
            raise ValueError('Horizon en annees entieres strictement positif.')
        if not 0 <= self.max_sites <= 1000:
            raise ValueError('Maximum de sites entre 0 et 1000 requis.')
        if not 0 <= self.age_bonus <= 5:
            raise ValueError("Bonus d'age limite a 5 points.")
        if self.no_car_weight+self.transit_weight+self.population_weight+self.equity_weight > 95.000001:
            raise ValueError('Les quatre poids principaux doivent totaliser au plus 95 points.')

def fr_download(url, path, refresh=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not refresh and path.exists() and path.stat().st_size:
        return path
    tmp = path.with_suffix(path.suffix+'.part')
    with urlopen(Request(url, headers={'User-Agent':'CitizHelper-France/2.0'}), timeout=120) as response, tmp.open('wb') as output:
        while block := response.read(1024*1024):
            output.write(block)
    tmp.replace(path)
    return path

def fr_json(url):
    with urlopen(Request(url,headers={'User-Agent':'CitizHelper-France/2.0'}),timeout=45) as response:
        return json.load(response)

def sphere_xyz(lat, lon):
    lat,lon=np.radians(np.asarray(lat,dtype=float)),np.radians(np.asarray(lon,dtype=float))
    return np.column_stack([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])

def nearest_metres(tree, lat, lon):
    if tree is None:
        return np.full(len(lat),np.nan)
    chord,_=tree.query(sphere_xyz(lat,lon),workers=2)
    return 2*6_371_008.8*np.arcsin(np.minimum(chord/2,1))

def gbfs_feeds(data):
    body=data.get('data',{})
    if 'feeds' in body:
        return body['feeds']
    for language in ['fr','en',*body]:
        if isinstance(body.get(language),dict) and 'feeds' in body[language]:
            return body[language]['feeds']
    raise ValueError('Decouverte GBFS sans feeds.')

def normalized_name(value):
    value=unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower()
    return re.sub('[^a-z0-9]','',value)

def license_profiles(raw):
    """Croisement OBSERVE BPERMIS/JNBVEH. Agrégats d'enquete, pas registre.

    Coefficient: adultes avec permis B sans vehicule leger disponible / menages
    sans vehicule leger disponible, avec les poids individu et menage respectifs.
    Seuils de fiabilite heuristiques explicites, sans bonus de ruralite.
    """
    with zipfile.ZipFile(raw/'emp2019.zip') as z:
        def read(name,sep,columns):
            with z.open(name) as f:
                return pd.read_csv(f,sep=sep,encoding='cp1252',dtype=str,usecols=columns)
        people=read('k_individu_public_V3.csv',';',['IDENT_MEN','IDENT_IND','BPERMIS','pond_indC'])
        ages=read('tcm_ind_kish_public_V3.csv',';',['ident_ind','AGE']).rename(columns={'ident_ind':'IDENT_IND'})
        households=read('q_menage_public_V3.csv',';',['IDENT_MEN','JNBVEH','pond_menC'])
        geography=read('tcm_men_public_V3.csv',',',['ident_men','REG_res']).rename(columns={'ident_men':'IDENT_MEN'})
    people=people.merge(ages,on='IDENT_IND',validate='one_to_one')
    households=households.merge(geography,on='IDENT_MEN',validate='one_to_one')
    people=people.merge(households[['IDENT_MEN','JNBVEH','REG_res']],on='IDENT_MEN',validate='many_to_one')
    people['age']=pd.to_numeric(people.AGE,errors='coerce')
    people['weight']=pd.to_numeric(people.pond_indC,errors='coerce')
    households['weight']=pd.to_numeric(households.pond_menC,errors='coerce')
    for frame in [people,households]:
        frame['no_vehicle']=pd.to_numeric(frame.JNBVEH,errors='coerce').eq(0)
        frame['region_key']=frame.REG_res.map(normalized_name)
    def profile(key):
        p=people if key=='FR_MET' else people.loc[people.region_key.eq(key)]
        h=households if key=='FR_MET' else households.loc[households.region_key.eq(key)]
        p=p.loc[p.no_vehicle & p.age.ge(18) & p.weight.gt(0)]
        h=h.loc[h.no_vehicle & h.weight.gt(0)]
        known=p.BPERMIS.isin(['1','2'])
        effective=float(h.weight.sum()**2/(h.weight.pow(2).sum())) if len(h) else 0.
        missing=float(p.loc[~known,'weight'].sum()/p.weight.sum()) if len(p) else 1.
        holders=float(p.loc[p.BPERMIS.eq('1'),'weight'].sum())
        denominator=float(h.weight.sum())
        reliable=len(h)>=50 and effective>=30 and missing<=.05
        return dict(region_key=key,sample_no_vehicle_households=len(h),sample_adults=len(p),
                    effective_household_n=effective,missing_license_weight_share=missing,
                    weighted_license_holders_no_vehicle=holders,weighted_no_vehicle_households=denominator,
                    licensed_adults_per_no_vehicle_household=holders/denominator if reliable and denominator>0 else np.nan,
                    reliable=reliable,reference_year=2019,scope='France_metropolitaine',
                    definition='BPERMIS=1_AGE>=18_JNBVEH=0_VP_VUL_campingcar',
                    source_url='https://www.statistiques.developpement-durable.gouv.fr/resultats-detailles-de-lenquete-mobilite-des-personnes-de-2019')
    return pd.DataFrame([profile('FR_MET'),*[profile(k) for k in sorted(households.region_key.dropna().unique())]])

def attach_license_profile(result):
    root=Path(result['workdir']); raw=root/'raw'
    for name in ['emp2019.zip','emp2019_dictionary.xlsx']:
        fr_download(FR_SOURCES[name],raw/name)
    profiles=license_profiles(raw)
    national=profiles.loc[profiles.region_key.eq('FR_MET')].iloc[0]
    if not national.reliable: raise ValueError('Echantillon national permis sans vehicule insuffisant.')
    by_region=profiles.set_index('region_key')
    data=result['overview'].copy()
    keys=data.region_name.map(normalized_name)
    coefficients=keys.map(by_region.licensed_adults_per_no_vehicle_household)
    metropolitan=~data.department.astype(str).str.startswith(('97','98')) & data.department.notna()
    use_national=metropolitan & coefficients.isna()
    coefficients.loc[use_national]=national.licensed_adults_per_no_vehicle_household
    coefficients.loc[~metropolitan]=np.nan
    data['license_coefficient']=coefficients
    data['license_status']=np.where(~metropolitan,'hors_champ_EMP2019',np.where(use_national,'estimation_EMP2019_calage_national','estimation_EMP2019_calage_regional'))
    data['license_source']=national.source_url
    data['license_reference_year']=2019
    data['uncovered_licensed_adults_no_car_estimate']=data.uncovered_no_car_proxy*coefficients
    data['uncovered_gap_licensed_adults_estimate']=data.uncovered_gap_no_car_proxy*coefficients
    data['license_local_observed']=False
    result['overview']=data; result['license_profiles']=profiles
    rows=[]
    for name in ['emp2019.zip','emp2019_dictionary.xlsx']:
        rows.append(dict(source=name,url=FR_SOURCES[name],status='ok',retrieved_at=datetime.fromtimestamp((raw/name).stat().st_mtime,timezone.utc).isoformat()))
    result['sources']=pd.concat([result['sources'],pd.DataFrame(rows)],ignore_index=True).drop_duplicates(['source','url'],keep='last')
    return result

def acquire_france(workdir='/tmp/citiz_france', refresh_live=False):
    root=Path(workdir); raw=root/'raw'
    # Reutilisation du cache public V1; aucune dependance a un resultat lyonnais.
    for name in ['population.zip','logement.zip']:
        old=Path('/tmp/citiz_v1/raw')/name
        if old.exists() and not (raw/name).exists():
            raw.mkdir(parents=True,exist_ok=True); shutil.copyfile(old,raw/name)
    def acquire(item):
        name,url=item
        live=refresh_live and name.endswith(('.json','.csv'))
        fr_download(url,raw/name,refresh=live)
        print('France / source disponible:',name,flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(acquire,FR_SOURCES.items()))
    cat=json.loads((raw/'stops_catalog.json').read_text())
    resource=next(r for r in cat['resources'] if r['format'].lower()=='csv' and r['type']=='main')
    fr_download(resource['url'],raw/'stops.csv',refresh=refresh_live)
    manifest=[dict(source=n,url=u,retrieved_at=datetime.fromtimestamp((raw/n).stat().st_mtime,timezone.utc).isoformat(),status='ok') for n,u in FR_SOURCES.items()]
    manifest.append(dict(source='stops.csv',url=resource['url'],retrieved_at=resource['last_modified'],status='inventaire_experimental_sans_horaires'))
    # Catalogues PAN + MobilityData; exclure le GBFS velo Yelo mal nomme.
    systems=pd.read_csv(raw/'systems.csv').fillna('')
    urls={r['Auto-Discovery URL']:r['Name'] for _,r in systems.iterrows()
          if r['Country Code']=='FR' and 'backend.citiz.fr/public/provider/' in r['Auto-Discovery URL']}
    catalog=json.loads((raw/'transport_catalog.json').read_text())
    for dataset in catalog:
        if 'citiz' in dataset.get('title','').lower() and dataset.get('type')=='vehicles-sharing':
            for r in dataset.get('resources',[]):
                if r.get('format','').lower()=='gbfs':
                    urls[r.get('original_url',r['url'])]=dataset['title']
    # Plusieurs catalogues peuvent pointer le meme provider avec v3.0 / 3.0.
    unique={}
    for url,name in urls.items():
        provider=re.search(r'/provider/(\d+)/',url)
        key='provider_'+provider[1] if provider else url
        unique.setdefault(key,(url,name))
    def station_source(item):
        key,(url,label)=item
        digest=hashlib.sha256(key.encode()).hexdigest()[:12]
        discovery=raw/f'gbfs_{digest}.json'; stations_file=raw/f'stations_{digest}.json'
        try:
            fr_download(url,discovery,refresh_live)
            data=json.loads(discovery.read_text())
            station_url=next(f['url'] for f in gbfs_feeds(data) if f['name']=='station_information')
            fr_download(station_url,stations_file,refresh_live)
            info=json.loads(stations_file.read_text())
            rows=[]
            for station in info['data']['stations']:
                name=station.get('name','')
                if isinstance(name,list): name=' / '.join(n.get('text','') for n in name)
                rows.append(dict(station_id=str(station['station_id']),network=label,provider=key,
                                 name=str(name),latitude=station['lat'],longitude=station['lon']))
            return rows,dict(source=label,url=url,status='ok',retrieved_at=str(info.get('last_updated','')))
        except Exception as error:
            return [],dict(source=label,url=url,status='indisponible_'+type(error).__name__,retrieved_at='')
    station_rows=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for rows,status in pool.map(station_source,unique.items()):
            station_rows.extend(rows); manifest.append(status)
            print('GBFS:',status['source'],len(rows),status['status'],flush=True)
    if not station_rows: raise RuntimeError('Aucune station Citiz accessible : couverture inconnue.')
    stations=pd.DataFrame(station_rows)
    # Deduplication geometrique des copies de catalogues, pas du stop_id GTFS.
    stations['lat_key']=stations.latitude.round(5); stations['lon_key']=stations.longitude.round(5)
    stations=stations.drop_duplicates(['lat_key','lon_key']).drop(columns=['lat_key','lon_key'])
    return raw,stations.reset_index(drop=True),pd.DataFrame(manifest)

def load_fr_communes(raw):
    data=json.loads((raw/'communes.json').read_text())
    records=[]
    for r in data:
        coords=r.get('centre',{}).get('coordinates',[np.nan,np.nan])
        records.append(dict(commune_code=r['code'],commune=r['nom'],department=r.get('codeDepartement',''),
                            region=r.get('codeRegion',''),population_legal=r.get('population',np.nan),
                            latitude=coords[1],longitude=coords[0]))
    communes=pd.DataFrame(records).drop_duplicates('commune_code')
    departments={r['code']:r['nom'] for r in json.loads((raw/'departements.json').read_text())}
    regions={r['code']:r['nom'] for r in json.loads((raw/'regions.json').read_text())}
    communes['department_name']=communes.department.map(departments).fillna('Non renseigne')
    communes['region_name']=communes.region.map(regions).fillna('Non renseignee')
    columns=['COM','P22_MEN','P22_RP_VOIT1P','P22_RP_VOIT1']
    with zipfile.ZipFile(raw/'logement.zip') as archive:
        name=next(n for n in archive.namelist() if n.lower().startswith('base-ic') and n.lower().endswith('.csv'))
        with archive.open(name) as f: housing=pd.read_csv(f,sep=';',dtype={'COM':str},usecols=columns)
    for c in columns[1:]: housing[c]=pd.to_numeric(housing[c],errors='coerce')
    # Arrondissements municipaux -> commune mere, avant toute aggregation.
    housing['COM']=housing.COM.replace(MUNICIPAL_PARENTS)
    housing=housing.groupby('COM')[columns[1:]].sum(min_count=1)
    housing['no_car_rate']=(1-housing.P22_RP_VOIT1P/housing.P22_MEN.replace(0,np.nan)).clip(0,1)
    housing['one_car_rate']=(housing.P22_RP_VOIT1/housing.P22_MEN.replace(0,np.nan)).clip(0,1)
    housing['households_rp2022']=housing.P22_MEN
    housing['no_car_households_rp2022']=(housing.P22_MEN-housing.P22_RP_VOIT1P).clip(lower=0)
    communes=communes.merge(housing[['no_car_rate','one_car_rate','households_rp2022','no_car_households_rp2022']],left_on='commune_code',right_index=True,how='left')
    return communes

def prepare_france(workdir, raw, stations, manifest):
    """Preparation 200 m limitee aux communes metropolitaines hors Corse."""
    root=Path(workdir); root.mkdir(parents=True,exist_ok=True)
    silver=Path(tempfile.mkdtemp(prefix='cells_build_',dir=root))
    communes=load_fr_communes(raw)
    communes=communes.loc[communes.region.isin(STUDY_REGIONS)].copy()
    metropolitan_codes=set(communes.commune_code)
    stops_parts=[]
    for chunk in pd.read_csv(raw/'stops.csv',usecols=['stop_lat','stop_lon'],chunksize=250_000):
        for c in chunk: chunk[c]=pd.to_numeric(chunk[c],errors='coerce')
        chunk=chunk.dropna()
        chunk=chunk.loc[chunk.stop_lat.between(-90,90)&chunk.stop_lon.between(-180,180)]
        stops_parts.append(chunk.round(5).drop_duplicates())
    stops=pd.concat(stops_parts,ignore_index=True).drop_duplicates()
    stop_tree=cKDTree(sphere_xyz(stops.stop_lat,stops.stop_lon))
    station_tree=cKDTree(sphere_xyz(stations.latitude,stations.longitude))
    summaries=[]; quality=[]
    usecols=['idcar_200m','lcog_geo','ind','men','men_pauv','ind_18_24','ind_25_39',
             'ind_40_54','ind_55_64','ind_65_79','ind_80p','i_est_200']
    with zipfile.ZipFile(raw/'population.zip') as archive:
        for name in archive.namelist():
            if not name.endswith('.csv'): continue
            with archive.open(name) as stream:
                for chunk_no,chunk in enumerate(pd.read_csv(stream,usecols=usecols,dtype={'lcog_geo':str},chunksize=120_000)):
                    chunk=chunk.loc[(chunk.ind>0)&(chunk.men>0)].copy()
                    if chunk.empty: continue
                    # Aucun partage arbitraire d'un carreau chevauchant des communes.
                    single=chunk.lcog_geo.str.fullmatch(r'[0-9AB]{5}',na=False)
                    quality.append(dict(file=name,chunk=chunk_no,cells=len(chunk),ambiguous_commune=int((~single).sum()),population_ambiguous=float(chunk.loc[~single,'ind'].sum())))
                    chunk=chunk.loc[single].copy()
                    chunk=chunk.rename(columns={'lcog_geo':'commune_code','idcar_200m':'cell_id','ind':'population','men':'households','men_pauv':'poor_households'})
                    chunk['commune_code']=chunk.commune_code.replace(MUNICIPAL_PARENTS)
                    chunk=chunk.loc[chunk.commune_code.isin(metropolitan_codes)].copy()
                    if chunk.empty: continue
                    chunk=chunk.merge(communes[['commune_code','commune','department','region','no_car_rate','one_car_rate']],on='commune_code',how='left',validate='many_to_one')
                    projection=chunk.cell_id.str.extract(r'CRS(\d+)RES200mN(-?\d+)E(-?\d+)')
                    if projection.isna().any().any(): raise ValueError('Projection de grille inconnue.')
                    chunk['latitude']=np.nan; chunk['longitude']=np.nan
                    for crs in projection[0].unique():
                        mask=projection[0].eq(crs)
                        xy=projection.loc[mask,[2,1]].astype(float).to_numpy()+100
                        transform=Transformer.from_crs(int(crs),4326,always_xy=True)
                        lon,lat=transform.transform(xy[:,0],xy[:,1])
                        chunk.loc[mask,'latitude']=lat; chunk.loc[mask,'longitude']=lon
                    chunk['nearest_stop_m']=nearest_metres(stop_tree,chunk.latitude,chunk.longitude)
                    chunk['nearest_citiz_m']=nearest_metres(station_tree,chunk.latitude,chunk.longitude)
                    chunk['citiz_covered']=chunk.nearest_citiz_m.le(400)
                    # Eloignement des arrets PUBLIES, jamais frequence de desserte.
                    chunk['transit_gap_proxy']=(chunk.nearest_stop_m/400-1).clip(0,1)
                    chunk['adults']=chunk[[c for c in usecols if c.startswith('ind_')]].sum(axis=1)
                    chunk['age_25_39']=chunk.ind_25_39
                    chunk['no_car_households_proxy']=chunk.households*chunk.no_car_rate
                    chunk['uncovered_population']=chunk.population*(~chunk.citiz_covered)
                    chunk['uncovered_no_car_proxy']=chunk.no_car_households_proxy*(~chunk.citiz_covered)
                    chunk['uncovered_gap_no_car_proxy']=chunk.uncovered_no_car_proxy*chunk.transit_gap_proxy
                    chunk['population_far_stops']=chunk.population*chunk.nearest_stop_m.gt(400)
                    chunk['license_status']='non_mesure'
                    chunk['transit_status']='proximite_arrets_publies_horaires_non_mesures'
                    sums=['population','households','poor_households','adults','age_25_39','uncovered_population',
                          'uncovered_no_car_proxy','uncovered_gap_no_car_proxy','population_far_stops']
                    summary=chunk.groupby('commune_code')[sums].sum(min_count=1)
                    summary['cells']=chunk.groupby('commune_code').size()
                    summary['imputed_cells']=chunk.groupby('commune_code').i_est_200.sum()
                    summaries.append(summary)
                    for department,group in chunk.groupby('department'):
                        folder=silver/str(department); folder.mkdir(exist_ok=True)
                        destination=folder/'cells.csv'
                        group.drop(columns=[c for c in usecols if c.startswith('ind_')]).to_csv(
                            destination,index=False,encoding='utf-8',mode='a',header=not destination.exists())
                    print('France / grilles:',name,chunk_no,len(chunk),flush=True)
    overview=communes.merge(pd.concat(summaries).groupby(level=0).sum(min_count=1),left_on='commune_code',right_index=True,how='left')
    overview['grid_status']=np.where(overview.cells.notna(),'200m_Filosofi2021','grille_absente_ou_geographie_non_raccordee')
    overview['license_status']='non_mesure'
    overview['transit_status']='proximite_arrets_publies_horaires_non_mesures'
    overview['citiz_inventory_status']='catalogues_partiels_verifier_terrain'
    overview['share_25_39_adults']=(overview.age_25_39/overview.adults.replace(0,np.nan)).clip(0,1)
    overview['poverty_rate']=(overview.poor_households/overview.households.replace(0,np.nan)).clip(0,1)
    # Ne pas confondre RP2022, population legale et Filosofi2021.
    overview['population_reference']='Filosofi2021_pour_score_population_legale_separee'
    # Bascule des partitions seulement apres une preparation complete.
    current=root/'cells'
    if current.exists():
        archive_folder=root/'archive'; archive_folder.mkdir(exist_ok=True)
        current.rename(archive_folder/('cells_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')))
    silver.rename(current)
    return dict(workdir=str(root),overview=overview,stations=stations,stops=stops,
                sources=manifest,quality=pd.DataFrame(quality))

def france_rank(overview, scenario=None, cost_overrides=None):
    scenario=scenario or FranceScenario(); scenario.validate()
    data=overview.copy()
    if scenario.region: data=data.loc[data.region.eq(scenario.region)]
    if scenario.department: data=data.loc[data.department.eq(scenario.department)]
    if scenario.search: data=data.loc[data.commune.str.contains(scenario.search,case=False,regex=False,na=False)|data.commune_code.eq(scenario.search)]
    def signal(column,anchor):
        x=data[column].clip(lower=0)
        return x/(x+anchor)
    target='uncovered_licensed_adults_no_car_estimate' if 'uncovered_licensed_adults_no_car_estimate' in data else 'uncovered_no_car_proxy'
    target_gap='uncovered_gap_licensed_adults_estimate' if 'uncovered_gap_licensed_adults_estimate' in data else 'uncovered_gap_no_car_proxy'
    # Part de la cible restant eloignee des arrets publies. Le volume seul
    # ne suffit pas dans une commune deja bien desservie (ex. Paris).
    gap=(data[target_gap]/data[target].where(data[target]>0)).clip(0,1)
    gap=gap.mask(data[target].eq(0),0)
    data['target_transit_gap']=gap
    support=(data[target]/200).clip(0,1)
    data['points_no_car']=scenario.no_car_weight*signal(target,1000)*gap
    data['points_transit']=scenario.transit_weight*signal(target_gap,500)
    data['target_basis']='permis_sans_vehicule_estime_EMP2019' if target!='uncovered_no_car_proxy' else 'proxy_sans_voiture_permis_non_mesure'
    data['points_population']=scenario.population_weight*signal('uncovered_population',10000)*gap
    data['points_equity']=scenario.equity_weight*(data.poverty_rate/.4).clip(0,1)*gap*support
    data['points_age']=scenario.age_bonus*(data.share_25_39_adults/.4).clip(0,1)*gap*support
    terms=['points_no_car','points_transit','points_population','points_equity','points_age']
    data['benefit_score']=data[terms].sum(axis=1,min_count=len(terms))
    data['transit_coverage_penalty']=scenario.transit_coverage_penalty*(1-gap)
    data['mobility_need_score']=(data.benefit_score-data.transit_coverage_penalty).clip(0,100)
    data['cost_total_eur']=np.nan if scenario.site_cost_eur is None else scenario.site_cost_eur
    data['cost_source']=scenario.cost_source.strip()
    data['budget_source']=scenario.budget_source.strip()
    data['horizon_years']=scenario.horizon_years
    data['cost_status']='non_documente'
    if cost_overrides is not None:
        for code,value in cost_overrides.items():
            source=scenario.cost_source.strip()
            if isinstance(value,tuple): value,source=value
            data.loc[data.commune_code.eq(code),'cost_total_eur']=value
            data.loc[data.commune_code.eq(code),'cost_source']=str(source).strip()
    if data.cost_total_eur.lt(0).any(): raise ValueError('Cout negatif interdit.')
    documented=np.isfinite(data.cost_total_eur)&data.cost_source.ne('')
    finance_ready=(scenario.budget_eur is not None and bool(scenario.budget_source.strip()) and bool(documented.any()) and scenario.horizon_years is not None)
    data.loc[documented,'cost_status']='montant_source_a_verifier'
    # Aucun prix ni budget suppose. Le coefficient de cout est relatif au
    # budget documente, pas a un montant de reference financier invente.
    data['cost_penalty']=np.nan
    data['score_status']='besoin_hors_couts_budget_non_documente'
    data['priority_score']=data.mobility_need_score
    if finance_ready:
        if scenario.budget_eur>0:
            data.loc[documented,'cost_penalty']=scenario.cost_penalty_weight*(data.loc[documented,'cost_total_eur']/scenario.budget_eur).clip(upper=2)
        else: data.loc[documented,'cost_penalty']=0.
        data['priority_score']=(data.mobility_need_score-data.cost_penalty).clip(0,100)
        data['score_status']='besoin_moins_penalite_cout_source'
    data['selection_order']=0
    data['selected']=False
    data=data.sort_values(['priority_score','cost_total_eur','commune_code'],ascending=[False,True,True],na_position='last').reset_index(drop=True)
    spent=0.; chosen=0
    for i,r in data.iterrows():
        if not finance_ready or chosen>=scenario.max_sites: break
        if not np.isfinite(r.cost_total_eur) or not str(r.cost_source).strip(): continue
        if not np.isfinite(r.priority_score) or r.priority_score<=0: continue
        if spent+r.cost_total_eur>scenario.budget_eur: continue
        spent+=r.cost_total_eur; chosen+=1
        data.loc[i,['selected','selection_order']]=[True,chosen]
    data['rank']=np.arange(1,len(data)+1)
    data['decision_level']='commune_a_etudier_pas_emplacement_valide'
    if 'annotate_evidence' in globals(): data=annotate_evidence(data)
    return data

def save_france(result, scenario=None):
    root=Path(result['workdir']); output=root/'output'; output.mkdir(parents=True,exist_ok=True)
    # Separations de responsabilite Bronze / Argent / Or, en CSV.
    bronze_meta=root/'bronze_metadata'; bronze_meta.mkdir(exist_ok=True)
    silver_meta=root/'silver_metadata'; silver_meta.mkdir(exist_ok=True)
    result['sources'].to_csv(bronze_meta/'sources_manifest.csv',index=False,encoding='utf-8')
    silver_columns=['commune_code','commune','department','region','population_legal','latitude','longitude',
                    'department_name','region_name','no_car_rate','one_car_rate','households_rp2022',
                    'no_car_households_rp2022','population','households','poor_households','adults',
                    'age_25_39','uncovered_population','uncovered_no_car_proxy','uncovered_gap_no_car_proxy',
                    'population_far_stops','cells','imputed_cells','grid_status','license_status','transit_status',
                    'citiz_inventory_status','share_25_39_adults','poverty_rate','population_reference']
    silver_columns += [c for c in ['license_coefficient','license_source','license_reference_year','license_local_observed',
                                  'uncovered_licensed_adults_no_car_estimate','uncovered_gap_licensed_adults_estimate'] if c in result['overview']]
    result['overview'][silver_columns].to_csv(silver_meta/'communes_enrichies.csv',index=False,encoding='utf-8')
    result['stations'].to_csv(silver_meta/'stations_nettoyees.csv',index=False,encoding='utf-8')
    result['quality'].to_csv(silver_meta/'qualite_raccordement.csv',index=False,encoding='utf-8')
    if 'license_profiles' in result:
        result['license_profiles'].to_csv(silver_meta/'profils_permis_EMP2019.csv',index=False,encoding='utf-8')
    scenario=scenario or FranceScenario()
    result['ranked']=france_rank(result['overview'],scenario)
    result['tables']={
        'citiz_fr_communes':result['ranked'],
        'citiz_fr_stations':result['stations'],
        'citiz_fr_sources':result['sources'],
        'citiz_fr_quality':result['quality'],
    }
    if 'license_profiles' in result: result['tables']['citiz_fr_permis_profils']=result['license_profiles']
    for name,df in result['tables'].items(): df.to_csv(output/f'{name}.csv',index=False,encoding='utf-8')
    (output/'scenario.json').write_text(json.dumps(asdict(scenario),indent=2),encoding='utf-8')
    if 'scope' in result:
        (output/'scope.json').write_text(json.dumps(result['scope'],ensure_ascii=False,indent=2),encoding='utf-8')
    if 'prepare_mobility_metrics' in globals(): prepare_mobility_metrics(result)
    return result

def run_france(workdir='/tmp/citiz_france', refresh=False, rebuild=False):
    root=Path(workdir)
    cache=root/'output'/'citiz_fr_communes.csv'
    if cache.exists() and not refresh and not rebuild:
        print('France / reprise du cache national prepare.',flush=True)
        result=dict(workdir=str(root),overview=pd.read_csv(cache,dtype={'commune_code':str,'department':str,'region':str}),
                    stations=pd.read_csv(root/'output'/'citiz_fr_stations.csv',dtype={'station_id':str}),
                    sources=pd.read_csv(root/'output'/'citiz_fr_sources.csv').fillna(''),quality=pd.read_csv(root/'output'/'citiz_fr_quality.csv'))
        return study_scope(attach_license_profile(result))
    raw,stations,manifest=acquire_france(workdir,refresh_live=refresh)
    result=save_france(study_scope(attach_license_profile(prepare_france(workdir,raw,stations,manifest))))
    print('FRANCE PRETE:',len(result['overview']),'communes;',len(stations),'stations connues;',int(result['overview'].cells.sum()),'carreaux raccordes.',flush=True)
    return result
