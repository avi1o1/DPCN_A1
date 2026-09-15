"""
Shared loading helpers for the dynamics analysis.

Reads the graphs, scores and metrics that `src/` already produced and writes its own
outputs alongside them. Centralises two things that are easy to get wrong:
node ids are strings in the GraphML files and in `data/metrics.json` but
integers in the index of `data/cleaned_scores.csv`, and every matrix is built
against an explicit nodelist so rows always line up with the score table.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

SRC_DIR = Path(__file__).resolve().parent
ROOT = SRC_DIR.parent

DATA_DIR = ROOT / "data"
GRAPH_DIR = DATA_DIR / "graphs"

RESULTS_DIR = DATA_DIR
FIGURES_DIR = ROOT / "figures"
RESULTS_JSON = RESULTS_DIR / "dynamics_metrics.json"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

NETWORKS = ["overall", "technology", "education", "ethics", "environment"]
TOPICS = ["Technology", "Education", "Ethics", "Environment"]

SEED = 20260920


def load_scores() -> pd.DataFrame:
    """Per-respondent question scores, index cast to str to match the graphs."""
    scores = pd.read_csv(DATA_DIR / "cleaned_scores.csv", index_col="respondent_id")
    scores.index = scores.index.astype(str)
    return scores


def load_meta() -> dict:
    return json.loads((DATA_DIR / "question_meta.json").read_text())


def load_metrics() -> dict:
    return json.loads((DATA_DIR / "metrics.json").read_text())


def load_graph(name: str) -> nx.Graph:
    return nx.read_graphml(GRAPH_DIR / f"network_{name.lower()}.graphml")


def load_similarity(name: str) -> np.ndarray:
    """Full N x N cosine similarity, unthresholded, with a zeroed diagonal."""
    return np.load(GRAPH_DIR / f"similarity_{name.lower()}.npy")


def load_all() -> dict:
    scores = load_scores()
    graphs = {name: load_graph(name) for name in NETWORKS}
    nodes = list(scores.index)

    for name, g in graphs.items():
        missing = set(nodes) ^ set(g.nodes())
        if missing:
            raise ValueError(f"node set mismatch between scores and {name}: {missing}")

    return {
        "scores": scores,
        "nodes": nodes,
        "graphs": graphs,
        "meta": load_meta(),
        "metrics": load_metrics(),
    }


def adjacency(g: nx.Graph, nodes: list[str], weighted: bool = False) -> np.ndarray:
    return nx.to_numpy_array(
        g, nodelist=nodes, weight="weight" if weighted else None, dtype=float
    )


def topic_means(scores: pd.DataFrame, meta: dict, impute_zero: bool = True) -> pd.DataFrame:
    """Mean score per respondent per topic, plus an `overall` column.

    Missing answers are imputed with 0 to match what `src/build_network.py` did
    before computing similarity, so opinions and graph structure agree.
    """
    frame = scores.fillna(0.0) if impute_zero else scores

    out = {}
    for topic in TOPICS:
        cols = [c for c, m in meta.items() if m["topic"] == topic]
        out[topic.lower()] = frame[cols].mean(axis=1)
    out["overall"] = frame.mean(axis=1)
    return pd.DataFrame(out)


def initial_opinions(
    scores: pd.DataFrame, meta: dict, topic: str = "overall", impute_zero: bool = True
) -> np.ndarray:
    """Starting opinion vector x(0) in canonical node order."""
    means = topic_means(scores, meta, impute_zero=impute_zero)
    return means[topic].to_numpy(dtype=float)


def write_results(section: str, payload: dict) -> None:
    """Merge one section into `data/dynamics_metrics.json`."""
    existing = {}
    if RESULTS_JSON.exists():
        existing = json.loads(RESULTS_JSON.read_text())

    existing[section] = payload
    RESULTS_JSON.write_text(json.dumps(existing, indent=2, default=_jsonable))
    print(f"  wrote data/{RESULTS_JSON.name} [{section}]")


def _jsonable(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"not JSON serialisable: {type(obj)}")


def save_figure(fig, name: str) -> None:
    path = FIGURES_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  wrote figures/{name}")
