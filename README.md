# Opinion Network Formation — Team "Deadlines Passing, Care Not"

Assignment: build and analyze a network from the class survey on Technology, Education,
Ethics, and Environment opinions (DPCN course, Assignment 1).

## Status

- [x] Data cleaning, network construction, structural analysis, centralities, communities,
      static visualizations — done (Aviral). See `report/AVIRAL.md` (method + analysis/insights).
- [x] Dynamics / heavy math (opinion dynamics simulation, epidemic-threshold analysis,
      ER + configuration null models, community permutation test, threshold sensitivity)
      — done (Varun). See `report/VARUN.md` (method + findings + report paragraphs).
- [ ] Interactive dashboard — see `report/ARIHANT_tasks.md`.
      Flat tables ready: run `python src/export_dashboard.py`, see `report/VARUN.md`.
- [ ] Final report PDF assembling everyone's sections.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Pipeline (run in this order)

```bash
python src/data_prep.py      # data/survey_data.csv -> data/cleaned_scores.csv, data/question_meta.json
python src/build_network.py  # -> data/graphs/network_<name>.graphml, similarity_<name>.npy
python src/analysis.py       # -> data/metrics.json (structure + centrality + community, per network)
python src/visualize.py      # -> figures/*.png
```

Networks built: `overall` + one per topic (`technology`, `education`, `ethics`, `environment`).
Nodes = respondents; an edge means two respondents are in the top 10% most similar pairs by
cosine similarity of their (-2..+2) Likert scores.

Then the dynamics on top of those graphs (reads `data/`, never rebuilds it):

```bash
python src/run_all.py           # -> data/dynamics_metrics.json, figures/dynamics_*.png  (~80s)
python src/verify.py            # 21 independent checks of the maths, exit 0 when all pass
python src/check_docs.py        # confirms report/VARUN.md matches the numbers above
python src/export_dashboard.py  # -> data/dashboard_{nodes.csv,networks.csv,curves.json}
```

## Project layout

```
data/
  survey_data.csv        raw export
  cleaned_scores.csv     cleaned, numeric, per-respondent scores
  question_meta.json     question code -> {topic, text}
  graphs/                GraphML networks + raw similarity matrices
  metrics.json           structural metrics, centralities, communities per network
  dynamics_metrics.json  DeGroot, epidemic, null models, threshold sensitivity
  dashboard_*.csv/json   flat tables for the dashboard
src/
  data_prep.py           \
  build_network.py        |  Aviral: cleaning, construction,
  analysis.py             |  structure, static figures
  visualize.py           /
  common.py              \
  degroot.py              |
  epidemic.py             |  Varun: dynamics, epidemic threshold,
  nullmodels.py           |  null models, sensitivity
  sensitivity.py          |
  run_all.py             |  run_all.py runs the four analyses
  verify.py              |  verify.py checks the maths
  check_docs.py          |  check_docs.py checks the writeup
  export_dashboard.py    /   export_dashboard.py feeds the dashboard
figures/                 static PNG plots (dynamics_*.png are Varun's)
dashboard/               interactive dashboard (Arihant, not created yet)
report/                  handoff docs + eventual report PDF
```
