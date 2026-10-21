"""Publication CSV OneLake, aucun nouveau fichier Parquet ni table Delta.

Les tables Delta de l'ancien prototype Lyon ne sont pas la sortie nationale.
Un rapport Power BI doit importer ces CSV ou utiliser un Dataflow configure.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json

FR_WORKSPACE='0532a204-3933-4804-9064-1224447ebbb3'
FR_LAKEHOUSES={'bronze':'3d7404d6-b36f-4b7c-97bd-aa9627ede34e',
               'silver':'2ff2289f-ff48-4d67-b329-22ea66ba3d52',
               'gold':'e22a30e8-658f-4bfd-81a6-0dbb773d1298'}


def restore_france_cache(workdir='/tmp/citiz_france',department=None,verbose=False):
    """Reprise CSV OneLake apres redemarrage ; grilles departementales a la demande."""
    import notebookutils
    root=Path(workdir); count=0
    def remote(layer,relative):
        return f'abfss://{FR_WORKSPACE}@onelake.dfs.fabric.microsoft.com/{FR_LAKEHOUSES[layer]}/Files/citiz_france/{relative}'
    jobs=[]
    if department is not None:
        folder=remote('silver','cells/'+str(department))
        if notebookutils.fs.exists(folder):
            jobs=[(entry.path,root/'cells'/str(department)/entry.name) for entry in notebookutils.fs.ls(folder) if entry.name.endswith('.csv')]
    elif not (root/'output'/'citiz_fr_communes.csv').exists():
        files=['citiz_fr_communes.csv','citiz_fr_stations.csv','citiz_fr_sources.csv','citiz_fr_quality.csv']
        if all(notebookutils.fs.exists(remote('gold','output/'+name)) for name in files):
            jobs=[(remote('gold','output/'+name),root/'output'/name) for name in files]
            jobs += [(remote('bronze','raw/'+name),root/'raw'/name) for name in ['emp2019.zip','emp2019_dictionary.xlsx'] if notebookutils.fs.exists(remote('bronze','raw/'+name))]
    for src,destination in jobs:
        if destination.exists(): continue
        destination.parent.mkdir(parents=True,exist_ok=True)
        notebookutils.fs.cp(src,'file:'+str(destination),False); count+=1
    if department is None:
        for name in ['kpi_agreges.csv','enquete_agregee.csv']:
            source=remote('bronze','inputs/'+name)
            if notebookutils.fs.exists(source):
                destination=root/'inputs'/name; destination.parent.mkdir(exist_ok=True,parents=True)
                notebookutils.fs.cp(source,'file:'+str(destination),False); count+=1
    if verbose: print('REPRISE CSV OneLake :',count,'fichiers.',flush=True)
    return count

def publish_france_files(france, only_scenario=None, include_raw=False, include_cells=True,verbose=False):
    import notebookutils
    try:
        from citiz_france import STUDY_DEPARTMENTS as allowed_departments
    except ImportError:
        allowed_departments=globals()['STUDY_DEPARTMENTS']
    root=Path(france['workdir'])
    def target(layer,relative):
        return f'abfss://{FR_WORKSPACE}@onelake.dfs.fabric.microsoft.com/{FR_LAKEHOUSES[layer]}/Files/citiz_france/{relative}'
    if only_scenario is not None:
        groups=[(Path(only_scenario),'gold','scenarios/'+Path(only_scenario).name)]
    else:
        groups=[(root/'output','gold','output'),(root/'code','gold','code'),
                (root/'diagnostics','gold','diagnostics'),
                (root/'bronze_metadata','bronze','metadata'),(root/'silver_metadata','silver','prepared'),
                (root/'research_raw','bronze','raw/enquetes'),(root/'research_inputs','bronze','inputs'),
                (root/'templates','gold','templates')]
        if include_cells: groups.append((root/'cells','silver','cells'))
        if include_raw: groups.append((root/'raw','bronze','raw'))
    jobs=[]
    for folder,layer,prefix in groups:
        if not folder.exists(): continue
        for file in folder.rglob('*'):
            if file.is_file() and file.suffix not in {'.part','.parquet'}:
                if prefix=='cells' and file.relative_to(folder).parts[0] not in allowed_departments: continue
                relative=prefix+'/'+file.relative_to(folder).as_posix()
                jobs.append((file,target(layer,relative)))
    for parent in sorted({t.rsplit('/',1)[0] for _,t in jobs}): notebookutils.fs.mkdirs(parent)
    def copy(item):
        file,t=item
        notebookutils.fs.cp('file:'+str(file),t,False)
        return dict(file=str(file.relative_to(root)),size_bytes=file.stat().st_size,target=t)
    with ThreadPoolExecutor(max_workers=4) as pool: records=list(pool.map(copy,jobs))
    manifest=root/'publication_csv.json'
    manifest.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    notebookutils.fs.cp('file:'+str(manifest),target('gold','publication_csv.json'),False)
    if verbose: print('FRANCE CSV PUBLIEE :',len(records),'fichiers OneLake, aucune nouvelle table Delta.',flush=True)
    return records
