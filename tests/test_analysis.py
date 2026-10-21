import sys,unittest,tempfile
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from analysis_views import build_analysis_tables,analysis_report,export_analysis_tables
from france_interactive import territory_metrics
from citiz_france import france_rank
from test_map_views import sample


class AnalysisTables(unittest.TestCase):
    def test_geographic_tables_and_score_components(self):
        data=france_rank(sample())
        tables=build_analysis_tables({'overview':sample(),'sources':pd.DataFrame({'status':['ok']})},data,None,territory_metrics)
        self.assertEqual(len(tables),7)
        dep=tables['departements'].iloc[0]
        self.assertAlmostEqual(dep[('Transports','A plus de 400 m des arrets %')],100*1850/3000)
        self.assertAlmostEqual(dep[('Citiz','A moins de 400 m %')],100*1300/3000)
        self.assertEqual(dep[('Population','Etudiee')],3000)
        self.assertEqual(tables['distribution']['Nombre de lignes'].sum(),2)
        self.assertNotIn(('Finances','Cout sur horizon EUR'),tables['decomposition'].columns)
        self.assertIsInstance(tables['classement'].columns,pd.MultiIndex)
        self.assertIn('colspan',analysis_report(tables))
        with tempfile.TemporaryDirectory() as folder:
            export_analysis_tables(tables,folder)
            self.assertEqual(len(list(Path(folder).glob('*.csv'))),7)
            self.assertEqual(len(pd.read_csv(Path(folder)/'analyse_classement.csv')),2)

    def test_local_geographic_totals_use_cells_not_overlapping_radii(self):
        candidates=pd.DataFrame(dict(commune_code=['01001','01001'],commune=['Alpha','Alpha'],
            priority_score=[30.,40.],new_population=[9999.,9999.],new_licensed_adults_no_car_estimate=[500.,500.]))
        cells=pd.DataFrame(dict(cell_id=['a','b'],commune_code=['01001','01001'],population=[100.,300.],
            nearest_stop_m=[0.,800.],citiz_covered=[True,False],licensed_adults_no_car_estimate=[10.,30.]))
        tables=build_analysis_tables({'overview':sample()},candidates,cells,territory_metrics)
        dep=tables['departements'].iloc[0]
        self.assertEqual(dep[('Population','Etudiee')],400)
        self.assertEqual(dep[('Cible','Permis hors Citiz estime')],30)
        self.assertEqual(dep[('Transports','A plus de 400 m des arrets %')],75)
        self.assertIn('ne s’additionnent pas',analysis_report(tables,True))


if __name__=='__main__':unittest.main()
