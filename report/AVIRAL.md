# Aviral's part — data prep, network construction, structural analysis & insights

This covers steps 1–3 of the pipeline: turning the raw survey into cleaned data, building the opinion network(s), running the core structural analysis, and the resulting insights. Everything here is reproducible by running the scripts in `src/` in order (see root `README.md`). Numbers in the Analysis section are copy-checked against `data/metrics.json` / `data/cleaned_scores.csv`, written by hand after looking at the figures, not scripted.

## Method

1. **Data cleaning** (`src/data_prep.py`): mapped the 5-point Likert scale to numeric scores (Strongly Disagree=-2 … Strongly Agree=+2), treated "No Comments" as a missing answer (`NaN`) rather than neutral, and dropped respondents who answered fewer than half of the 60 questions, leaving **87 respondents**. Each question was tagged with its topic from its column prefix: `T`=Technology, `E`=Education, `S`=Ethics, `V`=Environment (15 questions each). Output: `data/cleaned_scores.csv`, `data/question_meta.json`.
2. **Network construction** (`src/build_network.py`): nodes are respondents, and an edge means "these two people hold similar opinions." Edge weight is cosine similarity between opinion vectors (missing answers imputed as 0/neutral first). Only the **top 10% most similar pairs** (90th-percentile cut) become edges, to avoid the near-complete graph you'd get from thresholding raw Likert similarity. Built **5 networks**: `overall` (all 60 questions) plus one per topic (15 questions each). Output: `data/graphs/network_<name>.graphml` and `similarity_<name>.npy` (the full, unthresholded similarity matrix).
3. **Structural analysis** (`src/analysis.py`): degree distribution, average degree, clustering coefficient, connected components, giant-component diameter and average path length, all four centralities (degree/closeness/betweenness/eigenvector, top-5 nodes each), and Louvain community detection, all per network. Output: `data/metrics.json`.
4. **Visualizations** (`src/visualize.py`) → all in `figures/`: `network_<name>.png` (spring layout, coloured by community, isolates greyed out, legend + stats box), `degree_distribution_overall.png` (linear + log-log), `centrality_overall.png` (top-5 per measure, value-labelled), `topic_correlation_heatmap.png`, `community_topic_heatmap.png`, `topic_comparison.png` (giant-component share & clustering by topic), `isolates_vs_connected_overall.png` (opinion extremity, isolated vs. connected).

## Analysis & insights

**Everyone agrees, on average — the interesting variation is in how consistently.** Population mean opinion score (-2..+2) is positive for all four topics: Technology +0.99, Education +0.91, Ethics +1.28, Environment +1.37. There is no topic the class disagrees with on average; this is not a genuinely polarized population. What differs by topic is the spread (std. dev. of each respondent's mean score): Technology 0.37, Education 0.35, Ethics 0.45, Environment 0.47 — Ethics/Environment opinions are both stronger and more variable than Technology/Education opinions.

**Network cohesion tracks opinion variance, not opinion strength.**

| Topic | Population mean | Std dev | Giant component | Avg. clustering | Modularity Q |
|---|---|---|---|---|---|
| Technology | 0.99 | 0.37 | 75% | 0.39 | 0.24 |
| Education | 0.91 | 0.35 | 72% | 0.40 | 0.26 |
| Ethics | 1.28 | 0.45 | 52% | 0.36 | 0.15 |
| Environment | 1.37 | 0.47 | 51% | 0.37 | 0.08 |

This is counter-intuitive at first: Ethics and Environment have the strongest average agreement, yet the most fragmented networks. The explanation is the std-dev column, not the mean column — cosine similarity of a person's answer vector depends on the whole pattern of variation across the 15 questions in that topic, not just the average level. Where opinions are tightly bunched (Technology, Education), most people's vectors end up cosine-similar to most other people's, so the top-10%-similarity graph stays well connected. Where opinions are strong but more spread out (Ethics, Environment), the same threshold slices the population into many disconnected fragments even though almost everyone is "agreeing." Practical takeaway for the report: "the class agrees more on Environment than Technology" is true of the raw Likert average, but false of the network view — Technology is where the class is most mutually aligned in pattern, not just individually positive. See `figures/topic_comparison.png`.

**The well-connected "core" is the enthusiastic-agreement subgroup, not a random cross-section.** Comparing the 36 respondents with zero edges in the overall network to the 51 connected ones (`figures/isolates_vs_connected_overall.png`, `figures/degree_distribution_overall.png`): mean |score| (opinion strength, either direction) is 1.15 for isolated vs. 1.45 for connected respondents — connected respondents are more intense, not more moderate; mean raw score (agreement direction) is 0.89 (isolated) vs. 1.31 (connected); Welch's t-test on |score| gives p ≈ 2.3e-08, not noise. So the giant-component "core" is essentially the subgroup that answers Agree/Strongly Agree almost everywhere, which makes their 60-dimensional vectors cosine-similar to each other — exactly what the network is built to detect. The 36 isolated respondents are not opinion radicals being excluded; they're the more moderate, mixed-Neutral/Agree respondents who don't closely track any single dominant response pattern. Worth stating as a methodological caveat: this particular construction (cosine similarity + top-10% threshold) structurally favours detecting "who strongly agrees with everything" over detecting nuanced or moderate opinion groups — a different construction (e.g. Pearson correlation on centered scores, or a lower similarity threshold) would very likely connect more of these 36 people.

**Centrality measures agree with each other, except on who "bridges" opinion groups.** Degree, closeness and eigenvector centrality pick almost the same five people (114, 67, 94, 105 appear in 3+ of the top-5 lists). All five score above the population mean on every one of the four topics — e.g. respondent 114: Technology +1.47, Education +1.07, Ethics +1.67, Environment +1.93 vs. population means 0.99/0.91/1.28/1.37. They are not "average" people who happen to be well-linked; they're the most uniformly enthusiastic respondents. Betweenness centrality tells a different story: its top node is 41, not 114. Respondent 41 has a maxed-out Technology score (+2.00) but a comparatively lower Education score (+1.20, close to the population mean) — that mixed profile plausibly bridges the "max-agree-on-everything" cluster and other sub-clusters, which is exactly what betweenness rewards and degree doesn't. Takeaway: in this network, "most connected" and "most structurally important as a bridge" are different people — evidence that a single centrality measure isn't enough to describe importance here.

**The detected communities are shades of agreement, not opposing camps.** Louvain communities on the overall network (size ≥ 3), each compared to the population mean:

| Community | n | Distinctive topic | Deviation from population mean |
|---|---|---|---|
| 4 | 14 | Ethics | +0.36 (also Environment +0.30) |
| 2 | 13 | Education | +0.31 (fairly flat elsewhere, +0.2 to +0.3 on all) |
| 6 | 9 | Technology | -0.22 (only negative deviation found) |
| 16 | 8 | Technology | +0.39 (also Environment +0.34) |
| 3 | 7 | Environment | +0.22 |

Every community's mean score is still positive on every topic — none of them disagree with any topic overall, they just amplify or soften agreement on specific topics. Community 6 is the only group that dips below the already-positive population mean on a topic (Technology, -0.22), i.e. a mildly tech-skeptical subgroup relative to everyone else, not an anti-technology one in absolute terms. This is a consensus-shaped population with texture, not a network with real factions — don't over-claim "polarization" in the report; the honest framing is "differences in degree/topic of enthusiasm." See `figures/community_topic_heatmap.png`.

**Ethics and Environment opinions travel together; Technology and Education don't.** Respondent-level topic correlations (`figures/topic_correlation_heatmap.png`): Ethics–Environment r=0.70 (the most correlated pair — a person's stance on "values" questions predicts their stance on the other almost as well as a test-retest would); Technology–Education r=0.29 (the least correlated pair — enthusiasm for tech tells you almost nothing about feelings on educational reform, two largely independent axes of opinion in this cohort). Combined with the variance finding above, a reasonable reading is that Ethics and Environment together form one underlying "values" dimension, while Technology and Education are two separate, more consensual, more institutional dimensions.

**Bottom line for Results & Discussion:** this class is broadly agreeable across all four survey domains — there is no evidence of opposing camps or real disagreement in the raw data. The network reveals structure the raw averages hide: apparent "cohesion" in the similarity network is driven by low opinion variance, not high agreement, so Technology/Education look more "networked" than Ethics/Environment despite lower average scores; the well-connected core is a specific behavioural type (uniform strong agreement) rather than a demographic or topical faction; centrality measures disagree with each other about who is "important," which is itself a finding; and Ethics and Environment opinions appear to share a common underlying "values" axis that Technology and Education don't share with each other.

## Files you (Varun / Arihant) can build directly on top of

| File | What it is |
|---|---|
| `data/cleaned_scores.csv` | respondent_id × 60 question numeric scores (-2..2, NaN = no comment) |
| `data/question_meta.json` | question code → {topic, text} |
| `data/graphs/network_<name>.graphml` | networkx-readable graph, 5 variants |
| `data/graphs/similarity_<name>.npy` | full N×N cosine similarity matrix (no thresholding) — load with `np.load(...)`, row/col order matches `pd.read_csv(SCORES_CSV, index_col="respondent_id").index` |
| `data/metrics.json` | all structural metrics, centralities, community partitions, per network |
| `figures/*.png` | everything already plotted above |

Don't re-clean the data or rebuild the graphs — just run `pip install -r requirements.txt` and import/read from `data/`. If you need a different edge threshold or similarity metric, open an issue/ping me rather than duplicating `build_network.py`.
