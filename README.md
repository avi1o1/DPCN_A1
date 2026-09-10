# Opinion Network Formation — Team "Deadlines Passing, Care Not"

Assignment: build and analyze a network from the class survey on Technology, Education,
Ethics, and Environment opinions (DPCN course, Assignment 1).

## Status

- [x] Data cleaning, network construction, structural analysis, centralities, communities,
      static visualizations — done (Aviral). See `report/AVIRAL.md` (method + analysis/insights).
- [ ] Dynamics / heavy math (opinion dynamics simulation, epidemic-threshold analysis,
      ER null-model comparison) — see `report/VARUN_tasks.md`.
- [ ] Interactive dashboard — see `report/ARIHANT_tasks.md`.
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

## Project layout

```
data/
  survey_data.csv        raw export
  cleaned_scores.csv     cleaned, numeric, per-respondent scores
  question_meta.json     question code -> {topic, text}
  graphs/                GraphML networks + raw similarity matrices
  metrics.json           structural metrics, centralities, communities per network
src/
  data_prep.py
  build_network.py
  analysis.py
  visualize.py
figures/                 static PNG plots
dashboard/                interactive dashboard (Arihant)
report/                  handoff docs + eventual report PDF
```
