# Varun's part — dynamics & the heavy math

Everything structural (network construction, degree/clustering/centrality/communities) is already done — see `report/AVIRAL.md` and `data/metrics.json`. Your part is the stuff that actually needs the course's dynamical-systems machinery, not just graph metrics. Load the existing graphs/data, don't rebuild them.

**Load like this:**
```python
import json, numpy as np, networkx as nx, pandas as pd
g = nx.read_graphml("data/graphs/network_overall.graphml")   # weight="weight" on edges
sim = np.load("data/graphs/similarity_overall.npy")           # full N x N cosine similarity, unthresholded
scores = pd.read_csv("data/cleaned_scores.csv", index_col="respondent_id")
meta = json.loads(open("data/question_meta.json").read())
metrics = json.loads(open("data/metrics.json").read())        # my structural results, keyed by network name
```

## Suggested tasks (pick what fits your ~2-3 pages; don't need all of them)

### 1. Opinion dynamics simulation on the network (this is the core "dynamical process")

Treat each respondent's initial opinion as their mean overall score (or per-topic score), and simulate how opinions would evolve if people iteratively averaged with their network neighbours — this is the **DeGroot model**:

$$x_i(t+1) = \sum_{j} w_{ij}\, x_j(t), \quad \text{where } w_{ij} = A_{ij} / k_i \text{ (row-normalized adjacency)}$$

- Run it on `network_overall` (and maybe one topic network) starting from each respondent's real score, iterate ~30-50 steps, plot opinion trajectories over time.
- Because the network is fragmented (37 components), each component converges to its *own* consensus value (the degree-weighted average within that component) rather than one global consensus — that's a real, reportable finding tying directly into "what does the network reveal about class opinions" (echo chambers / lack of global consensus).
- Compare convergence speed to each component's algebraic connectivity (second-smallest Laplacian eigenvalue, `nx.laplacian_spectrum`) — bigger λ₂ ⇒ faster convergence. This is a direct, gradeable application of §6 (Laplacian) + the course's discrete-map stability criterion (§13/§18: stable iff the update matrix's relevant eigenvalue has magnitude < 1).
- Optional: also run a **voter model** (each step, a random node copies a random neighbour's *binarized* opinion, e.g. sign of their score) and compare time-to-consensus vs DeGroot.

### 2. Epidemic-style threshold analysis (treat "extreme opinion" as a contagion)

The course's SIS-on-networks threshold is $(\beta/\gamma)_c = 1/\lambda_{\max}$ where $\lambda_{\max}$ is the largest eigenvalue of the adjacency matrix. Compute $\lambda_{\max}$ for each network (`nx.adjacency_spectrum` or `np.linalg.eigvals` on the dense adjacency) and discuss: a denser/more clustered opinion-network (e.g. Technology, giant_frac=0.75) has a higher $\lambda_{\max}$ → a strong opinion would spread/reinforce more easily than in a fragmented one (Environment/Ethics). You can literally simulate SIS with "infected" = "holds the majority view" and check where it dies out vs. spreads, as a toy illustration.

### 3. Null-model comparison (is this really different from a random graph?)

Build an Erdős–Rényi graph `G(N, p)` with the same N and same density as `data/metrics.json[...]["structure"]["density"]` (`nx.gnp_random_graph`), and compare: clustering coefficient (ours: see `avg_clustering` in metrics.json vs ER's expected `C=p`); average path length (ours vs ER's `ln(N)/ln(<k>)` prediction, §12 Property 3); giant component fraction (ours vs the ER prediction `S = 1 - e^{-<k>S}`, solve numerically). This directly answers "is the opinion network small-world / does it match theory" — a good Results/Discussion paragraph, and it's the "heavy" derivation-based content the mid-sem/quizzes actually test.

### 4. Statistical significance of the communities

Test whether the Louvain communities found in `data/metrics.json` are more opinion-homogeneous than chance: permute the community labels randomly (keeping sizes fixed) many times, recompute within-community opinion variance each time, and get a p-value for the real partition's variance being lower than random. Simple, standard, and adds real statistical weight.

## What to hand back

A short script (e.g. `src/dynamics.py`) that reproduces your numbers, writing results to `data/dynamics_metrics.json` (mirror the style of `data/metrics.json`) and any plots to `figures/` with a `dynamics_` prefix, so nothing collides with the existing files. Also write 1-2 paragraphs for the **Results and Discussion** section, plus whatever figures you generate for **Analysis and Visualizations** — the report skeleton isn't written yet, just make sure your file/figure names are self-explanatory since whoever assembles the final PDF will need to caption them without asking you first.
