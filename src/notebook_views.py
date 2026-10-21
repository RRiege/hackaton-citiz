"""Deux vues du premier jet, rendues directement dans le notebook Fabric."""
from IPython.display import display, HTML


def show_decision(result):
    cells = result["cells"]
    selected = result["selection"]
    count = len(selected)
    new_population = selected.new_population.sum()
    cost = selected.cost_total_eur.sum()
    display(HTML(f"""
    <div style='font-family:Segoe UI,sans-serif;background:#102d38;color:white;padding:24px;border-radius:12px'>
      <span style='color:#7de0c0;font-size:12px;letter-spacing:2px'>CITIZ HELPER / PREMIER JET</span>
      <h2 style='color:white;margin:10px 0'>Ou rendre une voiture partagee utile ?</h2>
      <p>Metropole de Lyon · Donnees reelles · Python natif · Sans Spark</p>
      <div style='display:flex;gap:35px;flex-wrap:wrap'>
        <div><strong style='font-size:30px'>{count}</strong><br>stations dans le scenario</div>
        <div><strong style='font-size:30px'>{new_population:,.0f}</strong><br>habitants nouvellement proches</div>
        <div><strong style='font-size:30px'>{cost:,.0f} EUR</strong><br>cout suppose sur 3 ans</div>
      </div>
    </div>
    <p><b>Lecture :</b> la chaleur montre un besoin potentiel : menages sans voiture estimes,
    lacunes de transport et absence de Citiz proche. Les points verts sont le scenario sous budget.
    Le menu de la carte donne acces aux stations et aux carreaux d'analyse.</p>
    <p><b>A valider :</b> permis non observes ; motorisation estimee au taux communal ;
    bonus leger 25-39 ans ; couts pedagogiques sans devis ; rayon aerien 400m et parking non verifie.</p>
    """))
    display(result["map"])
    columns = ["selection_order", "commune", "priority_score", "new_population", "new_no_car_households_proxy", "cost_total_eur", "points_age", "cost_penalty"]
    display(selected[columns].rename(columns={
        "selection_order": "Ordre", "commune": "Commune", "priority_score": "Score marginal",
        "new_population": "Habitants supplementaires", "new_no_car_households_proxy": "Menages sans voiture (proxy)",
        "cost_total_eur": "Cout suppose 3 ans", "points_age": "Bonus age", "cost_penalty": "Penalite cout"}).round(1))


def show_analysis(result):
    display(HTML("<h2>Vue Analyse · comprendre et contester le classement</h2><p>Les poids sont des hypotheses. Le score n'est ni une probabilite de reservation, ni une preuve de rentabilite.</p>"))
    display(result["candidates"].head(30).round(3))
    display(HTML("<h3>Dates de desserte effectivement utilisees</h3>"))
    display(result["service_dates"])
    cells = result["cells"]
    quality = {
        "Carreaux habites": len(cells),
        "Population Filosofi 2021": round(cells.population.sum()),
        "Carreaux imputes INSEE": int(cells.i_est_200.eq(1).sum()),
        "Carreaux avec motorisation manquante": int(cells.no_car_rate.isna().sum()),
        "Bonus maximum 25-39": "5 points, desactivable",
        "Permis": "non mesure - aucun nombre de titulaires invente",
        "Distance": "400m a vol d'oiseau, pas 5 minutes de marche calculees",
        "Couts": "hypotheses uniformes remplacables par cost_overrides.csv",
        "Definition deficit TC": "meilleur arret proche, pas somme de passages ni frequentation",
    }
    import pandas as pd
    display(pd.DataFrame(quality.items(), columns=["Controle", "Valeur"]))
    display(result["sources"])


if "result" in globals():
    show_decision(result)
    show_analysis(result)
