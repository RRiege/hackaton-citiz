"""Controles sur les resultats reels, complement BI et lecture des tables Delta."""
from pathlib import Path
import numpy as np
import pandas as pd
import json


def validate_and_complete(result):
    import notebookutils
    import pyarrow as pa
    from deltalake import DeltaTable, write_deltalake
    cells, selected = result["cells"], result["selection"]
    cfg = Config(**json.loads((result["output"]/"config.json").read_text()))
    assert cells.cell_id.is_unique
    assert selected.candidate_id.is_unique
    assert selected.cost_total_eur.sum() <= cfg.budget_eur
    assert np.isclose(selected.new_population.sum(), cells.loc[cells.added_by_scenario, "population"].sum())
    assert selected.points_age.le(5).all()
    assert result["candidates"].priority_score.dropna().between(0, 100).all()
    summary = pd.DataFrame(cells.drop(columns="geometry")).copy()
    summary["population_covered"] = summary.population*summary.citiz_covered
    summary["population_added"] = summary.population*summary.added_by_scenario
    kpis = summary.groupby(["commune_code", "commune"], as_index=False).agg(
        population=("population", "sum"), population_covered=("population_covered", "sum"),
        population_added=("population_added", "sum"), households=("households", "sum"),
        no_car_households_proxy=("no_car_households_proxy", "sum"))
    result["tables"]["citiz_v1_commune_kpis"] = kpis
    root = f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSES['gold']}"
    options = {"bearer_token": notebookutils.credentials.getToken("storage"), "use_fabric_endpoint": "true"}
    write_deltalake(root+"/Tables/dbo/citiz_v1_commune_kpis", pa.Table.from_pandas(kpis, preserve_index=False),
                    mode="overwrite", schema_mode="overwrite", storage_options=options)
    verified = []
    for name, frame in result["tables"].items():
        disk = DeltaTable(root+"/Tables/dbo/"+name, storage_options=options).to_pandas()
        assert len(disk) == len(frame), f"Lecture incoherente: {name}"
        verified.append({"table": name, "rows_verified": len(disk)})
    report = pd.DataFrame(verified)
    report.to_csv(result["output"]/"validation.csv", index=False)
    kpis.to_parquet(result["output"]/"citiz_v1_commune_kpis.parquet", index=False)
    kpis.to_csv(result["output"]/"citiz_v1_commune_kpis.csv", index=False)
    print("VALIDATION REELLE OK : budget, gain unique, bonus age, 8 tables relues.")
    display(report)
    return report


if "result" in globals():
    validation = validate_and_complete(result)
