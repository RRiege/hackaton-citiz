"""Citiz Helper: premier diagnostic reproductible, Python natif, sans Spark.

La population couverte est un calcul geographique, le score est une heuristique.
Les permis ne sont pas observes; montants et references sont requis pour financer.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit
import html
import json
import re
import zipfile

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


@dataclass
class Config:
    workdir: str = "/tmp/citiz_v1"
    reference_date: str = "2026-10-20"
    epci: str = "200046977"  # Metropole de Lyon, perimetre du guide fourni
    radius_m: float = 400.0  # approximation a vol d'oiseau, PAS une isochrone
    budget_eur: float | None = None
    horizon_years: int = 3
    setup_eur: float | None = None
    vehicle_eur: float | None = None
    annual_operation_eur: float | None = None
    budget_source: str = ''
    cost_source: str = ''
    cost_reference_eur: float = 100_000.0
    max_cost_penalty: float = 25.0
    age_bonus_max: float = 5.0  # classe disponible: 25-39 ans, pas 25-35
    max_stations: int = 10
    target_households_anchor: float = 200.0
    population_anchor: float = 1500.0
    no_car_weight: float = 35.0
    transit_weight: float = 35.0
    population_weight: float = 20.0
    equity_weight: float = 5.0
    transit_coverage_penalty: float = 35.0

    def validate(self):
        amounts=[self.budget_eur,self.setup_eur,self.vehicle_eur,self.annual_operation_eur]
        if any(v is None or not np.isfinite(v) for v in amounts):
            raise ValueError('Renseigner les montants : aucun budget ni cout estime par defaut.')
        if (self.budget_eur>0 or any(v>0 for v in amounts[1:])) and (not self.budget_source.strip() or not self.cost_source.strip()):
            raise ValueError('Reference de budget et source des couts requises.')
        values = [self.radius_m, self.cost_reference_eur,
                  self.target_households_anchor, self.population_anchor]
        if not all(np.isfinite(v) and v > 0 for v in values):
            raise ValueError("Rayon et references doivent etre strictement positifs.")
        if self.budget_eur < 0 or self.horizon_years < 1 or self.max_stations < 0:
            raise ValueError("Budget, horizon ou nombre de stations invalide.")
        if not 0 <= self.age_bonus_max <= 5:
            raise ValueError("Le bonus d'age est borne a 5 points.")
        weights = [self.no_car_weight, self.transit_weight, self.population_weight, self.equity_weight]
        if not all(np.isfinite(w) and w >= 0 for w in weights) or sum(weights) > 95.000001:
            raise ValueError('Poids principaux positifs, somme au plus 95 points.')
        if min(self.setup_eur, self.vehicle_eur, self.annual_operation_eur, self.max_cost_penalty) < 0:
            raise ValueError("Les composantes de cout et leur penalite doivent etre positives.")
        if not np.isfinite(self.transit_coverage_penalty) or self.transit_coverage_penalty<0:
            raise ValueError('Penalite de couverture TC invalide.')


SOURCES = {
    "population.zip": "https://www.insee.fr/fr/statistiques/fichier/8735162/Filosofi2021_carreaux_200m_csv.zip",
    "logement.zip": "https://www.insee.fr/fr/statistiques/fichier/8647012/base-ic-logement-2022_csv.zip",
    "citiz.json": "https://data.grandlyon.com/files/rdata/lpa_mobilite.donnees/gbfs.json",
    "gtfs_catalogue": "https://transport.data.gouv.fr/datasets/horaires-theoriques-du-reseau-transports-en-commun-lyonnais",
}


def public_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def download(url, path):
    """Cache local atomique; ne journalise jamais les parametres d'URL."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size:
        return path
    temporary = path.with_suffix(path.suffix + ".part")
    request = Request(url, headers={"User-Agent": "CitizHelper-Hackathon/1.0"})
    with urlopen(request, timeout=180) as response, temporary.open("wb") as target:
        while block := response.read(1024 * 1024):
            target.write(block)
    temporary.replace(path)
    return path


def acquire(config):
    raw = Path(config.workdir) / "raw"
    manifest = []
    urls = {k: v for k, v in SOURCES.items() if k != "gtfs_catalogue"}
    urls["communes.json"] = f"https://geo.api.gouv.fr/epcis/{config.epci}/communes?format=geojson&geometry=contour"
    for name, url in urls.items():
        download(url, raw / name)
        manifest.append({"source": name, "url": public_url(url),
                         "retrieved_at_utc": datetime.fromtimestamp((raw/name).stat().st_mtime, timezone.utc).isoformat()})
        print("Source disponible:", name, flush=True)
    gbfs = json.loads((raw / "citiz.json").read_text())
    feeds = gbfs["data"].get("feeds")
    if feeds is None:  # GBFS 2.x
        feeds = next(iter(gbfs["data"].values()))["feeds"]
    stations_url = next(f["url"] for f in feeds if f["name"] == "station_information")
    download(stations_url, raw / "stations.json")
    manifest.append({"source": "stations.json", "url": public_url(stations_url),
                     "gbfs_last_updated": str(gbfs.get("last_updated", ""))})
    # Le GTFS officiel TCL exige une authentification. Cette copie publique est
    # publiee comme ressource communautaire Google sur le catalogue national.
    if not (raw / "gtfs_public.zip").exists():
        with urlopen(SOURCES["gtfs_catalogue"], timeout=90) as response:
            page = response.read().decode("utf-8")
        links = re.findall(r'''href=["']([^"']+)''', page)
        links = [html.unescape(u) for u in links
                 if "gtech-transit-prod.apigee.net/" in u and "lyon_tcl.zip" in u]
        if not links:
            raise RuntimeError("GTFS TCL public absent. Fournir un GTFS autorise dans raw/gtfs_public.zip.")
        download(links[0], raw / "gtfs_public.zip")
    manifest.append({"source": "gtfs_public.zip", "url": SOURCES["gtfs_catalogue"],
                     "note": "Copie publique Google referencee par le PAN; dates de service verifiees"})
    return raw, pd.DataFrame(manifest).fillna("")


def prepare_population(raw):
    import geopandas as gpd
    communes = gpd.GeoDataFrame.from_features(json.loads((raw/"communes.json").read_text())["features"], crs=4326)
    communes = communes[["code", "nom", "geometry"]].rename(columns={"code": "commune_code", "nom": "commune"})
    # Lecture par morceaux, sans charger toute la population nationale en RAM.
    parts = []
    with zipfile.ZipFile(raw / "population.zip") as archive:
        with archive.open("carreaux_200m_met.csv") as stream:
            for chunk in pd.read_csv(stream, dtype={"lcog_geo": str}, chunksize=150_000):
                keep = chunk.lcog_geo.str.contains(r"(?:^|[,; ])69\d{3}(?:$|[,; ])", regex=True, na=False)
                parts.append(chunk.loc[keep].copy())
    population = pd.concat(parts, ignore_index=True)
    coordinates = population.idcar_200m.str.extract(r"N(\d+)E(\d+)").astype(float)
    if coordinates.isna().any().any():
        raise ValueError("Identifiants de grille non reconnus; projection non devinee.")
    points = gpd.GeoDataFrame(population, geometry=gpd.points_from_xy(coordinates[1]+100, coordinates[0]+100), crs=3035).to_crs(4326)
    cells = gpd.sjoin(points, communes, predicate="within", how="inner").drop(columns="index_right").reset_index(drop=True)
    if cells.idcar_200m.duplicated().any():
        raise ValueError("Cellules affectees a plusieurs communes.")
    projected = cells.to_crs(2154)
    cells["x"] = projected.geometry.x
    cells["y"] = projected.geometry.y
    cells["latitude"] = cells.geometry.y
    cells["longitude"] = cells.geometry.x
    cells = cells.rename(columns={"idcar_200m": "cell_id", "ind": "population", "men": "households"})
    age_columns = ["ind_18_24", "ind_25_39", "ind_40_54", "ind_55_64", "ind_65_79", "ind_80p"]
    cells["adults"] = cells[age_columns].sum(axis=1)
    cells["age_25_39"] = cells["ind_25_39"]
    cells["poor_households"] = cells["men_pauv"]
    cells = cells.loc[(cells.population > 0) & (cells.households > 0)].copy().reset_index(drop=True)
    # Le RP est agrégé à la commune dans cette V1. Pas de fausse precision IRIS.
    columns = ["COM", "P22_MEN", "P22_RP_VOIT1P", "P22_RP_VOIT1"]
    with zipfile.ZipFile(raw / "logement.zip") as archive:
        name = next(n for n in archive.namelist() if n.lower().startswith("base-ic") and n.lower().endswith(".csv"))
        with archive.open(name) as stream:
            housing = pd.read_csv(stream, sep=";", usecols=columns, dtype={"COM": str}, low_memory=False)
    for column in columns[1:]:
        housing[column] = pd.to_numeric(housing[column], errors="coerce")
    housing["COM"] = housing.COM.replace({str(69380+i): "69123" for i in range(1, 10)})
    housing = housing.groupby("COM")[columns[1:]].sum(min_count=1)
    housing["no_car_rate"] = (1 - housing.P22_RP_VOIT1P / housing.P22_MEN.replace(0, np.nan)).clip(0, 1)
    housing["one_car_rate"] = (housing.P22_RP_VOIT1 / housing.P22_MEN.replace(0, np.nan)).clip(0, 1)
    cells = cells.merge(housing[["no_car_rate", "one_car_rate"]], left_on="commune_code", right_index=True, how="left")
    cells["no_car_households_proxy"] = cells.households * cells.no_car_rate
    cells["license_holders_without_car"] = np.nan  # permis NON mesure
    cells["motorization_scale"] = "commune_RP2022_proxy"
    if cells.empty:
        raise ValueError("Aucune cellule dans le territoire choisi.")
    return cells.reset_index(drop=True), communes


def active_services(calendar, exceptions, day):
    stamp = day.strftime("%Y%m%d")
    weekday = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
    ids = set()
    if not calendar.empty:
        valid = (calendar.start_date <= stamp) & (calendar.end_date >= stamp) & (calendar[weekday] == "1")
        ids = set(calendar.loc[valid, "service_id"])
    if not exceptions.empty:
        today = exceptions.loc[exceptions.date == stamp]
        ids |= set(today.loc[today.exception_type == "1", "service_id"])
        ids -= set(today.loc[today.exception_type == "2", "service_id"])
    return ids


def read_transit(raw, config):
    with zipfile.ZipFile(raw / "gtfs_public.zip") as archive:
        names = {Path(n).name: n for n in archive.namelist()}
        def read(name, columns=None, optional=False):
            if name not in names and optional:
                return pd.DataFrame()
            with archive.open(names[name]) as stream:
                return pd.read_csv(stream, dtype=str, usecols=columns)
        stops = read("stops.txt", ["stop_id", "stop_name", "stop_lat", "stop_lon"])
        trips = read("trips.txt", ["trip_id", "service_id"])
        calendar = read("calendar.txt", optional=True)
        exceptions = read("calendar_dates.txt", optional=True)
        events = read("stop_times.txt", ["trip_id", "stop_id", "departure_time"])
        frequencies = read("frequencies.txt", optional=True)
    day = date.fromisoformat(config.reference_date)
    weekday = day + timedelta(days=(1-day.weekday()) % 7)
    saturday = day + timedelta(days=(5-day.weekday()) % 7)
    times = events.departure_time.str.split(":", expand=True)
    hours = pd.to_numeric(times[0], errors="raise") + pd.to_numeric(times[1], errors="raise")/60
    events["hour"] = hours
    frequency_events = pd.DataFrame()
    if not frequencies.empty:
        for key in ["start_time", "end_time"]:
            t = frequencies[key].str.split(":", expand=True).astype(int)
            frequencies[key+"_sec"] = t[0]*3600+t[1]*60+t[2]
        frequencies["headway_secs"] = pd.to_numeric(frequencies.headway_secs, errors="raise")
        if (frequencies.headway_secs <= 0).any():
            raise ValueError("Intervalle GTFS non positif.")
        templates = events.loc[events.trip_id.isin(frequencies.trip_id)].copy()
        first = templates.groupby("trip_id").hour.min()
        templates["offset_sec"] = (templates.hour-templates.trip_id.map(first))*3600
        frequency_events = templates.merge(frequencies, on="trip_id").merge(trips, on="trip_id")
        events = events.loc[~events.trip_id.isin(frequencies.trip_id)]
    metrics = []
    for label, service_day, low, high in [("weekday", weekday, 6, 20), ("evening", weekday, 20, 24), ("weekend", saturday, 6, 24)]:
        services = active_services(calendar, exceptions, service_day)
        if not services:
            raise ValueError(f"GTFS sans service actif le {service_day}: classement courant impossible.")
        active_trips = set(trips.loc[trips.service_id.isin(services), "trip_id"])
        selected = events.loc[events.trip_id.isin(active_trips) & events.hour.ge(low) & events.hour.lt(high)]
        count = selected.drop_duplicates(["trip_id", "stop_id"]).groupby("stop_id").size()/(high-low)
        if not frequency_events.empty:
            f = frequency_events.loc[frequency_events.service_id.isin(services)].copy()
            lower = np.maximum(f.start_time_sec, low*3600-f.offset_sec)
            upper = np.minimum(f.end_time_sec, high*3600-f.offset_sec)
            f["count"] = np.maximum(0, np.ceil((upper-f.start_time_sec)/f.headway_secs)-np.maximum(0, np.ceil((lower-f.start_time_sec)/f.headway_secs)))
            count = count.add(f.groupby("stop_id")["count"].sum()/(high-low), fill_value=0)
        stops[f"departures_per_hour_{label}"] = stops.stop_id.map(count).fillna(0)
        metrics.append({"scenario": label, "service_date": service_day.isoformat(), "window": f"{low}-{high}"})
    for column in ["stop_lat", "stop_lon"]:
        stops[column] = pd.to_numeric(stops[column], errors="coerce")
    return stops.dropna(subset=["stop_lat", "stop_lon"]), pd.DataFrame(metrics)


def enrich_access(cells, stops, raw, config):
    import geopandas as gpd
    from pyproj import Transformer
    transform = Transformer.from_crs(4326, 2154, always_xy=True)
    stops = stops.copy()
    stops["x"], stops["y"] = transform.transform(stops.stop_lon.to_numpy(), stops.stop_lat.to_numpy())
    nearest = cKDTree(stops[["x", "y"]].to_numpy())
    neighbours = nearest.query_ball_point(cells[["x", "y"]].to_numpy(), config.radius_m)
    cells["transit_stop_count"] = [len(n) for n in neighbours]
    for label in ["weekday", "evening", "weekend"]:
        values = stops[f"departures_per_hour_{label}"].to_numpy()
        # Meilleur arret proche; evite de compter plusieurs fois le meme bus.
        cells[f"best_departures_per_hour_{label}"] = [max(values[n], default=0) for n in neighbours]
    cells["transit_gap"] = (
        .50*(1-np.minimum(cells.best_departures_per_hour_weekday/4, 1))
        + .25*(1-np.minimum(cells.best_departures_per_hour_evening/2, 1))
        + .25*(1-np.minimum(cells.best_departures_per_hour_weekend/2, 1)))
    stations = pd.DataFrame(json.loads((raw / "stations.json").read_text())["data"]["stations"])
    stations = stations.drop_duplicates("station_id").copy()
    stations["x"], stations["y"] = transform.transform(stations.lon.to_numpy(), stations.lat.to_numpy())
    distances, _ = cKDTree(stations[["x", "y"]].to_numpy()).query(cells[["x", "y"]].to_numpy())
    cells["nearest_citiz_m"] = distances
    cells["citiz_covered"] = distances <= config.radius_m
    cells["need_heat_weight"] = cells.no_car_households_proxy * (.25+.75*cells.transit_gap) * (~cells.citiz_covered)
    # La couche transport reste un diagnostic de l'offre, pas une frequentation.
    stops["nearby_population"] = [float(cells.iloc[n].population.sum()) for n in cKDTree(cells[["x", "y"]]).query_ball_point(stops[["x", "y"]], config.radius_m)]
    stations["nearby_population"] = [float(cells.iloc[n].population.sum()) for n in cKDTree(cells[["x", "y"]]).query_ball_point(stations[["x", "y"]], config.radius_m)]
    return cells, stops, stations


def score_benefit(population, no_car_households, transit_gap, poverty_rate, age_share, config):
    """References fixes et poids explicites; pas de ruralite ni de permis invente."""
    terms = {
        "points_no_car": config.no_car_weight*np.clip(no_car_households/config.target_households_anchor, 0, 1),
        "points_transit_gap": config.transit_weight*np.clip(transit_gap, 0, 1),
        "points_new_population": config.population_weight*np.clip(population/config.population_anchor, 0, 1),
        "points_equity": config.equity_weight*np.clip(poverty_rate/.4, 0, 1),
        "points_age": config.age_bonus_max*np.clip(age_share/.4, 0, 1),
    }
    terms["benefit_score"] = sum(terms.values())
    return terms


def cost_penalty(cost, config):
    if not np.isfinite(cost) or cost < 0:
        raise ValueError("Cout manquant ou negatif: le site ne peut pas etre optimise.")
    return config.max_cost_penalty*min(cost/config.cost_reference_eur, 2)


def score_mobility_need(population, target, gap, poverty, age, config):
    """Besoin lie a une cible substantielle ET au manque de TC, sans bonus rural."""
    gap=np.clip(gap,0,1)
    support=np.clip(target/config.target_households_anchor,0,1)
    terms=score_benefit(population,target,gap,poverty,age,config)
    for key in ['points_no_car','points_new_population']:
        terms[key]*=gap
    terms['points_transit_gap']=config.transit_weight*np.clip(target*gap/config.target_households_anchor,0,1)
    for key in ['points_equity','points_age']:
        terms[key]*=gap*support
    terms['benefit_score']=sum(v for k,v in terms.items() if k!='benefit_score')
    terms['transit_coverage_penalty']=config.transit_coverage_penalty*(1-gap)
    terms['mobility_need_score']=np.maximum(0,terms['benefit_score']-terms['transit_coverage_penalty'])
    return terms


def evaluate_site(cells, indices, config, cost):
    group = cells.iloc[indices]
    population = float(group.population.sum())
    if population <= 0:
        return None
    if group.no_car_rate.isna().any():
        return None  # absence de donnees: signaler, ne pas convertir en zero
    households = float(group.households.sum())
    no_car = float(group.no_car_households_proxy.sum())
    target_column='licensed_adults_no_car_estimate' if 'licensed_adults_no_car_estimate' in group else 'no_car_households_proxy'
    if group[target_column].isna().any(): return None
    target=float(group[target_column].sum())
    gap = float((group[target_column]*group.transit_gap).sum()/max(target,1e-12))
    poverty = float(group.poor_households.sum()/max(households, 1))
    age = float(group.age_25_39.sum()/max(group.adults.sum(), 1))
    terms = score_mobility_need(population, target, gap, poverty, age, config)
    penalty = cost_penalty(cost, config)
    return {"new_population": population, "new_no_car_households_proxy": no_car,
            "transit_gap": gap, "poverty_rate": poverty, "share_25_39_adults": age,
            **terms, "cost_penalty": penalty,
            "priority_score": max(0., terms["mobility_need_score"]-penalty),
            "cost_per_new_resident_eur": cost/population}


def rank_and_select(cells, config, cost_overrides=None):
    config.validate()
    overrides = {} if cost_overrides is None else cost_overrides
    xy = cells[["x", "y"]].to_numpy()
    areas = cKDTree(xy).query_ball_point(xy, config.radius_m)
    covered = cells.citiz_covered.astype('boolean')
    available = ~covered.fillna(True).to_numpy(dtype=bool)
    # Le centre propose doit lui aussi etre hors de la couverture existante.
    # Sans cette regle, ses voisins non couverts pouvaient le rendre attractif.
    site_eligible = available.copy()
    if 'nearest_citiz_m' in cells:
        distance = pd.to_numeric(cells.nearest_citiz_m, errors='coerce')
        available &= distance.notna().to_numpy()
        site_eligible &= distance.gt(config.radius_m).fillna(False).to_numpy()
    initially_available = available.copy()
    default_cost = config.setup_eur + config.vehicle_eur + config.horizon_years*config.annual_operation_eur
    # Matrice creuse: un seul calcul vectorise par iteration de selection.
    # Aucun cluster distribue; toutes les operations restent en Python/NumPy.
    from scipy.sparse import csr_matrix
    rows = np.repeat(np.arange(len(cells)), [len(a) for a in areas])
    columns = np.concatenate(areas).astype(int)
    matrix = csr_matrix((np.ones(len(columns)), (rows, columns)), shape=(len(cells), len(cells)))
    identifiers = cells.cell_id.to_numpy()
    costs = np.array([overrides.get(i, default_cost) for i in identifiers], dtype=float)
    if np.any(costs < 0):
        raise ValueError("Cout negatif interdit.")
    penalty = config.max_cost_penalty*np.minimum(costs/config.cost_reference_eur, 2)
    def metrics(mask):
        def total(column):
            return np.asarray(matrix @ (cells[column].fillna(0).to_numpy()*mask)).ravel()
        population = total("population")
        households = total("households")
        no_car = total("no_car_households_proxy")
        target = total('licensed_adults_no_car_estimate') if 'licensed_adults_no_car_estimate' in cells else no_car
        target_column='licensed_adults_no_car_estimate' if 'licensed_adults_no_car_estimate' in cells else 'no_car_households_proxy'
        gap = np.asarray(matrix @ (cells[target_column].fillna(0).to_numpy()*cells.transit_gap.to_numpy()*mask))/np.maximum(target,1e-12)
        poverty = total("poor_households")/np.maximum(households, 1)
        age = total("age_25_39")/np.maximum(total("adults"), 1)
        terms = score_mobility_need(population, target, gap, poverty, age, config)
        missing = np.asarray(matrix @ (cells.no_car_rate.isna().to_numpy()*mask)).ravel() > 0
        if 'licensed_adults_no_car_estimate' in cells:
            missing |= np.asarray(matrix @ (cells.licensed_adults_no_car_estimate.isna().to_numpy()*mask)).ravel() > 0
        eligible = (population > 0) & ~missing & np.isfinite(costs)
        return pd.DataFrame({"new_population": population, "new_no_car_households_proxy": no_car,
            'new_licensed_adults_no_car_estimate':target if 'licensed_adults_no_car_estimate' in cells else np.nan,
            "transit_gap": gap, "poverty_rate": poverty, "share_25_39_adults": age,
            **terms, "cost_penalty": penalty,
            "priority_score": np.where(eligible, np.maximum(0, terms["mobility_need_score"]-penalty), np.nan),
            "cost_per_new_resident_eur": costs/np.maximum(population, 1)})
    base = cells[["cell_id", "commune_code", "commune", "latitude", "longitude", "x", "y"]].rename(columns={"cell_id": "candidate_id"}).reset_index(drop=True)
    base["cost_total_eur"] = costs
    base["horizon_years"] = config.horizon_years
    base["cost_status"] = ["inconnu" if not np.isfinite(c) else "source_renseignee_a_verifier" for c in costs]
    base['cost_source']=config.cost_source
    base['budget_source']=config.budget_source
    base["site_status"] = "centre_carreau_parking_non_verifie"
    base['nearest_existing_citiz_m'] = cells.nearest_citiz_m.to_numpy() if 'nearest_citiz_m' in cells else np.nan
    base['existing_citiz_exclusion_m'] = config.radius_m
    base["license_status"] = "non_mesure"
    base["motorization_scale"] = "commune_RP2022_proxy"
    base["population_in_radius"] = np.asarray(matrix @ cells.population.to_numpy())
    candidates = pd.concat([base, metrics(available)], axis=1)
    candidates = candidates.loc[site_eligible & candidates.new_population.gt(0)].copy()
    usable_areas = {i: np.asarray(a, dtype=int) for i, a in zip(identifiers, areas)}
    candidates = candidates.sort_values(["priority_score", "candidate_id"], ascending=[False, True]).reset_index(drop=True)
    candidates["rank"] = np.arange(1, len(candidates)+1)
    candidates["age_band"] = "25-39 (proxy de la cible 25-35)"
    chosen, spent = [], 0.
    taken = np.zeros(len(cells), dtype=bool)
    for _ in range(config.max_stations):
        marginal = metrics(available)
        feasible = site_eligible & ~taken & (costs+spent <= config.budget_eur) & marginal.priority_score.gt(0).to_numpy()
        if not feasible.any():
            break
        choices = marginal.loc[feasible].copy()
        choices["cost"] = costs[feasible]
        i = choices.sort_values(["priority_score", "cost"], ascending=[False, True], kind="stable").index[0]
        candidate = base.iloc[i].to_dict()
        original = candidates.loc[candidates.candidate_id == candidate["candidate_id"]].iloc[0]
        candidate["rank"] = int(original["rank"])
        candidate["age_band"] = original["age_band"]
        value = marginal.iloc[i].to_dict()
        indices = usable_areas[candidate["candidate_id"]]
        fresh = indices[available[indices]]
        spent += costs[i]
        chosen.append({**candidate, **value, "selection_order": len(chosen)+1, "cumulative_cost_eur": spent})
        available[fresh] = False
        taken[i] = True
    selection = pd.DataFrame(chosen, columns=list(candidates.columns)+["selection_order", "cumulative_cost_eur"])
    cells["added_by_scenario"] = initially_available & ~available
    cells["covered_after_scenario"] = covered | cells.added_by_scenario
    return candidates, selection, usable_areas


def build_map(cells, stations, candidates, selection, output):
    import folium
    from folium.plugins import HeatMap, MarkerCluster
    import geopandas as gpd
    centre = [float(cells.latitude.mean()), float(cells.longitude.mean())]
    m = folium.Map(location=centre, zoom_start=11, tiles="OpenStreetMap", control_scale=True)
    heat = folium.FeatureGroup(name="Chaleur: besoin Citiz estime", show=True)
    values = cells.dropna(subset=["need_heat_weight"])
    scale = max(float(values.need_heat_weight.quantile(.95)), 1)
    HeatMap([[r.latitude, r.longitude, min(r.need_heat_weight/scale, 1)] for r in values.itertuples() if r.need_heat_weight > 0],
            radius=16, blur=12, min_opacity=.2).add_to(heat)
    heat.add_to(m)
    # Carreaux colores pour la lecture analytique; geometrie originale 200m.
    from shapely.geometry import box
    from branca.colormap import LinearColormap
    identifiers = cells.cell_id.str.extract(r"N(\d+)E(\d+)").astype(float)
    squares = gpd.GeoDataFrame(cells[["cell_id", "commune", "population", "transit_gap", "no_car_rate", "need_heat_weight", "citiz_covered"]].copy(),
                              geometry=[box(e, n, e+200, n+200) for n, e in identifiers.to_numpy()], crs=3035).to_crs(4326)
    squares = squares.astype({"citiz_covered": str})
    palette = LinearColormap(["#dcecf4", "#e8c26e", "#d54c3f"], vmin=0, vmax=scale)
    folium.GeoJson(json.loads(squares.to_json()), name="Analyse: carreaux 200m", show=False,
        style_function=lambda f: {"fillColor": palette(min(f["properties"]["need_heat_weight"] or 0, scale)), "color": "#ffffff", "weight": .2, "fillOpacity": .65},
        tooltip=folium.GeoJsonTooltip(fields=["commune", "population", "transit_gap", "no_car_rate", "citiz_covered"],
                                     aliases=["Commune", "Population Filosofi", "Deficit TC (0-1)", "Sans voiture: taux COMMUNAL", "Citiz proche"])).add_to(m)
    cluster = MarkerCluster(name="Stations Citiz existantes", show=True).add_to(m)
    for row in stations.itertuples():
        name = row.name if isinstance(row.name, str) else " / ".join(n.get("text", "") for n in row.name)
        folium.Marker([row.lat, row.lon], tooltip=html.escape(name),
                      popup=f"{html.escape(name)}<br>Habitants proches: {row.nearby_population:,.0f}", icon=folium.Icon(color="blue", icon="car", prefix="fa")).add_to(cluster)
    candidates_layer = folium.FeatureGroup(name="Top 100 secteurs a etudier", show=False).add_to(m)
    def add_candidate(row, layer, selected=False):
        text = (f"<b>{html.escape(row.commune)}</b><br>Score: {row.priority_score:.1f}/100"
                f"<br>Habitants nouvellement proches: {row.new_population:,.0f}"
                f"<br>Menages sans voiture (proxy communal): {row.new_no_car_households_proxy:,.0f}"
                f"<br>Permis: non mesure<br>Cout {row.cost_total_eur:,.0f} EUR / {row.horizon_years} ans (hypothese)"
                f"<br>Bonus age 25-39: {row.points_age:.1f}/5"
                "<br>Rayon aerien 400m; parking a verifier")
        folium.CircleMarker([row.latitude, row.longitude], radius=8 if selected else 5,
                            color="#087f70" if selected else "#ba6a20", fill=True, fill_opacity=.9,
                            tooltip=f"{row.commune}: {row.priority_score:.1f}", popup=folium.Popup(text, max_width=340)).add_to(layer)
    for row in candidates.head(100).itertuples():
        add_candidate(row, candidates_layer)
    chosen_layer = folium.FeatureGroup(name="Selection sous budget (scenario)", show=True).add_to(m)
    for row in selection.itertuples():
        add_candidate(row, chosen_layer, True)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(output))
    return m


def export_results(result, config):
    output = Path(config.workdir)/"output"
    output.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(result["cells"].drop(columns="geometry")).copy()
    summary["population_covered"] = summary.population * summary.citiz_covered
    summary["population_added"] = summary.population * summary.added_by_scenario
    commune_kpis = summary.groupby(["commune_code", "commune"], as_index=False).agg(
        population=("population", "sum"), population_covered=("population_covered", "sum"),
        population_added=("population_added", "sum"), households=("households", "sum"),
        no_car_households_proxy=("no_car_households_proxy", "sum"))
    tables = {
        "citiz_v1_coverage_cells": pd.DataFrame(result["cells"].drop(columns="geometry")),
        "citiz_v1_candidates": result["candidates"],
        "citiz_v1_selection": result["selection"],
        "citiz_v1_stations": result["stations"][["station_id", "lat", "lon", "nearby_population"]].astype({"station_id": str}),
        "citiz_v1_transit_stops": result["stops"],
        "citiz_v1_sources": result["sources"],
        "citiz_v1_service_dates": result["service_dates"],
        "citiz_v1_commune_kpis": commune_kpis,
    }
    for name, table in tables.items():
        table.to_csv(output/f"{name}.csv", index=False)
    (output/"config.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    result["map"] = build_map(result["cells"], result["stations"], result["candidates"], result["selection"], output/"citiz_map.html")
    result["tables"] = tables
    result["output"] = output
    return result


def run(config=None):
    config = config or Config()
    config.validate()
    raw, sources = acquire(config)
    print("Preparation de la population et de la motorisation...", flush=True)
    cells, communes = prepare_population(raw)
    print(len(cells), "carreaux habites;", round(cells.population.sum()), "habitants Filosofi", flush=True)
    stops, service_dates = read_transit(raw, config)
    cells, stops, stations = enrich_access(cells, stops, raw, config)
    print("Calcul des candidats et du gain marginal sous budget...", flush=True)
    overrides_path = Path(config.workdir)/"cost_overrides.csv"
    overrides = None
    if overrides_path.exists():
        costs = pd.read_csv(overrides_path)
        if costs.candidate_id.duplicated().any():
            raise ValueError("Couts dupliques pour un candidat.")
        overrides = dict(zip(costs.candidate_id, costs.cost_total_eur))
    candidates, selection, areas = rank_and_select(cells, config, overrides)
    result = export_results(dict(cells=cells, communes=communes, stops=stops, stations=stations,
                                 sources=sources, service_dates=service_dates,
                                 candidates=candidates, selection=selection), config)
    print(f"TERMINE: {len(candidates)} secteurs, {len(selection)} stations dans le scenario.", flush=True)
    print("Permis non mesures; couts hypothetiques; age 25-39; rayon aerien 400m.", flush=True)
    return result


if __name__ == "__main__":
    result = run()
