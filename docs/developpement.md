# Developpement et depot Git

## Installation

Utiliser Python 3.12 et les dependances du projet national :

```sh
python -m venv .venv
python -m pip install -r requirements-france.txt
python -m unittest discover -s tests -v
```

Activer l'environnement virtuel avant l'installation (`.venv\Scripts\Activate.ps1` sous PowerShell ou `source .venv/bin/activate` sous Linux/macOS).

## Sources et notebook

Modifier les modules de `src/`, puis regenerer le notebook autonome :

```sh
python scripts/build_france_notebook.py
```

Versionner ensemble les modules et `notebooks/citiz_france.ipynb`. Le notebook genere ne contient aucune sortie d'execution. Les modifications realisees directement dans Fabric doivent etre reportees dans les modules avant regeneration. La disposition en cellules du notebook autonome peut differer des trois cellules compactees de la session Fabric existante.

Le workflow `.github/workflows/checks.yml` execute les tests et verifie cette synchronisation sur GitHub. Les tests utilisent des fixtures et n'exigent ni connexion Fabric ni telechargement national. Ils ne valident pas l'exhaustivite des donnees de terrain.

## Contenu du depot

- `src/`, `scripts/`, `tests/` : code, construction du notebook et controles.
- `notebooks/` : notebook national et ancien prototype local identifie dans le README.
- `docs/` : architecture Bronze/Argent/Or, metriques, cartes et provenance.
- `data/public/` : petits releves publics avec leurs references ; pas les archives nationales.

Caches, donnees volumineuses, sorties, journaux, captures locales et fichiers `.env` sont exclus par `.gitignore`. Les donnees d'exploitation et reponses individuelles n'ont pas leur place dans le depot.

`src/france_fabric_files.py` contient actuellement les identifiants du workspace et des trois Lakehouses de l'equipe. Ce sont des identifiants de ressources, pas des secrets d'authentification. Ils doivent etre adaptes pour executer le projet dans un autre workspace. L'acces OneLake depend de la session Fabric et de ses permissions.

Les dependances de `requirements.txt` concernent aussi l'ancien prototype ; `requirements-france.txt` est la reference du pipeline national Python/CSV. Le code ne remplace pas la configuration d'un rapport Power BI.

## Depot de l'equipe

Depot public du projet : [RRiege/hackaton-citiz](https://github.com/RRiege/hackaton-citiz). Ne pas utiliser le depot ESP ni les depots Melon-Trick.

Pour reprendre sur une autre machine, cloner le depot Citiz confirme avec un compte autorise. Verifier le compte de `gh auth status` avant les commandes GitHub CLI : il peut differer de celui du navigateur. Ne jamais ajouter de jeton dans une URL Git, un fichier source ou un notebook.

Utiliser des messages de commit conventionnels : `feat:`, `fix:`, `docs:`, `test:`, `chore:` ou `revert:` selon la modification.

Verifier le contenu de chaque commit et les droits des fichiers tiers. Ne pas attribuer une licence aux documents ou donnees de tiers via la licence du code.
