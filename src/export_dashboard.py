"""
Flat tables for the dashboard.

`data/dynamics_metrics.json` is nested and keyed for the report. This writes
the same numbers as flat tables that a plotting library can load directly, so
the dashboard does not have to walk the nesting or re-derive anything from the
GraphML.

Run `python export_dashboard.py` after `run_all.py`. Writes three files into
`data/`.
"""

from __future__ import annotations

import json

import numpy as np
import networkx as nx
import pandas as pd

import common as C
import degroot as D

CENTRALITIES = [
    "degree_centrality",
    "closeness_centrality",
    "betweenness_centrality",
    "eigenvector_centrality",
]


def node_table(data: dict) -> pd.DataFrame:
    """One row per respondent, with everything the dashboard might colour by."""
    nodes = data["nodes"]
    metrics = data["metrics"]
    topics = C.topic_means(data["scores"], data["meta"])
    x0 = C.initial_opinions(data["scores"], data["meta"])

    rows = {"respondent_id": nodes, "opinion_overall": x0}
    for topic in C.TOPICS:
        rows[f"opinion_{topic.lower()}"] = topics[topic.lower()].reindex(nodes).to_numpy()

    for name in C.NETWORKS:
        g = data["graphs"][name]
        m = metrics[name]
        A = C.adjacency(g, nodes)

        rows[f"{name}__degree"] = [g.degree(n) for n in nodes]
        rows[f"{name}__is_isolate"] = [g.degree(n) == 0 for n in nodes]
        rows[f"{name}__community"] = [m["community"]["partition"][n] for n in nodes]
        # keep the full name: stripping "_centrality" would collide with the raw
        # degree column above
        for c in CENTRALITIES:
            rows[f"{name}__{c}"] = [m["centrality"][c][n] for n in nodes]

        # where each respondent ends up under the averaging dynamics
        rows[f"{name}__degroot_limit"] = D.predicted_consensus(g, nodes, x0, A)

        giant = max(nx.connected_components(g), key=len)
        rows[f"{name}__in_giant"] = [n in giant for n in nodes]

    return pd.DataFrame(rows)


def network_table(data: dict, results: dict) -> pd.DataFrame:
    """One row per network: Aviral's structure plus the dynamics results."""
    rows = []
    for name in C.NETWORKS:
        structure = data["metrics"][name]["structure"]
        dg = results["degroot"]["unweighted"][name]
        ep = results["epidemic"]["spectral"][name]

        rows.append({
            "network": name,
            "n_nodes": structure["n_nodes"],
            "n_edges": structure["n_edges"],
            "density": structure["density"],
            "avg_degree": structure["avg_degree"],
            "avg_clustering": structure["avg_clustering"],
            "n_components": structure["n_components"],
            "giant_fraction": structure["giant_component_fraction"],
            "modularity": data["metrics"][name]["community"]["modularity"],
            "n_isolated": dg["n_isolated"],
            "n_oscillating": dg["n_oscillating_nodes"],
            "consensus_giant": dg["consensus_giant"],
            "steps_to_converge": dg["steps_to_converge_giant"],
            "algebraic_connectivity": dg["algebraic_connectivity_normalized"],
            "slem": dg["slem"],
            "lambda_max": ep["lambda_max"],
            "epidemic_threshold": ep["threshold_qmf"],
        })
    return pd.DataFrame(rows)


def curve_data(results: dict) -> dict:
    """The two swept curves, as plain x/y lists."""
    sis = {}
    for name, s in results["epidemic"]["sweeps"].items():
        threshold = results["epidemic"]["spectral"][name]["threshold_qmf"]
        sis[name] = {
            "x_ratio_over_threshold": [r / threshold for r in s["ratios"]],
            "y_prevalence": s["prevalence"],
            "giant_size": s["giant_size"],
        }

    threshold_sweep = {}
    for name, rows in results["threshold_sensitivity"]["sweeps"].items():
        quantiles = sorted(rows, key=float)
        threshold_sweep[name] = {
            "x_quantile": [float(q) for q in quantiles],
            "y_giant_fraction": [rows[q]["giant_fraction"] for q in quantiles],
            "y_n_isolates": [rows[q]["n_isolates"] for q in quantiles],
            "y_avg_clustering": [rows[q]["avg_clustering"] for q in quantiles],
            "y_n_edges": [rows[q]["n_edges"] for q in quantiles],
        }

    return {
        "sis_sweep": sis,
        "threshold_sweep": threshold_sweep,
        "baseline_quantile": results["threshold_sensitivity"]["baseline_quantile"],
    }


def main() -> None:
    print("Exporting flat tables for the dashboard")
    data = C.load_all()

    if not C.RESULTS_JSON.exists():
        raise SystemExit("run_all.py has not been run yet, no results to export")
    results = json.loads(C.RESULTS_JSON.read_text())

    nodes = node_table(data)
    networks = network_table(data, results)
    curves = curve_data(results)

    nodes_path = C.RESULTS_DIR / "dashboard_nodes.csv"
    networks_path = C.RESULTS_DIR / "dashboard_networks.csv"
    curves_path = C.RESULTS_DIR / "dashboard_curves.json"

    nodes.to_csv(nodes_path, index=False)
    networks.to_csv(networks_path, index=False)
    curves_path.write_text(json.dumps(curves, indent=2))

    print(f"  wrote data/{nodes_path.name}     {nodes.shape[0]} rows x {nodes.shape[1]} cols")
    print(f"  wrote data/{networks_path.name}  {networks.shape[0]} rows x {networks.shape[1]} cols")
    print(f"  wrote data/{curves_path.name}")


if __name__ == "__main__":
    main()
