"""Tables d'analyse explicables : geographie, besoins, score et qualite."""
from pathlib import Path
import html
import numpy as np
import pandas as pd


def _columns(data,spec):
    frame=pd.DataFrame(index=data.index)
    for group,label,name in spec:
        frame[(group,label)]=data[name] if name in data else np.nan
    frame.columns=pd.MultiIndex.from_tuples(frame.columns)
    return frame.reset_index(drop=True)


def build_analysis_tables(france,ranked,cells,metrics_fn):
    local=cells is not None
    scored=ranked.copy()
    population=cells.copy() if local else ranked.copy()
    if local and 'cell_id' in population: population=population.drop_duplicates('cell_id')
    metadata=france.get('overview',pd.DataFrame())
    for frame_name in ['scored','population']:
        frame=scored if frame_name=='scored' else population
        if 'commune_code' in metadata and 'commune_code' in frame:
            missing=[c for c in ['region','region_name','department','department_name','commune'] if c not in frame and c in metadata]
            if missing: frame=frame.merge(metadata[['commune_code',*missing]].drop_duplicates('commune_code'),on='commune_code',how='left',validate='many_to_one')
        if frame_name=='scored': scored=frame
        else: population=frame
    ordered=scored.sort_values('priority_score',ascending=False,na_position='last')
    geography=[('Territoire','Code INSEE','commune_code'),('Territoire','Commune','commune'),('Territoire','Departement','department_name')]
    target='new_licensed_adults_no_car_estimate' if local else 'uncovered_licensed_adults_no_car_estimate'
    people='new_population' if local else 'uncovered_population'
    ranking=_columns(ordered,geography+[
        ('Besoin','Permis sans vehicule hors Citiz',target),
        ('Besoin','Habitants non couverts dans le rayon (non additif)' if local else 'Habitants hors Citiz',people),
        ('Transports','Manque TC de la cible (0-1)','transit_gap' if local else 'target_transit_gap'),
        ('Decision','Score /100','priority_score'),('Qualite','Statut permis','license_status'),
        ('Qualite','Statut du modele','evidence_status')])
    score_spec=geography[:2]+[
        ('Points de besoin','Cible permis','points_no_car'),
        ('Points de besoin','Eloignement TC','points_transit_gap' if local else 'points_transit'),
        ('Points de besoin','Population','points_new_population' if local else 'points_population'),
        ('Points de besoin','Social','points_equity'),('Points de besoin','Age','points_age'),
        ('Penalites','TC deja proches','transit_coverage_penalty')]
    if 'cost_penalty' in scored and scored.cost_penalty.notna().any():
        score_spec += [('Penalites','Couts documentes','cost_penalty'),('Finances','Cout sur horizon EUR','cost_total_eur'),('Finances','Reference','cost_source')]
    scores=_columns(ordered,score_spec+[('Resultat','Score /100','priority_score')])
    tables={'classement':ranking,'decomposition':scores}
    for key,title in [('region','regions'),('department','departements')]:
        if key not in population: continue
        records=[]
        for code,group in population.groupby(key,dropna=False,sort=True):
            measures=metrics_fn(group,group if local else None)
            group_scores=scored.loc[scored[key].eq(code)] if key in scored and pd.notna(code) else scored.iloc[:0]
            name_col=key+'_name'
            labels=group[name_col].dropna() if name_col in group else pd.Series(dtype=str)
            known=group_scores.priority_score.dropna()
            records.append({('Territoire','Code'):str(code) if pd.notna(code) else 'Non renseigne',
                ('Territoire','Nom'):str(labels.iloc[0]) if len(labels) else '',
                ('Population','Etudiee'):measures['population'],('Cible','Permis hors Citiz estime'):measures['target'],
                ('Transports','A plus de 400 m des arrets %'):measures['far_share'],
                ('Citiz','A moins de 400 m %'):measures['citiz_share'],
                ('Classement','Candidats' if local else 'Communes'):len(group_scores),
                ('Classement','Scores calculables'):len(known),('Classement','Mediane /100'):known.median(),
                ('Classement','Maximum /100'):known.max(),('Classement','Score >=40'):int(known.ge(40).sum())})
        table=pd.DataFrame(records)
        if len(table): table.columns=pd.MultiIndex.from_tuples(table.columns)
        tables[title]=table
    bins=pd.cut(scored.priority_score,[-np.inf,20,40,60,np.inf],labels=['0 a <20','20 a <40','40 a <60','60 et plus'],right=False)
    classes=bins.astype(object).fillna('Non calculable')
    distribution=classes.value_counts().reindex(['0 a <20','20 a <40','40 a <60','60 et plus','Non calculable'],fill_value=0)
    tables['distribution']=pd.DataFrame({'Classe de score':distribution.index,'Nombre de lignes':distribution.values,
        'Part des lignes %':100*distribution.values/max(len(scored),1)})
    quality=[]
    for column in ['priority_score',target,'population_far_stops','uncovered_population','license_coefficient','no_car_rate','cost_total_eur','cost_source']:
        if column not in scored: continue
        values=scored[column]
        missing=values.isna() | values.astype(str).str.strip().eq('')
        quality.append(dict(Variable=column,Lignes=len(values),Renseignees=int((~missing).sum()),Manquantes=int(missing.sum()),
            Part_manquante_pct=100*missing.mean() if len(values) else np.nan))
    tables['qualite']=pd.DataFrame(quality)
    tables['sources']=france.get('sources',pd.DataFrame()).copy()
    return tables


def analysis_report(tables,local=False):
    descriptions={
        'classement':('Classement detaille','Tri par score decroissant. '+('Les rayons se recouvrent : leurs gains ne s’additionnent pas.' if local else 'Les volumes portent sur les habitants hors couverture Citiz connue.')),
        'decomposition':('Decomposition et penalites','Points du scenario courant. Une colonne financiere apparait seulement si elle est renseignee.'),
        'regions':('Comparaison des regions','Pourcentages ponderes par la population renseignee. Mediane et maximum des scores, sans somme de scores.'),
        'departements':('Comparaison des departements','Population et cible agregees sans double comptage des carreaux. Les manquants restent exclus des denominateurs.'),
        'distribution':('Distribution des priorites','Effectifs et parts des lignes du classement. Les scores absents sont isoles.'),
        'qualite':('Completude des donnees','Les pourcentages portent sur les lignes, pas sur la population. Un champ rempli peut rester une estimation.'),
        'sources':('Inventaire et provenance','Sources disponibles et statuts de collecte. Un inventaire incomplet ne prouve pas une absence de service.')}
    result='<h3>Analyse du territoire</h3><p>Les tableaux suivent les filtres et les poids courants. Horaires, reservations et disponibilite des vehicules ne sont pas observes.</p>'
    for key,frame in tables.items():
        title,description=descriptions[key]
        limit=50 if key in ['classement','decomposition'] else 120
        subset=frame.head(limit)
        table=subset.to_html(index=False,escape=True,na_rep='Non renseigne',border=0,float_format=lambda x:f'{x:,.2f}'.replace(',',' '))
        text=f'{len(frame):,} lignes'.replace(',',' ')
        if len(frame)>limit: text+=f' · {limit} affichees · export CSV complet disponible'
        result+=(f'<details class="cb-analysis-table"{" open" if key=="classement" else ""}><summary>{html.escape(title)} <span>{text}</span></summary>'
                 f'<p>{html.escape(description)}</p><div class="cb-table-scroll">{table}</div></details>')
    return result


def export_analysis_tables(tables,folder,prefix='analyse_'):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    for name,frame in tables.items():
        data=frame.copy()
        if isinstance(data.columns,pd.MultiIndex): data.columns=[' / '.join(str(x) for x in column) for column in data.columns]
        data.to_csv(folder/(prefix+name+'.csv'),index=False,encoding='utf-8')
