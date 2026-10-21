"""Les cartes descriptives changent de variable, jamais les poids du modele."""
import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import pandas as pd
import numpy as np
from france_interactive import thematic_values,france_map,show_france_interactive,MAP_THEMES,map_availability,heat_intensities,territory_metrics
from citiz_france import france_rank,study_scope,STUDY_REGIONS


def sample():
    return pd.DataFrame(dict(commune_code=['01001','01002'],commune=['Alpha','Beta'],region=['84','84'],
        region_name=['Test','Test'],department=['01','01'],department_name=['Test','Test'],
        population=[1000.,2000.],population_far_stops=[250.,1600.],uncovered_population=[200.,1500.],
        uncovered_no_car_proxy=[50.,400.],uncovered_gap_no_car_proxy=[20.,300.],
        uncovered_licensed_adults_no_car_estimate=[40.,300.],uncovered_gap_licensed_adults_estimate=[15.,250.],
        no_car_households_rp2022=[100.,500.],poverty_rate=[.2,.3],share_25_39_adults=[.3,.4],
        latitude=[46.,46.01],longitude=[3.,3.01],license_status=['estime','estime'],grid_status=['ok','ok']))


class ThematicMaps(unittest.TestCase):
    def test_transport_and_citiz_cards_are_population_weighted(self):
        data=sample()
        metrics=territory_metrics(data)
        self.assertAlmostEqual(metrics['far_share'],100*1850/3000)
        self.assertAlmostEqual(metrics['citiz_share'],100*1300/3000)
        data.loc[1,'population_far_stops']=np.nan
        self.assertEqual(territory_metrics(data)['far_share'],25)
        data['uncovered_population']=np.nan
        self.assertTrue(np.isnan(territory_metrics(data)['citiz_share']))

    def test_local_cards_use_cells_not_overlapping_candidate_populations(self):
        cells=pd.DataFrame(dict(population=[100.,300.,900.],nearest_stop_m=[0.,800.,np.nan],
            citiz_covered=[True,False,pd.NA],licensed_adults_no_car_estimate=[10.,30.,90.]))
        metrics=territory_metrics(pd.DataFrame(dict(population=[99999.])),cells)
        self.assertEqual(metrics['target'],30)
        self.assertEqual(metrics['far_share'],75)
        self.assertEqual(metrics['citiz_share'],25)

    def test_heat_contrasts_without_turning_missing_or_zero_into_need(self):
        levels=heat_intensities([0,np.nan,-1,1,10,100,10000])
        np.testing.assert_array_equal(levels[:3],[0,0,0])
        self.assertTrue((np.diff(levels[3:])>0).all())
        self.assertEqual(levels[-1],1)
        self.assertLess(levels[3],.25)
        np.testing.assert_array_equal(heat_intensities([0,np.nan]),[0,0])

    def test_existing_stations_are_visible_and_heat_calibrated_at_france_zoom(self):
        data=france_rank(sample())
        france={'stations':pd.DataFrame(dict(latitude=[46.],longitude=[3.],name=['Test']))}
        m=france_map(france,data,data.iloc[:0])
        existing=next(c for c in m._children.values() if getattr(c,'layer_name','')=='Stations Citiz connues (carres C)')
        self.assertTrue(existing.show)
        heat=next(c for c in m._children.values() if getattr(c,'layer_name','')=='Chaleur des priorites (communes)')
        self.assertEqual(next(iter(heat._children.values())).options['max_zoom'],5)
        self.assertIn('pas le score /100',m.get_root().render())
    def test_study_scope_excludes_corsica_and_overseas(self):
        data=pd.DataFrame(dict(commune_code=['01001','2A004','97101','98701'],region=['84','94','01','987'],cells=[1,2,3,4]))
        stations=pd.DataFrame(dict(name=['Lyon','Corse','Guadeloupe'],latitude=[45.7,42.,16.],longitude=[4.8,9.,-61.]))
        result=study_scope(dict(overview=data,stations=stations))
        self.assertEqual(result['overview'].commune_code.tolist(),['01001'])
        self.assertEqual(result['stations'].name.tolist(),['Lyon'])
        self.assertEqual(result['scope']['cells'],1)
    def test_empty_scope_is_explicit_and_reset_restores_visible_data(self):
        with tempfile.TemporaryDirectory() as directory:
            france=dict(workdir=directory,overview=sample(),sources=pd.DataFrame({'status':['ok']}),
                        stations=pd.DataFrame(columns=['latitude','longitude','name']))
            dashboard=show_france_interactive(france,render=False)
            dashboard['search'].value='commune introuvable'
            dashboard['recalc']()
            self.assertIn('Aucune valeur exploitable',dashboard['state']['content_html'])
            self.assertNotIn('<iframe',dashboard['state']['content_html'])
            dashboard['reset_filters']()
            self.assertEqual(dashboard['search'].value,'')
            self.assertIn('<iframe',dashboard['state']['content_html'])
            self.assertTrue(all(code=='' or code in STUDY_REGIONS for _,code in dashboard['region'].options))
    def test_zero_score_is_still_drawn_and_missing_geography_reported(self):
        data=france_rank(sample());data['priority_score']=0.
        france={'stations':pd.DataFrame(columns=['latitude','longitude','name'])}
        m=france_map(france,data,data.iloc[:0])
        layer=next(c for c in m._children.values() if getattr(c,'layer_name','')=='Territoires a etudier')
        self.assertEqual(len(layer._children),2)
        self.assertEqual(map_availability(data,None,'priority')['available'],2)
        data['latitude']=np.nan
        self.assertEqual(map_availability(data,None,'priority')['available'],0)
    def test_independent_measures_and_missing_not_zero(self):
        data=france_rank(sample());before=data.copy(deep=True)
        target=thematic_values(data,None,'target').set_index('commune_code')
        transit=thematic_values(data,None,'transit').set_index('commune_code')
        coverage=thematic_values(data,None,'citiz').set_index('commune_code')
        self.assertEqual(target.loc['01001','map_value'],40)
        self.assertEqual(transit.loc['01001','map_value'],25)
        self.assertEqual(coverage.loc['01001','map_value'],80)
        pd.testing.assert_frame_equal(data,before)
        missing=data.drop(columns='uncovered_licensed_adults_no_car_estimate')
        self.assertTrue(thematic_values(missing,None,'target').map_value.isna().all())
        missing=data.assign(population=0)
        self.assertTrue(thematic_values(missing,None,'citiz').map_value.isna().all())
    def test_all_themes_have_their_own_legend(self):
        data=france_rank(sample());empty=data.iloc[:0]
        france={'stations':pd.DataFrame(columns=['latitude','longitude','name'])}
        for theme,(title,_) in MAP_THEMES.items():
            with self.subTest(theme=theme):
                rendered=france_map(france,data,empty,theme=theme).get_root().render()
                self.assertIn('Territoires : score de priorite /100' if theme=='priority' else title,rendered)
    def test_navigation_replaces_map_with_analysis_and_reuses_ranking(self):
        with tempfile.TemporaryDirectory() as directory:
            france=dict(workdir=directory,overview=sample(),sources=pd.DataFrame({'status':['ok']}),
                        stations=pd.DataFrame(columns=['latitude','longitude','name']))
            dashboard=show_france_interactive(france,render=False)
            state=dashboard['state']
            self.assertIsNotNone(state['last'])
            self.assertIn('<iframe',state['content_html'])
            self.assertNotIn('<h3>Priorites de besoin',state['content_html'])
            dashboard['map_view'].value='transit'
            self.assertEqual(state['ranking_runs'],1)
            self.assertIn('Eloignement des arrets',state['content_html'])
            dashboard['tabs'].value=2
            self.assertIn('<table',state['content_html'])
            self.assertNotIn('<iframe',state['content_html'])
            dashboard['tabs'].value=0
            self.assertIn('<iframe',state['content_html'])
            self.assertNotIn('<h3>Priorites de besoin',state['content_html'])
            self.assertEqual(state['ranking_runs'],1)

    def test_two_bi_views_preserve_scenario_and_reveal_expert_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            france=dict(workdir=directory,overview=sample(),sources=pd.DataFrame({'status':['ok']}),
                        stations=pd.DataFrame(columns=['latitude','longitude','name']))
            dashboard=show_france_interactive(france,render=False)
            state=dashboard['state']
            self.assertIn('data-view="simple"',state['content_html'])
            self.assertFalse(dashboard['expert_nav'].children)
            self.assertNotIn('<table',state['content_html'])
            original=state['last'][1].copy()
            dashboard['presentation'].value='expert'
            self.assertIn('data-view="expert"',state['content_html'])
            self.assertIn('Decomposition',state['content_html'])
            self.assertEqual(len(dashboard['expert_nav'].children),1)
            dashboard['tabs'].value=2
            self.assertIn('<table',state['content_html'])
            dashboard['presentation'].value='simple'
            self.assertEqual(dashboard['tabs'].value,0)
            self.assertIn('data-view="simple"',state['content_html'])
            self.assertEqual(state['ranking_runs'],1)
            pd.testing.assert_frame_equal(state['last'][1],original)

    def test_every_map_fits_full_selected_scope_even_national_many_rows(self):
        data=france_rank(sample())
        data=pd.concat([data]*3000,ignore_index=True)
        france={'stations':pd.DataFrame(columns=['latitude','longitude','name'])}
        for theme in MAP_THEMES:
            m=france_map(france,data,data.iloc[:0],theme=theme)
            bounds=next(c for c in m._children.values() if c.__class__.__name__=='FitBounds')
            self.assertEqual(bounds.bounds,[[46.,3.],[46.01,3.01]])
            self.assertIn('invalidateSize',m.get_root().render())


if __name__=='__main__': unittest.main()
