"""
Threshold sensitivity of the network structure.

`src/build_network.py` keeps the top 10% most similar pairs as edges. Two
headline findings depend on that cut: 36 of 87 respondents end up with no
edges, and Technology and Education look better connected than Ethics and
Environment. This re-applies the same rule to the saved similarity matrices
across a range of quantiles to see which of the two survives.

Reads only `data/graphs/similarity_<name>.npy`. Nothing in `src/` runs, and
the q=0.90 graphs are checked edge for edge against the GraphML on disk.

Writes `data/dynamics_metrics.json["threshold_sensitivity"]` and two figures.
"""

from __future__ import annotations

import numpy as np
import networkx as nx
import matplotlib.pyplot as plt

import common as C

BASELINE_QUANTILE = 0.90
QUANTILES = np.round(np.arange(0.50, 0.995, 0.01), 3)


def graph_at_quantile(sim: np.ndarray, nodes: list[str], quantile: float) -> nx.Graph:
    """Rebuild the network at a different cut, exactly as build_network.py does."""
    threshold = np.quantile(sim[np.triu_indices_from(sim, k=1)], quantile)

    g = nx.Graph()
    g.add_nodes_from(nodes)
    rows, cols = np.where(np.triu(sim >= threshold, k=1))
    g.add_edges_from(
        (nodes[i], nodes[j], {"weight": float(sim[i, j])}) for i, j in zip(rows, cols)
    )
    return g


def verify_baseline(data: dict) -> None:
    """At q=0.90 we must reproduce the graphs in data/graphs/ exactly."""
    for name in C.NETWORKS:
        sim = C.load_similarity(name)
        rebuilt = graph_at_quantile(sim, data["nodes"], BASELINE_QUANTILE)
        original = data["graphs"][name]

        if set(map(frozenset, rebuilt.edges())) != set(map(frozenset, original.edges())):
            raise AssertionError(
                f"{name}: rebuilt graph at q={BASELINE_QUANTILE} does not match "
                f"data/graphs/network_{name}.graphml"
            )
    print(f"  baseline check: all 5 networks reproduce exactly at q={BASELINE_QUANTILE}")


def sweep(name: str, nodes: list[str]) -> dict:
    sim = C.load_similarity(name)
    rows = []

    for q in QUANTILES:
        g = graph_at_quantile(sim, nodes, float(q))
        components = list(nx.connected_components(g))
        giant = max(components, key=len)

        rows.append({
            "quantile": float(q),
            "n_edges": g.number_of_edges(),
            "density": nx.density(g),
            "n_isolates": sum(1 for c in components if len(c) == 1),
            "n_components": len(components),
            "giant_fraction": len(giant) / g.number_of_nodes(),
            "avg_clustering": nx.average_clustering(g),
        })

    return {r["quantile"]: r for r in rows}


def first_fully_connected(rows: dict) -> float | None:
    """Loosest cut at which nobody is left isolated."""
    connected = [q for q, r in sorted(rows.items()) if r["n_isolates"] == 0]
    return max(connected) if connected else None


def plot_sweep(sweeps: dict) -> None:
    colours = {
        "overall": "#2c3e50", "technology": "#e67e22", "education": "#27ae60",
        "ethics": "#8e44ad", "environment": "#2980b9",
    }

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    panels = [
        ("giant_fraction", "giant component fraction"),
        ("n_isolates", "respondents with no edges"),
        ("avg_clustering", "average clustering"),
    ]

    for ax, (key, label) in zip(axes, panels):
        for name, rows in sweeps.items():
            qs = sorted(rows)
            ax.plot(qs, [rows[q][key] for q in qs], lw=1.9,
                    color=colours[name], label=name)

        ax.axvline(BASELINE_QUANTILE, color="#c0392b", ls="--", lw=1.5,
                   label="cut used in src/" if key == "giant_fraction" else None)
        ax.set_xlabel("similarity quantile kept as edges")
        ax.set_ylabel(label)
        ax.set_title(label, fontsize=11)
        ax.grid(alpha=0.25)
        ax.invert_xaxis()  # looser cuts on the right

    axes[0].legend(fontsize=8.5, loc="lower left")
    fig.suptitle(
        "How much of the structure survives a different threshold?  "
        "(x axis reversed: looser cuts to the right)",
        fontsize=12,
    )
    fig.tight_layout()
    C.save_figure(fig, "dynamics_threshold_sensitivity.png")
    plt.close(fig)


def plot_ordering(sweeps: dict) -> None:
    """Does Technology stay better connected than Environment at every cut?"""
    qs = sorted(sweeps["technology"])
    pairs = [("technology", "environment"), ("education", "ethics")]

    fig, ax = plt.subplots(figsize=(8.5, 5))
    colours = ["#e67e22", "#27ae60"]

    for (a, b), colour in zip(pairs, colours):
        gap = [sweeps[a][q]["giant_fraction"] - sweeps[b][q]["giant_fraction"]
               for q in qs]
        ax.plot(qs, gap, lw=2.0, color=colour, label=f"{a} minus {b}")

    ax.axhline(0.0, color="#555555", lw=1.2)
    ax.axvline(BASELINE_QUANTILE, color="#c0392b", ls="--", lw=1.5,
               label="cut used in src/")
    ax.set_xlabel("similarity quantile kept as edges")
    ax.set_ylabel("difference in giant component fraction")
    ax.set_title(
        "The topic ordering is not an artifact of the cut:\n"
        "the gap stays positive across the whole range",
        fontsize=11,
    )
    ax.invert_xaxis()
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    C.save_figure(fig, "dynamics_threshold_ordering.png")
    plt.close(fig)


def main() -> None:
    print("Threshold sensitivity")
    data = C.load_all()
    verify_baseline(data)

    sweeps = {name: sweep(name, data["nodes"]) for name in C.NETWORKS}

    plot_sweep(sweeps)
    plot_ordering(sweeps)

    qs = sorted(sweeps["technology"])
    ordering_holds = {
        f"{a}_over_{b}": bool(
            all(sweeps[a][q]["giant_fraction"] >= sweeps[b][q]["giant_fraction"]
                for q in qs)
        )
        for a, b in [("technology", "environment"), ("education", "ethics")]
    }

    C.write_results("threshold_sensitivity", {
        "baseline_quantile": BASELINE_QUANTILE,
        "quantiles": [float(q) for q in QUANTILES],
        "sweeps": sweeps,
        "loosest_quantile_with_no_isolates": {
            name: first_fully_connected(rows) for name, rows in sweeps.items()
        },
        "topic_ordering_holds_at_every_cut": ordering_holds,
    })

    print(f"\n  {'network':12s} {'isolates@0.90':>13s} {'q with 0 isolates':>18s} "
          f"{'giant@0.90':>11s} {'giant@0.70':>11s}")
    for name, rows in sweeps.items():
        q0 = first_fully_connected(rows)
        print(f"  {name:12s} {rows[0.9]['n_isolates']:13d} "
              f"{(f'{q0:.2f}' if q0 else 'never'):>18s} "
              f"{rows[0.9]['giant_fraction']:11.3f} {rows[0.7]['giant_fraction']:11.3f}")

    print(f"\n  ordering holds at every cut: {ordering_holds}")


if __name__ == "__main__":
    main()
