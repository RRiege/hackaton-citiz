"""Publication des sorties V1 dans les Lakehouses attaches, sans Spark."""
from pathlib import Path
import json
import pandas as pd

WORKSPACE_ID = "0532a204-3933-4804-9064-1224447ebbb3"
LAKEHOUSES = {
    "bronze": "3d7404d6-b36f-4b7c-97bd-aa9627ede34e",
    "silver": "2ff2289f-ff48-4d67-b329-22ea66ba3d52",
    "gold": "e22a30e8-658f-4bfd-81a6-0dbb773d1298",
}


def publish(result, workdir="/tmp/citiz_v1"):
    import notebookutils
    import pyarrow as pa
    from deltalake import write_deltalake
    options = {"bearer_token": notebookutils.credentials.getToken("storage"),
               "use_fabric_endpoint": "true"}
    def root(layer):
        return f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSES[layer]}"
    # Les seuls ecrasements concernent les sorties dediees citiz_v1_*.
    published = []
    for name, frame in result["tables"].items():
        path = f"{root('gold')}/Tables/dbo/{name}"
        write_deltalake(path, pa.Table.from_pandas(frame, preserve_index=False),
                        mode="overwrite", schema_mode="overwrite", storage_options=options)
        published.append({"table": name, "rows": len(frame), "path": path})
        print("Table Gold publiee:", name, len(frame), flush=True)
    for directory, layer in [("raw", "bronze"), ("output", "gold")]:
        target = f"{root(layer)}/Files/citiz_v1/{directory}"
        notebookutils.fs.mkdirs(target)
        for file in (Path(workdir)/directory).iterdir():
            if file.is_file() and file.suffix != ".part":
                notebookutils.fs.cp("file:"+str(file), target+"/"+file.name, False)
    # Version nettoyee Silver pour permettre de reprendre les calculs.
    for name, frame in {
        "citiz_v1_population": pd.DataFrame(result["cells"].drop(columns="geometry")),
        "citiz_v1_transit_stops": result["stops"],
    }.items():
        write_deltalake(f"{root('silver')}/Tables/dbo/{name}",
                        pa.Table.from_pandas(frame, preserve_index=False),
                        mode="overwrite", schema_mode="overwrite", storage_options=options)
    result["publication"] = pd.DataFrame(published)
    print("Publication terminee. Modele Power BI a connecter aux tables citiz_v1_*.")
    return result["publication"]


if "result" in globals():
    publication = publish(result)
