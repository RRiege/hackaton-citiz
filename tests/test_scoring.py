"""Tests des regles de decision; les donnees artificielles restent dans les tests."""
import sys
import unittest
import tempfile
import zipfile
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from citiz_v1 import Config, cost_penalty, score_benefit, score_mobility_need, rank_and_select, active_services, read_transit

def funded_config(**changes):
    values=dict(budget_eur=250000,setup_eur=5000,vehicle_eur=20000,annual_operation_eur=12000,
                budget_source='fixture synthetique',cost_source='fixture synthetique')
    values.update(changes)
    return Config(**values)


def fixture():
    return pd.DataFrame({
        "cell_id": ["a", "b", "c"], "x": [0., 100., 2000.], "y": [0., 0., 0.],
        "commune_code": ["X"]*3, "commune": ["Test"]*3,
        "latitude": [45.]*3, "longitude": [4.]*3,
        "population": [500., 500., 500.], "households": [250.]*3,
        "no_car_rate": [.8]*3, "no_car_households_proxy": [200.]*3,
        "transit_gap": [.8]*3, "poor_households": [50.]*3,
        "adults": [400.]*3, "age_25_39": [100.]*3,
        "citiz_covered": [False]*3,
    })


class Rules(unittest.TestCase):
    def test_local_transit_need_requires_both_demand_and_gap(self):
        cfg=Config()
        covered=score_mobility_need(10000,2000,0,.3,.4,cfg)
        unmet=score_mobility_need(1500,300,.8,.3,.4,cfg)
        tiny=score_mobility_need(10,1,1,.3,.4,cfg)
        self.assertEqual(covered['mobility_need_score'],0)
        self.assertGreater(unmet['mobility_need_score'],tiny['mobility_need_score'])
        self.assertLess(tiny['mobility_need_score'],1)
    def test_cost_penalty_monotonic_and_missing_not_free(self):
        cfg = Config()
        self.assertGreater(cost_penalty(100000, cfg), cost_penalty(50000, cfg))
        with self.assertRaises(ValueError):
            cost_penalty(np.nan, cfg)

    def test_age_bonus_limited_and_disabled(self):
        cfg = Config()
        self.assertEqual(score_benefit(100, 100, .5, .2, 1, cfg)["points_age"], 5)
        cfg.age_bonus_max = 0
        self.assertEqual(score_benefit(100, 100, .5, .2, 1, cfg)["points_age"], 0)

    def test_budget_and_overlap(self):
        cells = fixture()
        cfg = funded_config(budget_eur=122000, max_stations=10)
        _, selection, _ = rank_and_select(cells, cfg)
        self.assertEqual(len(selection), 2)
        self.assertLessEqual(selection.cost_total_eur.sum(), cfg.budget_eur)
        self.assertEqual(selection.new_population.sum(), cells.population.sum())
        self.assertEqual(cells.added_by_scenario.sum(), 3)

    def test_existing_population_never_counted_again(self):
        cells = fixture()
        cells.loc[0, "citiz_covered"] = True
        _, selection, _ = rank_and_select(cells, funded_config())
        self.assertEqual(selection.new_population.sum(), 1000)

    def test_existing_station_excludes_center_even_with_uncovered_neighbors(self):
        cells=fixture()
        cells.loc[0,'citiz_covered']=True
        ranked,selected,_=rank_and_select(cells,funded_config())
        self.assertNotIn('a',ranked.candidate_id.tolist())
        self.assertNotIn('a',selected.candidate_id.tolist())
        self.assertIn('b',ranked.candidate_id.tolist())

    def test_station_distance_boundary_and_unknown_are_excluded(self):
        cells=fixture()
        cells['nearest_citiz_m']=[400.,400.01,np.nan]
        ranked,selected,_=rank_and_select(cells,funded_config())
        self.assertEqual(ranked.candidate_id.tolist(),['b'])
        self.assertEqual(selected.candidate_id.tolist(),['b'])
        self.assertTrue(ranked.nearest_existing_citiz_m.gt(400).all())

    def test_fully_covered_area_returns_no_proposal(self):
        cells=fixture().assign(citiz_covered=True)
        ranked,selected,_=rank_and_select(cells,funded_config())
        self.assertTrue(ranked.empty)
        self.assertTrue(selected.empty)
        self.assertEqual(cells.added_by_scenario.sum(),0)

    def test_unknown_existing_coverage_is_not_a_new_opportunity(self):
        cells=fixture().assign(citiz_covered=pd.NA,nearest_citiz_m=np.nan)
        ranked,selected,_=rank_and_select(cells,funded_config())
        self.assertTrue(ranked.empty)
        self.assertTrue(selected.empty)
        self.assertTrue(cells.covered_after_scenario.isna().all())
        self.assertFalse(cells.added_by_scenario.any())

    def test_higher_cost_cannot_improve_same_site_score(self):
        cfg = funded_config()
        base, _, _ = rank_and_select(fixture(), cfg)
        changed, _, _ = rank_and_select(fixture(), cfg, {"a": 100000})
        self.assertLess(changed.set_index("candidate_id").loc["a", "priority_score"],
                        base.set_index("candidate_id").loc["a", "priority_score"])

    def test_unknown_cost_is_excluded_from_selection(self):
        _, selected, _ = rank_and_select(fixture(), funded_config(), {"a": np.nan, "b": np.nan, "c": np.nan})
        self.assertTrue(selected.empty)

    def test_no_budget_no_selection(self):
        _, selected, _ = rank_and_select(fixture(), funded_config(budget_eur=0))
        self.assertTrue(selected.empty)

    def test_calendar_exceptions(self):
        calendar = pd.DataFrame([{"service_id": "normal", "start_date": "20260101", "end_date": "20261231", "tuesday": "1"}])
        exceptions = pd.DataFrame([{"service_id": "normal", "date": "20261020", "exception_type": "2"},
                                   {"service_id": "special", "date": "20261020", "exception_type": "1"}])
        self.assertEqual(active_services(calendar, exceptions, date(2026, 10, 20)), {"special"})

    def test_gtfs_frequency_templates_not_counted_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            with zipfile.ZipFile(raw/"gtfs_public.zip", "w") as z:
                z.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\ns,Test,45,4\n")
                z.writestr("trips.txt", "trip_id,service_id\nt,all\n")
                z.writestr("stop_times.txt", "trip_id,stop_id,departure_time\nt,s,06:00:00\n")
                z.writestr("frequencies.txt", "trip_id,start_time,end_time,headway_secs\nt,06:00:00,08:00:00,3600\n")
                z.writestr("calendar.txt", "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nall,1,1,1,1,1,1,1,20260101,20261231\n")
            stops, _ = read_transit(raw, Config())
            self.assertAlmostEqual(stops.iloc[0].departures_per_hour_weekday, 2/14)
            self.assertAlmostEqual(stops.iloc[0].departures_per_hour_weekend, 2/18)


if __name__ == "__main__":
    unittest.main()
