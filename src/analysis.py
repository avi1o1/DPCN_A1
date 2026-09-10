"""
Core network analysis: structural metrics, centralities, and community
detection for the overall opinion network and each per-topic network.

Writes a single `data/metrics.json` summary that downstream work (dashboard,
report, teammates' deeper analysis) can read without recomputing anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import numpy as np
from networkx.algorithms.community import modularity
from community import community_louvain  # python-louvain

ROOT = Path(__file__).resolve().parent.parent
GRAPH_DIR = ROOT / "data" / "graphs"
METRICS_JSON = ROOT / "data" / "metrics.json"


def load_graph(name: str) -> nx.Graph:
    path = GRAPH_DIR / f"network_{name.lower()}.graphml"
    return nx.read_graphml(path)


def structural_summary(g: nx.Graph) -> dict:
    degrees = dict(g.degree())
    deg_values = list(degrees.values())

    components = list(nx.connected_components(g))
    largest_cc = max(components, key=len)
    giant = g.subgraph(largest_cc).copy()

    summary = {
        "n_nodes": g.number_of_nodes(),
        "n_edges": g.number_of_edges(),
        "density": nx.density(g),
        "avg_degree": float(np.mean(deg_values)),
        "avg_clustering": nx.average_clustering(g),
        "n_components": len(components),
        "giant_component_fraction": len(largest_cc) / g.number_of_nodes(),
        "giant_component_diameter": (
            nx.diameter(giant) if giant.number_of_nodes() > 1 else 0
        ),
        "giant_component_avg_path_length": (
            nx.average_shortest_path_length(giant)
            if giant.number_of_nodes() > 1
            else 0.0
        ),
        "degree_sequence": sorted(deg_values, reverse=True),
    }
    return summary


def centralities(g: nx.Graph) -> dict:
    degree_c = nx.degree_centrality(g)
    closeness_c = nx.closeness_centrality(g)
    betweenness_c = nx.betweenness_centrality(g, weight=None)
    try:
        eigen_c = nx.eigenvector_centrality(g, max_iter=1000, weight="weight")
    except nx.PowerIterationFailedConvergence:
        eigen_c = {n: float("nan") for n in g.nodes()}

    def top5(d: dict) -> list[tuple[str, float]]:
        return sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "degree_top5": top5(degree_c),
        "closeness_top5": top5(closeness_c),
        "betweenness_top5": top5(betweenness_c),
        "eigenvector_top5": top5(eigen_c),
        "degree_centrality": degree_c,
        "closeness_centrality": closeness_c,
        "betweenness_centrality": betweenness_c,
        "eigenvector_centrality": eigen_c,
    }


def communities(g: nx.Graph) -> dict:
    partition = community_louvain.best_partition(g, weight="weight", random_state=42)
    n_communities = len(set(partition.values()))
    mod = community_louvain.modularity(partition, g, weight="weight")

    sizes = {}
    for node, comm in partition.items():
        sizes[comm] = sizes.get(comm, 0) + 1

    return {
        "partition": partition,
        "n_communities": n_communities,
        "modularity": mod,
        "community_sizes": sizes,
    }


def analyse_all() -> dict:
    names = ["overall", "technology", "education", "ethics", "environment"]
    results = {}
    for name in names:
        g = load_graph(name)
        results[name] = {
            "structure": structural_summary(g),
            "centrality": centralities(g),
            "community": communities(g),
        }
    METRICS_JSON.write_text(json.dumps(results, indent=2, default=str))
    return results


if __name__ == "__main__":
    results = analyse_all()
    for name, res in results.items():
        s = res["structure"]
        c = res["community"]
        print(
            f"{name:12s} N={s['n_nodes']:3d} L={s['n_edges']:4d} "
            f"<k>={s['avg_degree']:.2f} C={s['avg_clustering']:.3f} "
            f"components={s['n_components']} giant_frac={s['giant_component_fraction']:.2f} "
            f"communities={c['n_communities']} Q={c['modularity']:.3f}"
        )
    print(f"\nWrote {METRICS_JSON}")
