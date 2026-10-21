"""Contrats d'agregats : les inconnus, les cohortes et les perimetres restent explicites."""
import sys, unittest, tempfile
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from mobility_metrics import operational_kpis, survey_metrics, annotate_evidence, prepare_mobility_metrics
from mobility_metrics import public_usage_observations, public_observations_for_scope, validate_public_observations


def kpi(metric='activation_30d',numerator=2,denominator=4):
    return dict(commune_code='01001',period_start='2026-01-01',period_end='2026-03-31',metric=metric,
                numerator=numerator,denominator=denominator,source='fixture agregee synthetique',definition_version='v1')


class AggregateContracts(unittest.TestCase):
    def test_public_counts_scope_and_rounding(self):
        data=public_usage_observations()
        self.assertEqual(len(data),29)
        self.assertEqual(data.source_id.nunique(),6)
        motives=data.loc[data.metric.str.startswith('motivation_')]
        self.assertEqual(motives.numerator.tolist(),[1504,1451,1403,1189,808])
        self.assertTrue(motives.denominator.eq(1813).all())
        self.assertGreater(motives.value.sum(),100)
        self.assertTrue(data.loc[data.source_id.eq('CITIZ_ORLEANS2025'),'numerator'].isna().all())
        self.assertTrue(data.loc[data.source_id.eq('CITIZ_LB2026'),'sample_n'].isna().all())
        self.assertFalse(data.strict_operational_kpi.any())
        self.assertFalse(data.used_in_ranking.any())
        published=data.loc[data.metric.eq('locations_jour_vehicule_publie')].iloc[0]
        self.assertEqual(published.value,.13)
        self.assertTrue(pd.isna(published.denominator))
    def test_public_observations_do_not_spread_local_data(self):
        data=public_usage_observations()
        elsewhere=public_observations_for_scope(data,{'01001'},departments={'01'})
        self.assertTrue(elsewhere.scope_type.eq('national').all())
        local=public_observations_for_scope(data,{'69085'},departments={'69'})
        self.assertEqual(local.loc[local.commune_code.ne(''),'commune_code'].unique().tolist(),['69085'])
        bad=data.copy(); bad.loc[0,'commune_code']='01001'
        with self.assertRaises(ValueError): validate_public_observations(bad)
        bad=data.copy(); bad.loc[0,'numerator']=1
        with self.assertRaises(ValueError): validate_public_observations(bad)
    def test_missing_is_not_zero(self):
        data=operational_kpis()
        self.assertTrue(data.value.isna().all())
        self.assertTrue(data.status.eq('a_collecter').all())
        zero=operational_kpis(pd.DataFrame([kpi(numerator=0,denominator=4)]))
        self.assertEqual(zero.iloc[0].value,0)
        unknown=operational_kpis(pd.DataFrame([kpi(numerator=0,denominator=0)]))
        self.assertTrue(unknown.value.isna().all())
    def test_rate_and_vehicle_day_units(self):
        data=operational_kpis(pd.DataFrame([kpi(),kpi('bookings_per_vehicle_day',10,2)]))
        self.assertEqual(data.value.tolist(),[50,5])
    def test_invalid_counts_sources_duplicate_and_definition_rejected(self):
        invalid=[dict(numerator=5,denominator=4),dict(numerator=.5),dict(numerator=np.inf),dict(source=''),
                 dict(period_end='2025-01-01'),dict(definition_version='v2'),dict(metric='occupation_supposee')]
        for changes in invalid:
            row=kpi(); row.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError): operational_kpis(pd.DataFrame([row]))
        with self.assertRaises(ValueError): operational_kpis(pd.DataFrame([kpi(),kpi()]))
        with self.assertRaises(ValueError): operational_kpis(pd.DataFrame([dict(**kpi(),email='a@b.fr')]))
    def test_multichoice_survey_does_not_force_sum_to_100(self):
        common=dict(commune_code='01001',n_reponses=8,n_eligibles=10,date_debut='2026-01-01',date_fin='2026-02-01',source='fixture locale')
        data=survey_metrics(pd.DataFrame([dict(**common,motif='visites_proches'),dict(**common,motif='courses_volumineuses')]))
        self.assertEqual(data.share_pct.sum(),160)
        self.assertTrue(data.status.str.contains('declaratif').all())
        bad=data.iloc[:1][list(common)+['motif']].copy(); bad['n_reponses']=11
        with self.assertRaises(ValueError): survey_metrics(bad)
    def test_evidence_does_not_change_ranking_or_certify_precision(self):
        original=pd.DataFrame(dict(priority_score=[80.,np.nan],cells=[10,0],imputed_cells=[4,0]))
        data=annotate_evidence(original)
        self.assertTrue(data.priority_score.equals(original.priority_score))
        self.assertEqual(data.iloc[0].imputed_cell_share,.4)
        self.assertIn('limitee',data.iloc[0].evidence_status)
        self.assertIn('insuffisante',data.iloc[1].evidence_status)
    def test_exports_have_no_synthetic_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            result=prepare_mobility_metrics(dict(workdir=directory,overview=pd.DataFrame({'commune_code':['01001']})))
            self.assertTrue(result['survey'].empty)
            self.assertTrue(result['kpis'].value.isna().all())
            root=Path(directory)
            self.assertEqual(len(pd.read_csv(root/'templates'/'kpi_agreges.csv')),0)
            self.assertTrue((root/'templates'/'questionnaire_local.csv').exists())
            self.assertFalse((root/'research_inputs').exists())
    def test_real_aggregate_import_with_commune_code_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'inputs').mkdir()
            pd.DataFrame([kpi()]).to_csv(root/'inputs'/'kpi_agreges.csv',index=False)
            result=prepare_mobility_metrics(dict(workdir=directory,overview=pd.DataFrame({'commune_code':['01001']})))
            self.assertEqual(result['kpis'].iloc[0].commune_code,'01001')
            self.assertEqual(result['kpis'].iloc[0].value,50)
            self.assertTrue((root/'research_inputs'/'kpi_agreges.csv').exists())


if __name__=='__main__': unittest.main()
