import sys, unittest, tempfile
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from citiz_france import FranceScenario, france_rank, sphere_xyz, nearest_metres, MUNICIPAL_PARENTS, license_profiles
import zipfile
from scipy.spatial import cKDTree
from france_interactive import local_department, priority_color, france_map

def overview():
    return pd.DataFrame(dict(commune_code=['A','B','C'],commune=['Alpha','Beta','Gamma'],region=['01','01','02'],
                             department=['01','02','03'],uncovered_no_car_proxy=[1500.,900.,np.nan],
                             uncovered_gap_no_car_proxy=[300.,600.,np.nan],uncovered_population=[10000.,7000.,np.nan],
                             poverty_rate=[.2,.3,np.nan],share_25_39_adults=[.3,.4,np.nan]))

def funded(**changes):
    values=dict(budget_eur=250000,site_cost_eur=61000,budget_source='fixture budget synthetique',cost_source='fixture cout synthetique',horizon_years=3)
    values.update(changes)
    return FranceScenario(**values)

class NationalRules(unittest.TestCase):
    def test_arrondissements_reconciled_for_three_cities(self):
        self.assertEqual(MUNICIPAL_PARENTS['75101'],'75056')
        self.assertEqual(MUNICIPAL_PARENTS['69389'],'69123')
        self.assertEqual(MUNICIPAL_PARENTS['13216'],'13055')
    def test_budget_and_missing_data(self):
        ranked=france_rank(overview(),funded(budget_eur=61000))
        self.assertEqual(ranked.selected.sum(),1)
        self.assertLessEqual(ranked.loc[ranked.selected,'cost_total_eur'].sum(),61000)
        self.assertTrue(ranked.loc[ranked.commune_code.eq('C'),'priority_score'].isna().all())
    def test_zero_budget_and_age_cap(self):
        ranked=france_rank(overview(),FranceScenario(budget_eur=0,age_bonus=0))
        self.assertEqual(ranked.selected.sum(),0)
        self.assertTrue(ranked.points_age.dropna().eq(0).all())
        with self.assertRaises(ValueError): FranceScenario(age_bonus=6).validate()
    def test_filters_preserve_scope(self):
        self.assertEqual(france_rank(overview(),FranceScenario(region='02')).commune_code.tolist(),['C'])
        self.assertEqual(france_rank(overview(),FranceScenario(search='alp')).commune_code.tolist(),['A'])
    def test_missing_cost_excludes_and_higher_cost_penalizes(self):
        base=france_rank(overview(),funded()).set_index('commune_code')
        changed=france_rank(overview(),funded(),cost_overrides={'B':100000,'A':np.nan}).set_index('commune_code')
        self.assertLess(changed.loc['B','priority_score'],base.loc['B','priority_score'])
        self.assertTrue(np.isnan(changed.loc['A','priority_score']))
        self.assertFalse(changed.loc['A','selected'])
    def test_no_money_assumed_without_sources(self):
        scenario=FranceScenario()
        self.assertIsNone(scenario.budget_eur); self.assertIsNone(scenario.site_cost_eur)
        ranked=france_rank(overview(),scenario)
        self.assertTrue(ranked.cost_total_eur.isna().all()); self.assertTrue(ranked.cost_penalty.isna().all())
        self.assertEqual(ranked.selected.sum(),0)
        self.assertTrue(ranked.priority_score.dropna().ge(0).all())
        unreferenced=france_rank(overview(),FranceScenario(budget_eur=250000,site_cost_eur=61000))
        self.assertEqual(unreferenced.selected.sum(),0); self.assertTrue(unreferenced.cost_penalty.isna().all())
        no_horizon=funded(); no_horizon.horizon_years=None
        self.assertEqual(france_rank(overview(),no_horizon).selected.sum(),0)
    def test_license_target_changes_priority_not_age_assumption(self):
        data=overview()
        data['uncovered_licensed_adults_no_car_estimate']=[100.,2500.,np.nan]
        data['uncovered_gap_licensed_adults_estimate']=[20.,1200.,np.nan]
        ranked=france_rank(data)
        self.assertEqual(ranked.iloc[0].commune_code,'B')
        self.assertTrue(ranked.loc[ranked.commune_code.eq('C'),'priority_score'].isna().all())
    def test_observed_permis_vehicle_crossing_uses_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            n=100; ids=[str(i) for i in range(n)]
            frames={
                'k_individu_public_V3.csv':(pd.DataFrame({'IDENT_MEN':ids,'IDENT_IND':ids,'BPERMIS':['1']*60+['2']*40,'pond_indC':[1]*n}),';'),
                'tcm_ind_kish_public_V3.csv':(pd.DataFrame({'ident_ind':ids,'AGE':[30]*n}),';'),
                'q_menage_public_V3.csv':(pd.DataFrame({'IDENT_MEN':ids,'JNBVEH':[0]*n,'pond_menC':[1]*n}),';'),
                'tcm_men_public_V3.csv':(pd.DataFrame({'ident_men':ids,'REG_res':['Ile-de-France']*n}),',')}
            with zipfile.ZipFile(root/'emp2019.zip','w') as z:
                for name,(frame,separator) in frames.items(): z.writestr(name,frame.to_csv(index=False,sep=separator).encode('cp1252'))
            profiles=license_profiles(root)
            national=profiles.loc[profiles.region_key.eq('FR_MET')].iloc[0]
            self.assertAlmostEqual(national.licensed_adults_per_no_vehicle_household,.6)
            self.assertTrue(national.reliable)
    def test_local_needs_available_without_financial_estimate(self):
        from test_scoring import fixture
        data=fixture().assign(transit_gap_proxy=.8,longitude=[4.,4.001,4.03])
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/'cells'/'01'; folder.mkdir(parents=True)
            data.to_csv(folder/'cells.csv',index=False)
            stations=pd.DataFrame(dict(latitude=[46.],longitude=[5.],name=['Fixture distante']))
            ranked,selected,_=local_department({'workdir':directory,'stations':stations},'01',FranceScenario())
            self.assertTrue(selected.empty)
            self.assertTrue(ranked.cost_total_eur.isna().all())
            self.assertTrue(ranked.cost_penalty.isna().all())
            self.assertTrue(ranked.priority_score.notna().all())
            self.assertTrue(ranked.nearest_existing_citiz_m.gt(400).all())
    def test_weights_change_ranking_without_rural_variable(self):
        data=overview(); data['rural']=[True,False,True]
        data['uncovered_no_car_proxy']=[900.,15000.,np.nan]
        data['uncovered_gap_no_car_proxy']=[600.,900.,np.nan]
        a=france_rank(data,FranceScenario(no_car_weight=95,transit_weight=0,population_weight=0,equity_weight=0,age_bonus=0,transit_coverage_penalty=0))
        b=france_rank(data,FranceScenario(no_car_weight=0,transit_weight=95,population_weight=0,equity_weight=0,age_bonus=0,transit_coverage_penalty=0))
        self.assertEqual(a.iloc[0].commune_code,'A'); self.assertEqual(b.iloc[0].commune_code,'B')
        data['rural']=~data.rural
        c=france_rank(data,FranceScenario(no_car_weight=95,transit_weight=0,population_weight=0,equity_weight=0,age_bonus=0,transit_coverage_penalty=0))
        self.assertTrue(a.priority_score.equals(c.priority_score))
    def test_covered_big_city_does_not_outrank_substantial_unmet_demand(self):
        data=overview()
        data['uncovered_no_car_proxy']=[100000.,1500.,2.]
        data['uncovered_gap_no_car_proxy']=[0.,1200.,2.]
        data['uncovered_population']=[1000000.,10000.,10.]
        data['poverty_rate']=.3; data['share_25_39_adults']=.4
        ranked=france_rank(data).set_index('commune_code')
        self.assertEqual(ranked.loc['A','priority_score'],0)
        self.assertGreater(ranked.loc['B','priority_score'],ranked.loc['C','priority_score'])
        self.assertLess(ranked.loc['C','priority_score'],1)
    def test_marker_colors_have_fixed_thresholds_and_missing_status(self):
        self.assertNotEqual(priority_color(19.9),priority_color(20))
        self.assertNotEqual(priority_color(39.9),priority_color(40))
        self.assertNotEqual(priority_color(59.9),priority_color(60))
        self.assertEqual(priority_color(70),priority_color(100))
        self.assertEqual(priority_color(np.nan),'#77838c')
    def test_high_priority_marker_drawn_above_low_priority_neighbor(self):
        data=overview().iloc[:2].copy()
        data['latitude']=45.7; data['longitude']=4.8
        data['department_name']='Test'; data['no_car_households_rp2022']=100
        data['priority_score']=[80.,5.]; data['points_age']=0.
        data['cost_total_eur']=np.nan; data['cost_penalty']=np.nan; data['cost_source']=''
        m=france_map({'stations':pd.DataFrame(columns=['latitude','longitude','name'])},data,data.iloc[:0])
        layer=next(c for c in m._children.values() if getattr(c,'layer_name','')=='Territoires a etudier')
        markers=list(layer._children.values())
        self.assertEqual([c.options['fillColor'] for c in markers],[priority_color(5),priority_color(80)])
        self.assertTrue(all(c.options['pane']=='priority_points' for c in markers))
    def test_world_distances_work_in_metropole_and_overseas(self):
        tree=cKDTree(sphere_xyz([48.85,-21.1],[2.35,55.5]))
        distance=nearest_metres(tree,[48.85,-21.1,48.851],[2.35,55.5,2.35])
        self.assertAlmostEqual(distance[0],0); self.assertAlmostEqual(distance[1],0)
        self.assertTrue(110<distance[2]<112)

if __name__=='__main__': unittest.main()
