"""Collecter les sources et exporter les chiffres publics verifies, sans Spark."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import pandas as pd
from mobility_metrics import archive_research_sources, prepare_mobility_metrics

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--workdir',default='data/collecte_usages')
args=parser.parse_args()
root=Path(args.workdir); root.mkdir(parents=True,exist_ok=True)
manifest=archive_research_sources(root)
result=prepare_mobility_metrics(dict(workdir=root,overview=pd.DataFrame({'commune_code':[]})))
print(manifest[['source_id','status']].to_string(index=False))
print(len(result['public_observations']),'chiffres publics verifies, ecrits dans',root/'output'/'citiz_fr_usages_publics.csv')
