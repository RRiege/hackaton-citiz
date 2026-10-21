from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
def code(text): return dict(cell_type='code',metadata={},source=text.splitlines(True),execution_count=None,outputs=[])
cells=[dict(cell_type='markdown',metadata={},source=['# Citiz France — carte interactive et recalcul Python\n','Python natif, sans Spark. Fichiers CSV. Vue nationale des territoires et détail 200 m par département.\n']),
       code('import sys, subprocess, importlib.util\nnames=["pandas","numpy","scipy","pyproj","folium","ipywidgets"]\nmissing=[n for n in names if importlib.util.find_spec(n) is None]\nif missing: subprocess.check_call([sys.executable,"-m","pip","install",*missing])\n'),
       code((root/'src/notebook_diagnostics.py').read_text(encoding='utf-8')),
       code((root/'src/mobility_metrics.py').read_text(encoding='utf-8')),
       code((root/'src/france_fabric_files.py').read_text(encoding='utf-8')),
       code('with diagnostic_output("/tmp/citiz_france","reprise"):\n    try:\n        restore_france_cache()\n    except ImportError:\n        pass  # hors Fabric\n'),
       code((root/'src/citiz_france.py').read_text(encoding='utf-8')),
       code('with diagnostic_output("/tmp/citiz_france","initialisation"):\n    france=run_france()\n    _mobility=prepare_mobility_metrics(france)\n'),
       code((root/'src/citiz_v1.py').read_text(encoding='utf-8').split('if __name__ == "__main__":')[0]),
       code((root/'src/analysis_views.py').read_text(encoding='utf-8')),
       code((root/'src/france_interactive.py').read_text(encoding='utf-8')),
       code('fr_dashboard=show_france_interactive(france,render=False)\ndisplay(fr_dashboard["widget"])\nfrom IPython.display import display as _html_display, HTML\n_html_display(HTML(fr_dashboard["state"]["content_html"]),display_id=fr_dashboard["state"]["map_id"])\nfr_dashboard["state"]["map_published"]=True\n'),
       code('with diagnostic_output(france["workdir"],"sources"):\n    archive_research_sources(france["workdir"])\n'),
       code('# Dans Fabric : sauvegarder CSV, cartes et grilles dans OneLake\n_scenario,_ranked,_selected,_map,_local=fr_dashboard["state"]["last"]\nfor _theme in MAP_THEMES:\n    _variant=france_map(france,_ranked,_selected,fr_dashboard["state"]["cells"],theme=_theme)\n    _filename="carte_france.html" if _theme=="priority" else "carte_france_"+_theme+".html"\n    _variant.save(str(Path(france["workdir"])/"output"/_filename))\npublication_csv=publish_france_files(france)\n')]
publication=cells[-1]['source']
cells[-1]=code('with diagnostic_output(france["workdir"],"publication"):\n'+''.join('    '+line for line in publication))
notebook=dict(nbformat=4,nbformat_minor=5,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3'),language_info=dict(name='python',version='3.12')),cells=cells)
(root/'notebooks/citiz_france.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=2),encoding='utf-8')
