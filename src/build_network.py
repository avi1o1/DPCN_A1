"""
Opinion network construction.

Nodes are survey respondents. Two respondents are linked if their opinion
vectors (Likert scores mapped to [-2, 2]) are sufficiently similar, measured
by cosine similarity. Missing answers ("No Comments") are imputed as 0
(neutral) so every respondent contributes a full-length vector.

Produces:
  - one overall network built from all 60 questions
  - one network per topic (Technology / Education / Ethics / Environment)
    built from that topic's 15 questions only

Graphs are saved as GraphML (for teammates / Gephi / further analysis) and
node similarity matrices as .npy for reuse.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parent.parent
SCORES_CSV = ROOT / "data" / "cleaned_scores.csv"
META_JSON = ROOT / "data" / "question_meta.json"
GRAPH_DIR = ROOT / "data" / "graphs"
GRAPH_DIR.mkdir(parents=True, exist_ok=True)

# Keep the top SIMILARITY_QUANTILE fraction of pairwise similarities as edges.
# This keeps the graph sparse enough for meaningful community/centrality analysis
# instead of the near-complete graph you'd get from a raw threshold on Likert data.
SIMILARITY_QUANTILE = 0.90


def load_data() -> tuple[pd.DataFrame, dict]:
    scores = pd.read_csv(SCORES_CSV, index_col="respondent_id")
    meta = json.loads(META_JSON.read_text())
    return scores, meta


def topic_columns(meta: dict, topic: str | None) -> list[str]:
    if topic is None:
        return list(meta.keys())
    return [c for c, m in meta.items() if m["topic"] == topic]


def build_similarity_graph(
    scores: pd.DataFrame, cols: list[str], quantile: float = SIMILARITY_QUANTILE
) -> tuple[nx.Graph, np.ndarray]:
    """Build a weighted, undirected similarity graph over respondents.

    Missing values are imputed with 0 (neutral) before computing cosine
    similarity, since a respondent skipping a question is closer to "no
    strong opinion" than to any specific stance.
    """
    matrix = scores[cols].fillna(0.0).to_numpy()
    sim = cosine_similarity(matrix)
    np.fill_diagonal(sim, 0.0)

    threshold = np.quantile(sim[np.triu_indices_from(sim, k=1)], quantile)

    g = nx.Graph()
    g.add_nodes_from(scores.index)
    n = len(scores.index)
    ids = scores.index.to_numpy()
    for i in range(n):
        for j in range(i + 1, n):
            w = sim[i, j]
            if w >= threshold:
                g.add_edge(ids[i], ids[j], weight=float(w))
    return g, sim


def build_all_networks() -> dict[str, nx.Graph]:
    scores, meta = load_data()
    topics = sorted({m["topic"] for m in meta.values()})

    networks = {}

    g_overall, sim_overall = build_similarity_graph(scores, topic_columns(meta, None))
    networks["overall"] = g_overall
    np.save(GRAPH_DIR / "similarity_overall.npy", sim_overall)
    nx.write_graphml(g_overall, GRAPH_DIR / "network_overall.graphml")

    for topic in topics:
        cols = topic_columns(meta, topic)
        g, sim = build_similarity_graph(scores, cols)
        networks[topic] = g
        np.save(GRAPH_DIR / f"similarity_{topic.lower()}.npy", sim)
        nx.write_graphml(g, GRAPH_DIR / f"network_{topic.lower()}.graphml")

    return networks


if __name__ == "__main__":
    networks = build_all_networks()
    for name, g in networks.items():
        n, l = g.number_of_nodes(), g.number_of_edges()
        density = nx.density(g)
        print(f"{name:12s} N={n:3d}  L={l:4d}  density={density:.3f}")
    print(f"\nGraphs written to {GRAPH_DIR}")
