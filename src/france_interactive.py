"""Interface interactive Fabric: widgets -> recalcul Python -> nouvelle carte.

Sans Output/interact, non pris en charge par Fabric. Les widgets HTML sont mis
a jour en place. Une session Python ouverte est necessaire pour recalculer.
"""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import html, json
import numpy as np
import pandas as pd
from pyproj import Transformer
try:
    from citiz_france import FranceScenario, france_rank, STUDY_REGIONS, STUDY_DEPARTMENTS, sphere_xyz, nearest_metres
except ImportError:
    pass  # definitions deja chargees dans le notebook Fabric
try:
    from mobility_metrics import annotate_evidence, mobility_panel_html
except ImportError:
    pass
try:
    from analysis_views import build_analysis_tables, analysis_report, export_analysis_tables
except ImportError:
    pass


PRIORITY_COLORS=[(20,'#2878a5','Faible · 0 a <20'),(40,'#d7aa28','Moderee · 20 a <40'),
                 (60,'#e07732','Elevee · 40 a <60'),(101,'#b52b42','Tres elevee · 60 a 100')]


def priority_color(score):
    if not np.isfinite(score): return '#77838c'
    return next(color for upper,color,_ in PRIORITY_COLORS if score<upper)


MAP_THEMES={
    'priority':('Priorites d implantation','Score de besoin /100, avec les poids du scenario. Centres de communes ou de carreaux a etudier.'),
    'target':('Permis et absence de vehicule','Personnes estimees avec permis B et aucun vehicule disponible, hors couverture Citiz.'),
    'transit':('Eloignement des arrets','Part de population a plus de 400 m a vol d oiseau d un arret publie. Proxy spatial : les horaires, frequences et destinations ne sont pas mesures.'),
    'citiz':('Couverture Citiz','Population estimee a moins de 400 m a vol d oiseau d une station connue. L inventaire peut etre incomplet ; pas une mesure de disponibilite des voitures.'),
    'evidence':('Solidite des donnees','Violet : estimations et proxys a valider. Gris : donnees insuffisantes. Aucun indicateur de precision statistique invente.')}


HEAT_GRADIENT={0.0:'#245db5',.25:'#22a7c7',.5:'#f0d447',.75:'#ed8537',1.0:'#bb2345'}


def heat_intensities(weights):
    """Echelle log relative au perimetre ; zeros et manquants sans chaleur."""
    values=np.asarray(weights,dtype=float)
    positive=np.isfinite(values)&(values>0)
    result=np.zeros(len(values),dtype=float)
    if positive.any():
        logged=np.log1p(values[positive])
        result[positive]=np.minimum(logged/max(float(np.quantile(logged,.99)),1e-12),1)
    return result


def add_known_stations(m,stations,show=True):
    import folium
    from folium.plugins import FastMarkerCluster
    layer=folium.FeatureGroup(name='Stations Citiz connues (bleu)',show=show).add_to(m)
    FastMarkerCluster([[float(r.latitude),float(r.longitude),html.escape(str(r.name))] for r in stations.itertuples()],control=False,
        icon_create_function="function(c){return L.divIcon({html:'<div style=\"background:#2367a2;color:white;border:2px solid white;border-radius:50%;width:28px;height:28px;line-height:28px;text-align:center\">'+c.getChildCount()+'</div>',className:'citiz-existing-cluster',iconSize:[32,32]});}",
        callback="function(row){return L.marker([row[0],row[1]],{icon:L.divIcon({html:'<span style=\"background:#2367a2;color:white;border:2px solid white;border-radius:4px;padding:2px 4px;font:bold 12px Arial\">C</span>',className:'citiz-existing',iconSize:[22,22]})}).bindPopup('Station Citiz connue<br>'+row[2]);}").add_to(layer)
    return layer


def fit_study_bounds(m,data):
    located=data.dropna(subset=['latitude','longitude'])
    if located.empty: return
    bounds=[[float(located.latitude.min()),float(located.longitude.min())],
            [float(located.latitude.max()),float(located.longitude.max())]]
    m._citiz_study_bounds=bounds
    m.fit_bounds(bounds,max_zoom=12,padding=[24,24])
    import folium
    name=m.get_name()
    # Le conteneur Fabric et le panneau BI peuvent changer de largeur apres rendu.
    m.get_root().script.add_child(folium.Element(f"window.addEventListener('load',()=>setTimeout(()=>{{{name}.invalidateSize();{name}.fitBounds({json.dumps(bounds)},{{maxZoom:12,padding:[24,24]}});}},250));"))


def map_availability(ranked,cells,theme):
    data=ranked if cells is None or theme in ['priority','evidence'] else cells
    located=data.latitude.notna()&data.longitude.notna()
    values=pd.Series(1.,index=data.index) if theme=='evidence' else data.priority_score if theme=='priority' else thematic_values(ranked,cells,theme).map_value
    known=located&np.isfinite(values)
    return dict(total=len(data),geocoded=int(located.sum()),available=int(known.sum()))


def thematic_values(ranked,cells,theme):
    """Variables cartographiees distinctes du score. Ne modifie pas le classement."""
    if theme not in MAP_THEMES: raise ValueError('Carte inconnue : '+str(theme))
    data=(ranked if cells is None else cells).copy()
    def numeric(name):
        return pd.to_numeric(data[name],errors='coerce') if name in data else pd.Series(np.nan,index=data.index)
    if cells is None:
        target=numeric('uncovered_licensed_adults_no_car_estimate')
        population=numeric('population')
        transit=(numeric('population_far_stops')/population.where(population>0)).clip(0,1)
        coverage=(1-numeric('uncovered_population')/population.where(population>0)).clip(0,1)
    else:
        target=numeric('licensed_adults_no_car_estimate')
        covered=data['citiz_covered'] if 'citiz_covered' in data else None
        if covered is not None: target=target.where(~covered.fillna(True).astype(bool),0).where(covered.notna())
        population=numeric('population')
        distance=numeric('nearest_stop_m')
        transit=distance.gt(400).astype(float).where(distance.notna())
        coverage=data['citiz_covered'].astype(float) if 'citiz_covered' in data else numeric('missing_coverage')
    data['map_value']=target.clip(lower=0) if theme=='target' else 100*(transit if theme=='transit' else coverage)
    data['map_order']=population if theme in ['transit','citiz'] else target
    data['map_heat_weight']=target if theme=='target' else target*transit if theme=='transit' else population*coverage
    return data.replace([np.inf,-np.inf],np.nan)


def _map_travel_controls(m):
    import folium
    uid=m.get_name()
    m.get_root().header.add_child(folium.Element('''<style>
    .leaflet-tile-pane{filter:grayscale(1) contrast(.94) brightness(1.04)}
    .leaflet-container{font:12px "Segoe UI",Arial,sans-serif;background:#edf1f2}
    .leaflet-control-layers,.leaflet-bar{border:1px solid #dce4e6!important;border-radius:7px!important;box-shadow:0 2px 8px #183f4812!important}
    .leaflet-popup-content{font:12px "Segoe UI",Arial,sans-serif;line-height:1.65}
    </style>'''))
    m.get_root().script.add_child(folium.Element(f"document.getElementById('{uid}').appendChild(document.getElementById('{uid}_legend'));"))


def _indicator_map(france,ranked,cells,theme):
    import folium
    from folium.plugins import HeatMap,FastMarkerCluster,Fullscreen
    data=thematic_values(ranked,cells,theme).dropna(subset=['latitude','longitude'])
    title,description=MAP_THEMES[theme]
    m=folium.Map(location=[46.7,2.3],zoom_start=5,zoom_snap=.1,tiles='OpenStreetMap',height=540,control_scale=True,prefer_canvas=True)
    m.get_root().height='540px'; Fullscreen(position='topleft').add_to(m)
    folium.map.CustomPane('priority_points',z_index=625,pointer_events=True).add_to(m)
    valid=data.loc[data.map_value.notna()].copy()
    if theme=='target':
        colors=['#d4c5ed','#b09bd8','#8363b6','#563487']
        bounds=[100,500,2000,np.inf] if cells is None else [1,5,20,np.inf]
        labels=['<100','100 a <500','500 a <2000','2000 et plus'] if cells is None else ['<1','1 a <5','5 a <20','20 et plus']
        unit='personnes estimees'
        heat=folium.FeatureGroup(name='Concentration de la cible estimee',show=True).add_to(m)
        weight=valid.map_heat_weight.clip(lower=0)
        intensity=heat_intensities(weight)
        HeatMap([[float(a),float(b),float(w)] for a,b,w in zip(valid.latitude,valid.longitude,intensity) if w>0],
                radius=16,blur=12,min_opacity=.12,max_zoom=5 if cells is None else 9,gradient=HEAT_GRADIENT).add_to(heat)
    elif theme=='transit':
        colors=['#2878a5','#e3c35b','#ed9046','#b52b42']; bounds=[25,50,75,np.inf]
        labels=['0 a <25 %','25 a <50 %','50 a <75 %','75 a 100 %']; unit='% de population a plus de 400 m d un arret publie'
    else:
        colors=['#edb46d','#b6cdb0','#60a5a0','#087f70']; bounds=[25,50,75,np.inf]
        labels=['0 a <25 %','25 a <50 %','50 a <75 %','75 a 100 %']; unit='% de population proche d une station connue' if cells is None else '% : carreau proche d une station connue'
    points=folium.FeatureGroup(name=title,show=True).add_to(m)
    # Volumes pour rendre les grandes cibles visibles, jamais un bonus rural.
    shown=valid.sort_values('map_order',ascending=False,na_position='last').head(600)
    shown=shown.sort_values('map_value',ascending=True,kind='stable')
    for r in shown.itertuples():
        color=next(c for b,c in zip(bounds,colors) if r.map_value<b)
        name=str(getattr(r,'commune',getattr(r,'commune_code','Carreau')))
        identifier=str(getattr(r,'commune_code',getattr(r,'cell_id','')))
        value=f'{r.map_value:,.0f}' if theme=='target' else f'{r.map_value:.1f}'
        popup=(f'<b>{html.escape(name)}</b><br>{html.escape(identifier)}<br><b>{value} {html.escape(unit)}</b><br>'
               f'{html.escape(description)}<br>Indicateur descriptif ; aucun changement des poids ou du score.')
        marker=folium.CircleMarker([r.latitude,r.longitude],radius=5,color=color,fill=True,fill_color=color,
                                   fill_opacity=.85,weight=1,tooltip=f'{name} · {value}',popup=folium.Popup(popup,max_width=360))
        marker.options['pane']='priority_points'; marker.add_to(points)
    missing=folium.FeatureGroup(name='Indicateur manquant - pas zero',show=True).add_to(m)
    for r in data.loc[data.map_value.isna()].head(600).itertuples():
        folium.CircleMarker([r.latitude,r.longitude],radius=3,color='#77838c',fill=True,
                            tooltip=f"{getattr(r,'commune',getattr(r,'commune_code','Carreau'))} : indicateur manquant").add_to(missing)
    stations=france['stations']
    if len(data) and (cells is not None or len(ranked)<5000):
        stations=stations.loc[stations.latitude.between(data.latitude.min()-.1,data.latitude.max()+.1)&stations.longitude.between(data.longitude.min()-.1,data.longitude.max()+.1)]
    fit_study_bounds(m,data)
    add_known_stations(m,stations,show=theme=='citiz')
    folium.LayerControl(collapsed=True).add_to(m)
    swatches=''.join(f'<div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:{c};margin-right:7px"></span>{label}</div>' for c,label in zip(colors,labels))
    foot=('Chaleur bleu → jaune → rouge : concentration relative, echelle log ; accumulation des voisins. Points violets : volumes estimes. ' if theme=='target' else '')
    foot+=('Points : 600 plus grandes cibles estimees du perimetre. ' if theme=='target' else 'Points : 600 communes ou carreaux les plus peuples du perimetre. ')
    foot+='Couleur selon l indicateur ; filtrer pour explorer les autres communes. Gris : manquant.'
    m.get_root().html.add_child(folium.Element(f'<div id="{m.get_name()}_legend" style="position:absolute;bottom:76px;left:14px;z-index:999;background:white;padding:10px;border-radius:8px;box-shadow:0 2px 8px #0003;font:11px Arial;line-height:1.6;max-width:230px"><details><summary style="cursor:pointer"><b>Legende · {html.escape(title)}</b></summary>{html.escape(unit)}{swatches}<div style="font-size:11px;color:#52606b">{foot}</div></details></div>'))
    _map_travel_controls(m)
    return m


def france_map(france, ranked, selected, cells=None, evidence=False,theme='priority'):
    if evidence: theme='evidence'  # compatibilite des anciens appels
    if theme not in MAP_THEMES: raise ValueError('Carte inconnue : '+str(theme))
    if theme in ['target','transit','citiz']: return _indicator_map(france,ranked,cells,theme)
    evidence=theme=='evidence'
    import folium
    from folium.plugins import HeatMap, FastMarkerCluster, Fullscreen
    m=folium.Map(location=[46.7,2.3],zoom_start=5,zoom_snap=.1,tiles='OpenStreetMap',height=540,
                 control_scale=True,prefer_canvas=True)
    m.get_root().height='540px'
    Fullscreen(position='topleft').add_to(m)
    # Les marqueurs de score doivent rester au-dessus du canvas de chaleur.
    folium.map.CustomPane('priority_points',z_index=625,pointer_events=True).add_to(m)
    national=cells is None
    frame=ranked.dropna(subset=['latitude','longitude'])
    heat=folium.FeatureGroup(name='Chaleur des priorites (communes)' if national else 'Besoin potentiel (carreaux 200 m)',show=not evidence).add_to(m)
    if national:
        values=frame.dropna(subset=['priority_score']).copy()
        target='uncovered_gap_licensed_adults_estimate' if 'uncovered_gap_licensed_adults_estimate' in values else 'uncovered_gap_no_car_proxy'
        weight=values[target].clip(lower=0)*values.priority_score/100
    else:
        values=cells.dropna(subset=['no_car_households_proxy']).copy()
        target='licensed_adults_no_car_estimate' if 'licensed_adults_no_car_estimate' in values else 'no_car_households_proxy'
        weight=values[target]*values.transit_gap_proxy*(~values.citiz_covered.fillna(True).astype(bool))
    intensity=heat_intensities(weight)
    HeatMap([[float(a),float(b),float(w)] for a,b,w in zip(values.latitude,values.longitude,intensity) if w>0],
            radius=16 if national else 14,blur=12,min_opacity=.12,max_zoom=5 if national else 9,
            gradient=HEAT_GRADIENT).add_to(heat)
    points=folium.FeatureGroup(name='Territoires a etudier' if national else 'Emplacements proposes - parking a verifier').add_to(m)
    chosen_ids=set(selected.commune_code if national else selected.candidate_id)
    detail_cols=['commune','priority_score','cost_total_eur','points_age','cost_penalty']
    display_frame=pd.concat([frame.loc[frame.priority_score.notna()].head(250),selected]).drop_duplicates('commune_code' if national else 'candidate_id')
    # En dezoom, les voisins se recouvrent : dessiner les fortes priorites en dernier.
    display_frame=display_frame.sort_values('priority_score',ascending=True,kind='stable')
    for r in display_frame.itertuples():
        identifier=r.commune_code if national else r.candidate_id
        chosen=identifier in chosen_ids
        if national:
            detail=(f"Commune {html.escape(r.commune_code)} · {html.escape(r.department_name)}<br>"
                    f"Menages sans voiture du RP2022 : {r.no_car_households_rp2022:,.0f}<br>"
                    f"Menages sans voiture hors couverture Citiz (proxy) : {r.uncovered_no_car_proxy:,.0f}<br>"
                    f"Cible permis B sans vehicule (estimation EMP2019) : {getattr(r,'uncovered_licensed_adults_no_car_estimate',np.nan):,.0f}<br>"
                    "Centre de commune : ni emplacement ni habitants gagnes par une station.")
        else:
            detail=(f"Habitants du departement nouvellement a moins de 400 m : {r.new_population:,.0f}<br>"
                    f"Menages sans voiture (proxy) : {r.new_no_car_households_proxy:,.0f}<br>"
                    f"Station Citiz connue la plus proche : {getattr(r,'nearest_existing_citiz_m',np.nan):,.0f} m<br>"
                    "Centre hors exclusion Citiz de 400 m (seuil heuristique).<br>"
                    "Centre de carreau ; distance aerienne ; parking a verifier.")
        cost_text=f'{r.cost_total_eur:,.0f} EUR' if np.isfinite(r.cost_total_eur) and getattr(r,'cost_source','') else 'non documente'
        penalty_text=f'{r.cost_penalty:.1f} points' if np.isfinite(r.cost_penalty) else 'non calculee'
        popup=(f"<b>{html.escape(str(r.commune))}</b><br>Score {r.priority_score:.1f}/100"
               f"<br>{detail}<br>Cout sur horizon documente : {cost_text}"
               f"<br>Reference cout : {html.escape(str(getattr(r,'cost_source','') or 'non renseignee'))}"
               f"<br>Penalite TC deja proches : {getattr(r,'transit_coverage_penalty',0):.1f} points"
               f"<br>Penalite cout : {penalty_text} · bonus 25–39 : {r.points_age:.1f}"
               f"<br>Solidite : {html.escape(str(getattr(r,'evidence_status','modele_non_valide')))}"
               f"<br>Part de carreaux imputes : {getattr(r,'imputed_cell_share',np.nan):.1%} (pas part de population)"
               "<br>Usage occasionnel, horaires TC et parking : a documenter. Permis : estimation d'enquete, pas registre local actuel.")
        fill_color='#7964aa' if evidence else priority_color(r.priority_score)
        marker=folium.CircleMarker([r.latitude,r.longitude],radius=9 if chosen else 6,
                            color='#087f70' if chosen else fill_color,weight=3 if chosen else 2,
                            fill=True,fill_color=fill_color,fill_opacity=.9,
                            tooltip=f'{r.commune} · {r.priority_score:.1f}',popup=folium.Popup(popup,max_width=390))
        marker.options['pane']='priority_points'
        marker.add_to(points)
    stations=france['stations']
    # Filtre uniquement visuel local: le moteur de couverture utilise toutes les stations.
    if len(frame) and (cells is not None or len(frame)<5000):
        extent=cells if cells is not None else frame
        stations=stations.loc[stations.latitude.between(extent.latitude.min()-.1,extent.latitude.max()+.1)&stations.longitude.between(extent.longitude.min()-.1,extent.longitude.max()+.1)]
    add_known_stations(m,stations,show=True)
    if national:
        missing=folium.FeatureGroup(name='Permis ou donnees fines manquants - pas de score',show=True).add_to(m)
        for r in frame.loc[frame.priority_score.isna()].itertuples():
            folium.CircleMarker([r.latitude,r.longitude],radius=3,color='#77838c',fill=True,
                                tooltip=f'{r.commune} : donnees insuffisantes',
                                popup=f"Commune conservee dans le perimetre. Permis : {html.escape(str(getattr(r,'license_status','non renseigne')))}. Grille : {html.escape(str(getattr(r,'grid_status','non renseignee')))}. Aucun besoin suppose nul.").add_to(missing)
    fit_study_bounds(m,cells if cells is not None else frame)
    folium.LayerControl(collapsed=True).add_to(m)
    swatches=('Violet : estimations et proxys, validation requise' if evidence else ''.join(f'<div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:{color};margin-right:7px"></span>{label}</div>' for _,color,label in PRIORITY_COLORS))
    uid=m.get_name()
    m.get_root().html.add_child(folium.Element(
        f'<div id="{uid}_legend" style="position:absolute;bottom:76px;left:14px;z-index:999;background:white;padding:10px;border-radius:8px;box-shadow:0 2px 8px #0003;font:11px Arial;line-height:1.6;max-width:230px"><details><summary style="cursor:pointer"><b>Legende de la carte</b></summary>'+
        ('<b>Solidite des donnees</b><br>' if evidence else '<b>Territoires : score de priorite /100</b>')+swatches+
        '<div style="color:#77838c">Gris : donnees insuffisantes</div>'
        '<div>Contour vert : retenu sous budget</div>'
        '<div>Carre C / groupe bleu : Citiz existant</div>'
        '<div style="font-size:11px">Chaleur bleu → jaune → rouge : concentration relative, echelle log, accumulation des voisins ; pas le score /100.</div>'
        '<div style="max-width:230px;font-size:11px;color:#52606b">Seuils fixes entre scenarios. Points = centres des communes ou carreaux ; top 250 scores calculables, zero inclus.</div></details></div>'))
    _map_travel_controls(m)
    return m


def territory_metrics(ranked,cells=None):
    """Agregats sur les populations connues, jamais sur les rayons qui se recouvrent."""
    data=ranked if cells is None else cells
    def numeric(name):
        return pd.to_numeric(data[name],errors='coerce') if name in data else pd.Series(np.nan,index=data.index)
    pop=numeric('population')
    if cells is None:
        far=numeric('population_far_stops')
        covered=pop-numeric('uncovered_population')
        target=numeric('uncovered_licensed_adults_no_car_estimate')
    else:
        distance=numeric('nearest_stop_m')
        far=pop.where(distance.gt(400),0).where(distance.notna())
        flag=data.citiz_covered if 'citiz_covered' in data else pd.Series(pd.NA,index=data.index)
        covered=pop.where(flag.eq(True).fillna(False),0).where(flag.notna())
        target=numeric('licensed_adults_no_car_estimate').where(flag.eq(False).fillna(False),0).where(flag.notna())
    def share(values):
        known=pop.notna()&values.notna()
        denominator=pop.where(known).sum(min_count=1)
        numerator=values.where(known).sum(min_count=1)
        return (100*numerator/denominator if np.isfinite(denominator) and denominator>0 else np.nan,numerator)
    far_share,far_population=share(far)
    citiz_share,citiz_population=share(covered)
    return dict(target=target.sum(min_count=1),population=pop.sum(min_count=1),far_share=far_share,
                far_population=far_population,citiz_share=citiz_share,citiz_population=citiz_population)


UI_STYLE='''<style>
.cb,.cb-report{font:13px "Segoe UI",Arial,sans-serif;color:#203d43;background:#f6f8f9;padding:16px;border:1px solid #e6ecee;border-radius:10px;box-sizing:border-box;white-space:normal}
.cb *,.cb-report *{box-sizing:border-box}.cb h3,.cb h4,.cb p{margin:0 0 7px}.cb h3{font-size:17px;font-weight:600}.cb h4{font-size:12px;font-weight:600}.cb small{display:block;font-size:11px;color:#657b80;line-height:1.55}
.cb-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}.cb-head small{font-size:11px}.cb-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:14px}.cb-card{background:white;border:1px solid #e1e8eb;border-radius:8px;padding:13px 14px;border-top:2px solid #168487}.cb-label{font-size:10px;font-weight:600;color:#61797e}.cb-card strong{display:block;font-size:28px;line-height:1.45;font-weight:600;letter-spacing:-.6px;color:#163f48}
.cb-body{display:grid;grid-template-columns:minmax(0,1fr) 230px;gap:14px}.cb-map{background:white;border:1px solid #e1e8eb;border-radius:8px;overflow:hidden;min-width:0}.cb-maphead{padding:12px 14px;border-bottom:1px solid #edf1f2}.cb-maphead p{font-size:11px;color:#657b80;margin:0;line-height:1.5}.cb-map iframe{display:block;border:0!important}
.cb-side{display:flex;flex-direction:column;gap:12px;max-height:610px;overflow:auto}.cb-side section{background:white;border:1px solid #e1e8eb;border-radius:8px;padding:13px}.cb-side h4{margin-top:2px}.cb-place{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:10px 0;border-top:1px solid #edf1f2}.cb-place>b{font-size:20px;font-weight:600}.cb-place span{min-width:0}.cb-place small{overflow-wrap:anywhere;font-size:10px}.cb-swatches{display:flex;flex-wrap:wrap;gap:6px 14px;margin:10px 0 6px}.cb-swatches span{font-size:10px;color:#61797e}.cb-swatches i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}.cb-rule{border-left:2px solid #168487!important}.cb-rule b{display:block;margin-bottom:5px;font-size:12px}
.cb-term{display:grid;grid-template-columns:1fr auto;gap:4px;font-size:10px;margin:9px 0}.cb-term>div{grid-column:1/-1;background:#edf2f3;height:5px;border-radius:4px}.cb-term i{display:block;height:5px;background:#218b91;border-radius:4px}.cb-footer{font-size:10px;color:#71858a;margin-top:12px}.cb facts{display:block}.cb-fact{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid #eef2f3;font-size:11px}.cb-fact b{font-weight:500;text-align:right}.cb summary,.cb-report summary{cursor:pointer;font-size:11px;font-weight:600;color:#305b64;padding:4px 0}.cb details p{font-size:11px;line-height:1.65;margin:8px 0;color:#657b80}
.cb-report{overflow-x:auto;line-height:1.65}.cb-report h3{font-size:16px;font-weight:600;margin:15px 0 10px}.cb-report h4{font-size:13px}.cb-report p,.cb-report details{color:#5e747a;font-size:12px}.cb-report table{border-collapse:collapse;width:100%;font-size:11px;border:none;background:white;margin:12px 0}.cb-report th{background:#edf3f4;color:#24484f;font-weight:600;text-align:left;position:sticky;top:0}.cb-report th,.cb-report td{padding:9px 11px;border:0;border-bottom:1px solid #e4ebee;vertical-align:top}.cb-report tr:nth-child(even){background:#f8fafb}.cb-report a{color:#087f80}
.cb-analysis-table{background:white;border:1px solid #e1e8eb;border-radius:8px;padding:12px 14px;margin:12px 0}.cb-analysis-table summary{font-size:13px!important}.cb-analysis-table summary span{font-size:10px;color:#71858a;font-weight:400;margin-left:12px}.cb-table-scroll{max-height:500px;overflow:auto}.cb-table-scroll th{position:static;white-space:normal;min-width:100px}.cb-table-scroll td{white-space:nowrap}.cb-table-scroll thead tr:first-child th{border-bottom:2px solid #cbdcde}
@media(max-width:900px){.cb-body{grid-template-columns:1fr}.cb-side{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));max-height:none}.cb-cards{gap:8px}.cb-card{padding:10px}.cb-card strong{font-size:24px}}
@media(max-width:540px){.cb-cards{grid-template-columns:1fr}.cb-side{grid-template-columns:1fr}.cb-head{align-items:flex-start}}
</style>'''


def report_panel(content):
    return UI_STYLE+'<div class="cb-report">'+content+'</div>'


def dashboard_html(france,ranked,selected,m,cells,theme,scope_label,expert=False):
    """Habillage BI commun : indicateurs, carte centrale et lecture contextuelle."""
    esc=lambda text:html.escape(str(text))
    number=lambda value:f'{value:,.0f}'.replace(',',' ') if np.isfinite(value) else 'Non disponible'
    title,description=MAP_THEMES[theme]
    valid=ranked.loc[ranked.priority_score.notna()]
    availability=map_availability(ranked,cells,theme)
    metrics=territory_metrics(ranked,cells)
    def card(label,value,sub):
        return f'<div class="cb-card"><div class="cb-label">{esc(label)}</div><strong>{esc(value)}</strong><small>{esc(sub)}</small></div>'
    percent=lambda value:f'{value:.1f} %' if np.isfinite(value) else 'Non disponible'
    cards=card('Permis B, sans vehicule',number(metrics['target']),'Estimation hors couverture Citiz')
    cards+=card('Eloignes des arrets',percent(metrics['far_share']),f'{number(metrics["far_population"])} habitants a plus de 400 m')
    cards+=card('Proches de Citiz',percent(metrics['citiz_share']),f'{number(metrics["citiz_population"])} habitants a moins de 400 m')
    top=valid.sort_values('priority_score',ascending=False).head(3)
    entries=''.join(f'<div class="cb-place"><span><b>{esc(r.commune)}</b><small>{esc(getattr(r,"candidate_id","")) if expert else "Carreau a verifier" if cells is not None else esc(getattr(r,"department_name","Commune"))}</small></span><b style="color:{priority_color(r.priority_score)}">{r.priority_score:.1f}</b></div>' for r in top.itertuples())
    if not entries: entries='<p>Aucun score calculable ; absence de donnees ne signifie pas absence de besoin.</p>'
    extras=''
    if expert:
        if len(top):
            first=top.iloc[0]
            bars=''
            for label,keys in [('Cible permis',['points_no_car']),('Manque TC',['points_transit','points_transit_gap']),('Population',['points_population','points_new_population']),('Social',['points_equity']),('Age 25–39',['points_age'])]:
                key=next((key for key in keys if key in first.index),None)
                value=first[key] if key else np.nan
                if np.isfinite(value): bars+=f'<div class="cb-term"><span>{esc(label)}</span><b>{value:.1f} pts</b><div><i style="width:{min(max(value,0),100)}%"></i></div></div>'
            extras+=f'<section><h4>Decomposition · {esc(first.commune)}</h4>{bars}<small>Avant penalites TC ({first.get("transit_coverage_penalty",0):.1f} pts) et couts documentes.</small></section>'
        extras+=f'<section><h4>Qualite et couverture</h4><p>{number(len(valid))} scores calculables / {number(len(ranked))}<br>{number(ranked.priority_score.isna().sum())} scores absents</p><small>Inventaire Citiz partiel possible. Proximite TC sans horaires. Estimation locale du permis, pas registre actuel.</small></section>'
    if theme=='priority':
        swatches=''.join(f'<span><i style="background:{color}"></i>{esc(label)}</span>' for _,color,label in PRIORITY_COLORS)
        reading='Points : score /100. Chaleur : concentration relative bleu → jaune → rouge.'
    elif theme=='evidence':
        swatches='<span><i style="background:#7964aa"></i>Modele a valider</span><span><i style="background:#77838c"></i>Donnees absentes</span>'
        reading='Couleur : statut des donnees, pas une probabilite de precision.'
    elif theme=='target':
        swatches='<span><i style="background:#b09bd8"></i>Cible estimee</span><span><i style="background:#77838c"></i>Valeur absente</span>'
        reading='Points violets : volume estime, voir les seuils dans Legende. Chaleur : concentration relative bleu → jaune → rouge.'
    else:
        colors=['#2878a5','#e3c35b','#ed9046','#b52b42'] if theme=='transit' else ['#edb46d','#b6cdb0','#60a5a0','#087f70']
        swatches=''.join(f'<span><i style="background:{color}"></i>{label}</span>' for color,label in zip(colors,['<25 %','25 a <50 %','50 a <75 %','75 a 100 %']))
        reading='Couleur : part de population eloignee des arrets.' if theme=='transit' else 'Couleur : part de population proche du Citiz connu.'
    facts=(f'<div class="cb-fact"><span>Population etudiee</span><b>{number(metrics["population"])}</b></div>'
           '<div class="cb-fact"><span>Distance aux arrets</span><b>A vol d’oiseau</b></div>'
           '<div class="cb-fact"><span>Horaires / frequences</span><b>Non renseignes</b></div>'
           '<div class="cb-fact"><span>Disponibilite Citiz</span><b>Non mesuree</b></div>')
    sources=('<details><summary>Sources et limites</summary><p>Population : Filosofi2021. Motorisation : RP2022. Permis : EMP2019, repartition locale estimee. '
             'Arrets : inventaire PAN, couverture possiblement incomplete. Stations : flux GBFS Citiz, inventaire possiblement incomplet. '
             'Les seuils de 400 m sont a vol d’oiseau. Aucun budget ou cout suppose.</p></details>')
    side=(f'<section><h4>Priorites a examiner <small>Score de besoin /100</small></h4>{entries}'
          '<small>Stationnement et cheminements a verifier.</small></section>'+extras+
          f'<section><h4>Transports et donnees</h4>{facts}{sources}</section>'+
          ('<section class="cb-rule"><b>Implantation locale</b><small>Centres a 400 m ou moins des stations connues exclus. Seuil heuristique.</small></section>' if expert else ''))
    return (UI_STYLE+f'<div class="cb" data-view="{"expert" if expert else "simple"}"><div class="cb-head"><div><h3>{esc(scope_label)}</h3><small>{number(len(ranked))} {"centres candidats" if cells is not None else "communes"} · {number(availability["available"])} valeurs cartographiables</small></div></div>'
            f'<div class="cb-cards">{cards}</div><div class="cb-body"><div class="cb-map"><div class="cb-maphead"><h4>{esc(title)}</h4><p>{esc(description)}</p><div class="cb-swatches">{swatches}</div><small>{reading}</small></div>{m._repr_html_()}</div><aside class="cb-side">{side}</aside></div>'
            '<div class="cb-footer">Parts calculees sur la population renseignee. Cible permis estimee ; pas une prevision de clients. C : station Citiz connue.</div></div>')


def local_department(france, department, scenario, costs=None):
    """Recalcul du gain marginal sur les habitants DU departement uniquement."""
    if department not in STUDY_DEPARTMENTS: raise ValueError('Choisir un departement de France metropolitaine hors Corse.')
    # Dans le notebook, ces definitions viennent de la cellule moteur V1.
    try:
        from citiz_v1 import Config, rank_and_select
    except ImportError:
        Config=globals()['Config']; rank_and_select=globals()['rank_and_select']
    files=sorted((Path(france['workdir'])/'cells'/department).glob('*.csv'))
    if not files and 'restore_france_cache' in globals():
        restore_france_cache(france['workdir'],department=department)
        files=sorted((Path(france['workdir'])/'cells'/department).glob('*.csv'))
    if not files: raise ValueError('Pas de grille fine disponible pour ce departement. La commune reste visible dans la vue France.')
    data=pd.concat([pd.read_csv(p,dtype={'commune_code':str,'department':str,'region':str}) for p in files],ignore_index=True).drop_duplicates('cell_id')
    # Eviter de recalculer sur une copie partielle d'un departement cherche par nom.
    data=data.dropna(subset=['no_car_rate']).copy()
    if data.empty: raise ValueError('Motorisation absente : emplacements non calculables.')
    # Coordonnees cartesiennes locales: valables aussi en outre-mer et en Corse.
    transform=Transformer.from_crs(4326,f'+proj=aeqd +lat_0={data.latitude.mean()} +lon_0={data.longitude.mean()} +datum=WGS84 +units=m',always_xy=True)
    data['x'],data['y']=transform.transform(data.longitude.to_numpy(),data.latitude.to_numpy())
    data['transit_gap']=data.transit_gap_proxy
    # Recalcul avec l'inventaire courant, toutes communes et limites comprises.
    from scipy.spatial import cKDTree
    stations=france['stations'].dropna(subset=['latitude','longitude'])
    tree=cKDTree(sphere_xyz(stations.latitude,stations.longitude)) if len(stations) else None
    data['nearest_citiz_m']=nearest_metres(tree,data.latitude,data.longitude)
    data['citiz_covered']=data.nearest_citiz_m.le(400).where(data.nearest_citiz_m.notna())
    if 'overview' in france and 'license_coefficient' in france['overview']:
        coefficients=france['overview'].set_index('commune_code').license_coefficient
        data['licensed_adults_no_car_estimate']=data.no_car_households_proxy*data.commune_code.map(coefficients)
    common_cost=(scenario.site_cost_eur is not None and bool(scenario.cost_source.strip()))
    documented_overrides={code:value for code,value in (costs or {}).items() if isinstance(value,tuple) and str(value[1]).strip()}
    finance=(scenario.budget_eur is not None and scenario.budget_source.strip() and scenario.horizon_years is not None and (common_cost or bool(documented_overrides)))
    # Zero est un neutre algorithmique pour calculer le BESOIN, jamais un prix.
    cfg=Config(budget_eur=scenario.budget_eur if finance else 0,max_stations=scenario.max_sites if finance else 0,
               setup_eur=scenario.site_cost_eur if finance and common_cost else 0,vehicle_eur=0,annual_operation_eur=0,
               horizon_years=scenario.horizon_years if finance else 1,
               budget_source=scenario.budget_source if finance else '',cost_source=(scenario.cost_source or 'references_par_site') if finance else '',
               cost_reference_eur=scenario.budget_eur if finance and scenario.budget_eur>0 else 1,
               age_bonus_max=scenario.age_bonus,max_cost_penalty=scenario.cost_penalty_weight if finance else 0,
               no_car_weight=scenario.no_car_weight,transit_weight=scenario.transit_weight,
               population_weight=scenario.population_weight,equity_weight=scenario.equity_weight,
               transit_coverage_penalty=scenario.transit_coverage_penalty)
    raw_costs={} if common_cost else {code:np.nan for code in data.cell_id}
    for code,value in (costs or {}).items():
        raw_costs[code]=value[0] if isinstance(value,tuple) and str(value[1]).strip() else np.nan
    ranked,selected,_=rank_and_select(data,cfg,raw_costs if finance else None)
    def source_for(code):
        if not finance: return ''
        if code in (costs or {}): return str(documented_overrides.get(code,('',''))[1]).strip()
        return scenario.cost_source.strip() if common_cost else ''
    ranked['cost_source']=ranked.candidate_id.map(source_for)
    selected['cost_source']=selected.candidate_id.map(source_for)
    ranked['budget_source']=scenario.budget_source.strip()
    selected['budget_source']=scenario.budget_source.strip()
    if not finance:
        for column in ['cost_total_eur','cost_penalty','cost_per_new_resident_eur']:
            ranked[column]=np.nan
        ranked['cost_status']='non_documente'
        ranked['score_status']='besoin_hors_couts_budget_non_documente'
    if 'annotate_evidence' in globals():
        ranked=annotate_evidence(ranked); selected=annotate_evidence(selected)
    return ranked,selected,data


def show_france_interactive(france,render=True):
    import ipywidgets as w
    from IPython.display import display as ipython_display, HTML, update_display
    # Fabric fournit son propre display pour enregistrer les widgets interactifs.
    # Le rendu HTML de carte conserve le display IPython et son display_id.
    widget_display=globals().get('display',ipython_display)
    import uuid
    base=france['overview'].loc[france['overview'].region.isin(STUDY_REGIONS)].copy()
    region_options=[('Metropole hors Corse','')]+sorted({(r.region_name,str(r.region)) for r in base.itertuples() if pd.notna(r.region)})
    field_layout=lambda:w.Layout(width='32%',min_width='280px',flex='1 1 280px',margin='0 8px 8px 0',height='28px')
    field_style={'description_width':'76px'}
    region=w.Dropdown(options=region_options,description='Region',layout=field_layout(),style=field_style)
    department=w.Dropdown(options=[('Tous les departements','')],description='Departement',layout=field_layout(),style=field_style)
    search=w.Text(description='Commune',placeholder='Nom ou code INSEE',continuous_update=True,layout=field_layout(),style=field_style)
    mode=w.Dropdown(options=[('Communes','national')],value='national',description='Echelle',
                    layout=field_layout(),style=field_style)
    presentation=w.ToggleButtons(options=[('Vue simple','simple'),('Analyse complete','expert')],value='simple',
                                 style={'button_width':'145px'},layout=w.Layout(width='310px'))
    view_simple=w.Button(description='Vue simple',layout=w.Layout(width='140px'))
    view_expert=w.Button(description='Analyse complete',layout=w.Layout(width='155px'))
    view_simple.on_click(lambda _:setattr(presentation,'value','simple'))
    view_expert.on_click(lambda _:setattr(presentation,'value','expert'))
    view_switch=w.HBox([view_simple,view_expert],layout=w.Layout(width='310px'))
    map_view=w.Dropdown(options=[(label,key) for key,(label,_) in MAP_THEMES.items()],value='priority',description='Carte',layout=field_layout(),style=field_style)
    budget=w.Text(value='',placeholder='Non renseigne',description='Budget EUR',continuous_update=True)
    cost=w.Text(value='',placeholder='Non renseigne',description='Cout/site EUR',continuous_update=True)
    budget_source=w.Text(value='',placeholder='Reference du budget valide',description='Source budget',continuous_update=True,layout=w.Layout(width='600px'))
    cost_source=w.Text(value='',placeholder='Devis, tarif ou reference + horizon commun',description='Source cout',continuous_update=True,layout=w.Layout(width='600px'))
    horizon=w.Text(value='',placeholder='Non renseigne',description='Horizon (ans)',continuous_update=True)
    max_sites=w.IntSlider(value=20,min=0,max=100,step=1,description='Max sites',continuous_update=False)
    weights=[w.IntSlider(value=value,min=0,max=100,description=label,continuous_update=False,
                         style={'description_width':'150px'},layout=w.Layout(width='350px'))
             for label,value in [('Permis + sans voiture',35),('Eloignement TC',35),('Population',20),('Contexte social',5)]]
    age=w.IntSlider(value=5,min=0,max=5,description='Bonus 25–39',continuous_update=False)
    penalty=w.IntSlider(value=25,min=0,max=50,description='Penalite cout',continuous_update=False)
    tc_penalty=w.IntSlider(value=35,min=0,max=60,description='TC deja proches',continuous_update=False,
                          style={'description_width':'150px'},layout=w.Layout(width='350px'))
    apply=w.Button(description='Appliquer',layout=w.Layout(width='112px'))
    apply.add_class('citiz-primary')
    reset=w.Button(description='Reinitialiser',tooltip='Reinitialiser les filtres',layout=w.Layout(width='110px'))
    export=w.Button(description='Exporter CSV',layout=w.Layout(width='128px'))
    status=w.HTML(); kpis=w.HTML(); canvas=w.HTML(); table=w.HTML(); analysis=w.HTML(); usages=w.HTML()
    state={'busy':False,'last':None,'cells':None,'maps':{},'analysis_tables':{},'content_html':'','map_id':'citiz_france_'+uuid.uuid4().hex,'map_published':False,'ranking_runs':0}
    header=w.HTML("""<div style='font:12px Segoe UI;color:#61797e;padding:5px 4px 14px'>
    <b style='font-size:23px;font-weight:600;color:#17464e'>Citiz</b><span style='margin-left:13px'>Territoires &amp; mobilite</span></div>""",layout=w.Layout(flex='1 1 230px'))
    note="""<details><summary>Definitions, sources et limites du modele</summary><p>France metropolitaine : communes a etudier, pas stations validees.
    Cible permis B sans vehicule estimee avec EMP2019 et RP2022 ; pas registre local.
    Le score emploie la proximite des arrets publies, sans horaires, et une penalite de couverture ajustable. La carte Arrets montre separement la part de population eloignee de plus de 400 m.
    Pas de bonus rural. Bonus experimental 25-39 ans plafonne a 5 points. Les quatre poids principaux sont normalises sur 95 points.
    Sans budget, couts, horizon commun et references : selection financiere desactivee. Aucun montant suppose.
    Detail 200 m : centres de carreaux, distances aeriennes, parking et cheminement a verifier.</p></details>"""
    def render_content():
        if state['last'] is None:
            content='<p>Choisir un perimetre puis recalculer.</p>'
        elif tabs.value==0:
            theme=map_view.value
            scenario,ranked,selected,_,local=state['last']
            m=state['maps'].get(theme)
            if m is None:
                scenario,ranked,selected,_,local=state['last']
                m=france_map(france,ranked,selected,state['cells'],theme=theme)
                state['maps'][theme]=m
            last=list(state['last']); last[3]=m; state['last']=tuple(last)
            title,description=MAP_THEMES[theme]
            availability=map_availability(ranked,state['cells'],theme)
            scope_label=' · '.join(str(x) for x in [region.label,department.label if department.value else '',search.value.strip()] if x)
            if availability['available']==0:
                content=(f'<div style="max-width:950px;padding:20px;background:#fff4dd;border-left:5px solid #d9a52a;font:14px Segoe UI">'
                         f'<h3>Aucune valeur exploitable sur ce perimetre</h3><p>{html.escape(scope_label)} : {availability["total"]} lignes, '
                         f'{availability["geocoded"]} geolocalisees. Aucun score ou indicateur disponible pour cette carte.</p>'
                         '<p>Ce resultat ne signifie pas une absence de besoin. Choisir un autre territoire ou cliquer sur <b>Reinitialiser les filtres</b>.</p></div>')
            else:
                content=dashboard_html(france,ranked,selected,m,state['cells'],theme,scope_label,expert=presentation.value=='expert')
        elif tabs.value==2:
            content=report_panel(kpis.value+note+analysis.value)
        elif tabs.value==3:
            content=report_panel(usages.value)
        else:
            content=''
        state['content_html']=content
        if state['map_published']:
            update_display(HTML(content),display_id=state['map_id'])
    def view_changed(change):
        if state['busy']: return
        render_content()
    def update_scale():
        mode.options=[('Communes','national')]+([('Carreaux 200 m','local')] if department.value else [])
    def update_departments():
        subset=base if not region.value else base.loc[base.region.eq(region.value)]
        old=department.value
        options=[('Tous les departements','')]+sorted({(f'{r.department} · {r.department_name}',str(r.department)) for r in subset.itertuples() if pd.notna(r.department)})
        department.options=options
        if old in [code for _,code in options]: department.value=old
        update_scale()
    def params():
        raw=np.asarray([x.value for x in weights],dtype=float)
        normalized=raw*95/max(raw.sum(),1)
        def amount(text):
            value=text.strip().replace(' ','').replace(',','.')
            return None if not value else float(value)
        return FranceScenario(budget_eur=amount(budget.value),site_cost_eur=amount(cost.value),
                              budget_source=budget_source.value.strip(),cost_source=cost_source.value.strip(),max_sites=max_sites.value,
                              horizon_years=None if not horizon.value.strip() else int(horizon.value.strip()),
                              no_car_weight=normalized[0],transit_weight=normalized[1],population_weight=normalized[2],
                              equity_weight=normalized[3],age_bonus=age.value,cost_penalty_weight=penalty.value,
                              transit_coverage_penalty=tc_penalty.value,
                              region=region.value,department=department.value,search=search.value.strip())
    def recalc(*args):
        if state['busy']: return
        state['busy']=True; apply.disabled=True
        status.value='<p>Recalcul Python en cours…</p>'
        try:
            scenario=params()
            local=mode.value=='local'
            if local and not department.value: raise ValueError('Choisir un departement pour le detail 200 m.')
            overrides_file=Path(france['workdir'])/('site_cost_overrides.csv' if local else 'commune_cost_overrides.csv')
            costs=None
            if overrides_file.exists():
                overrides=pd.read_csv(overrides_file,dtype={'commune_code':str,'candidate_id':str})
                key='candidate_id' if local else 'commune_code'
                if overrides[key].duplicated().any(): raise ValueError('Couts dupliques pour un identifiant.')
                if 'source' not in overrides: raise ValueError('Ajouter la colonne source aux couts saisis.')
                costs={code:(amount,str(source).strip() if pd.notna(source) else '') for code,amount,source in zip(overrides[key],pd.to_numeric(overrides.cost_total_eur,errors='raise'),overrides.source)}
            if local:
                ranked,selected,cells=local_department(france,department.value,scenario,costs)
                if scenario.search:
                    status.value='<p>En detail, le calcul porte sur tout le departement. Vider Commune pour eviter une ambiguite de perimetre.</p>'
            else:
                ranked=france_rank(base,scenario,costs)
                selected=ranked.loc[ranked.selected]; cells=None
            state['ranking_runs']+=1
            m=france_map(france,ranked,selected,cells,theme=map_view.value)
            canvas.value='<p><b>Carte interactive ci-dessous :</b> zoom, couches, fiches au clic et plein ecran. Points colores par score avec seuils fixes. Chaleur relative au territoire affiche : cible estimee eloignee des TC et hors Citiz.</p>'
            total_cost=selected.cost_total_eur.sum()
            financed=(scenario.budget_eur is not None and scenario.budget_source and ranked.cost_penalty.notna().any())
            money=(f"<span><b>{total_cost:,.0f} EUR</b><br>cout des lignes retenues</span><span><b>{scenario.budget_eur-total_cost:,.0f} EUR</b><br>budget restant</span>" if financed else
                   '<span><b>Budget non documente</b><br>selection financiere desactivee</span><span><b>Couts non estimes</b><br>classement des besoins</span>')
            kpis.value=(f"<div style='display:flex;gap:28px;font:14px Segoe UI;padding:18px;background:#eff6f5;border-radius:8px'>"
                        f"<span><b style='font-size:24px'>{len(ranked):,}</b><br>{'candidats 200 m' if local else 'communes explorees'}</span>"
                        f"<span><b style='font-size:24px'>{len(selected) if financed else '—'}</b><br>{'emplacements retenus' if local else 'territoires retenus'}</span>"+money+'</div>')
            common=['commune','priority_score','evidence_status','transit_coverage_penalty','cost_total_eur','cost_source','points_age','cost_penalty']
            extra=['new_population','new_no_car_households_proxy','new_licensed_adults_no_car_estimate'] if local else ['department_name','uncovered_licensed_adults_no_car_estimate','license_status','grid_status']
            table.value=('<h3>Selection sous budget documente</h3>'+selected[common+extra].round(2).to_html(index=False,escape=True,na_rep='Non renseigne') if financed else
                         '<h3>Priorites de besoin — hors couts</h3><p>Selection financiere non calculee : fournir budget, couts et references.</p>'+ranked[common+extra].head(15).round(2).to_html(index=False,escape=True,na_rep='Non renseigne'))
            failures=france['sources'].loc[~france['sources'].status.eq('ok')&~france['sources'].status.str.startswith('inventaire')]
            state['analysis_tables']=build_analysis_tables(france,ranked,cells,territory_metrics)
            analysis.value=analysis_report(state['analysis_tables'],local)
            usages.value=mobility_panel_html(france,ranked) if 'mobility_panel_html' in globals() else '<p>Module usages non charge.</p>'
            state['last']=(scenario,ranked,selected,m,local)
            state['cells']=cells; state['maps']={map_view.value:m}
            render_content()
            status.value=''
        except Exception as error:
            state['last']=None
            status.value=f"<p style='color:#b43c30'>{html.escape(str(error))}</p>"
            kpis.value=''; canvas.value=''; table.value=''; analysis.value=''; usages.value=''
            state['maps']={}; state['cells']=None
            state['analysis_tables']={}
            render_content()
        finally:
            apply.disabled=False; state['busy']=False
    def region_changed(change):
        if state['busy']: return
        state['busy']=True; update_departments(); state['busy']=False; recalc()
    def reset_filters(*args):
        state['busy']=True
        region.value=''; update_departments(); department.value=''; search.value=''; mode.value='national'
        state['busy']=False; recalc()
    def save(*args):
        if state['last'] is None: return
        scenario,ranked,selected,m,local=state['last']
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        folder=Path(france['workdir'])/'scenarios'/stamp; folder.mkdir(parents=True)
        ranked.to_csv(folder/'classement.csv',index=False,encoding='utf-8')
        selected.to_csv(folder/'selection.csv',index=False,encoding='utf-8')
        export_analysis_tables(state['analysis_tables'],folder)
        (folder/'parametres.json').write_text(json.dumps(asdict(scenario),indent=2),encoding='utf-8')
        m.save(str(folder/'carte.html'))
        (folder/'vue_cartographique.json').write_text(json.dumps({'carte':map_view.value,'presentation':presentation.value,'cartes_disponibles':MAP_THEMES},ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'tableau_de_bord.html').write_text(state['content_html'],encoding='utf-8')
        for theme,cached_map in state['maps'].items(): cached_map.save(str(folder/f'carte_{theme}.html'))
        if 'publish_france_files' in globals(): publish_france_files(france,only_scenario=folder)
        status.value=f'<p>Scenario CSV et carte sauvegardes : {html.escape(str(folder))}</p>'
    update_departments()
    region.observe(region_changed,names='value')
    def department_changed(change):
        if state['busy']: return
        state['busy']=True; update_scale(); state['busy']=False; recalc()
    department.observe(department_changed,names='value')
    for control in [mode,max_sites,*weights,age,penalty,tc_penalty]: control.observe(recalc,names='value')
    apply.on_click(recalc); export.on_click(save); reset.on_click(reset_filters)
    for control in [budget_source,cost_source]: control.layout.width='410px'
    settings=w.HBox([w.VBox([w.HTML('<b>Poids du besoin</b>'),*weights,tc_penalty,age]),
                     w.VBox([w.HTML('<b>Scenario financier · sources requises</b>'),budget,cost,horizon,max_sites,penalty,budget_source,cost_source])],
                    layout=w.Layout(flex_flow='row wrap'))
    actions=w.HBox([apply,reset],layout=field_layout())
    actions.layout.padding='0 0 0 84px'
    actions.layout.align_items='center'
    decision=w.HBox([map_view,mode,actions],layout=w.Layout(flex_flow='row wrap',width='100%',margin='0'))
    # Un seul panneau monte : certains rendus Fabric empilent les enfants de Tab.
    panels=[w.VBox([]),settings,w.VBox([]),w.VBox([])]
    tabs=w.ToggleButtons(options=[('Cartes',0),('Parametres',1),('Analyse',2),('Usages et sources',3)],value=0)
    nav_buttons=[]
    for label,index in tabs.options:
        button=w.Button(description=label,layout=w.Layout(width='150px'))
        button.on_click(lambda _,index=index:setattr(tabs,'value',index))
        nav_buttons.append(button)
    tab_bar=w.HBox(nav_buttons,layout=w.Layout(flex_flow='row wrap'))
    panel=w.VBox([panels[0]])
    def update_toolbar():
        decision.children=(map_view,mode,actions)
    def switch_panel(change):
        panel.children=(panels[change['new']],)
        update_view_buttons()
        update_toolbar()
        render_content()
    tabs.observe(switch_panel,names='value')
    map_view.observe(view_changed,names='value')
    expert_nav=w.VBox([])
    def presentation_changed(change):
        tabs.value=0
        update_view_buttons()
        update_toolbar()
        expert_nav.children=(w.HBox([tab_bar,export],layout=w.Layout(flex_flow='row wrap',align_items='center')),) if change['new']=='expert' else ()
        render_content()
    presentation.observe(presentation_changed,names='value')
    def update_view_buttons():
        for button,key in [(view_simple,'simple'),(view_expert,'expert')]:
            active=presentation.value==key
            button.style.button_color='#176f74' if active else '#f4f7f8'
            button.style.text_color='white' if active else '#31545c'
        for index,button in enumerate(nav_buttons):
            button.style.button_color='#176f74' if tabs.value==index else '#f4f7f8'
            button.style.text_color='white' if tabs.value==index else '#31545c'
    for button in [apply,reset,export,view_simple,view_expert,*nav_buttons]:
        button.style.font_family='Segoe UI'
        button.style.font_size='12px'
        button.style.font_weight='500'
        button.layout.border='1px solid #dce5e8'
        button.layout.height='28px'
        # Fabric conserve une hauteur de ligne native de 28 px : le centrage
        # flex evite que bordure et padding repoussent le texte vers le bas.
        button.layout.display='flex'
        button.layout.align_items='center'
        button.layout.justify_content='center'
        button.layout.padding='0'
        button.layout.margin='0 4px 0 0'
    apply.style.button_color='#176f74';apply.style.text_color='white'
    reset.style.button_color='#f4f7f8';export.style.button_color='#f4f7f8'
    reset.style.text_color='#31545c';export.style.text_color='#31545c'
    update_view_buttons()
    dashboard=w.VBox([w.HBox([header,view_switch],layout=w.Layout(flex_flow='row wrap',align_items='center')),
                       w.HBox([region,department,search],layout=w.Layout(flex_flow='row wrap')),
                       decision,expert_nav,panel,status],layout=w.Layout(width='100%'))
    dashboard.add_class('citiz-ui')
    recalc()
    if render:
        widget_display(dashboard)
        if state['last'] is not None:
            ipython_display(HTML(state['content_html']),display_id=state['map_id'])
            state['map_published']=True
    # Handles conserves pour verification et reprise sans recharger les sources.
    return dict(widget=dashboard,state=state,region=region,department=department,search=search,
                mode=mode,budget=budget,cost=cost,budget_source=budget_source,cost_source=cost_source,
                horizon=horizon,weights=weights,age=age,penalty=penalty,map_view=map_view,tabs=tabs,presentation=presentation,expert_nav=expert_nav,recalc=recalc,reset_filters=reset_filters)
