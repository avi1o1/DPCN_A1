"""
Null models for the opinion network.

Three nulls, each destroying less than the last. Erdos-Renyi keeps only the node
count and density, and gives the analytic course predictions C = p,
L = ln(N)/ln(<k>) and S solving S = 1 - exp(-<k>S). The configuration model
keeps every degree exactly and randomizes only the wiring, so the 36 isolated
respondents stay isolated and any remaining gap is real structure. A label
permutation keeps the network and the community sizes and destroys only the
link between community membership and opinion.

Modularity here uses networkx's Louvain for both real and null graphs, so it
will not match `data/metrics.json` exactly. Only the real-versus-null
comparison within this file is meaningful.

Writes `data/dynamics_metrics.json["nullmodels"]` and two figures.
"""

from __future__ import annotations

import numpy as np
import networkx as nx
from networkx.algorithms.community import louvain_communities, modularity
import matplotlib.pyplot as plt
from scipy.optimize import brentq

import common as C

N_NULL = 500
N_PERMUTATIONS = 10000
MIN_COMMUNITY = 3  # smaller than this is an isolate, not a group


def graph_stats(g: nx.Graph, seed: int = C.SEED) -> dict:
    giant_nodes = max(nx.connected_components(g), key=len)
    giant = g.subgraph(giant_nodes)

    # sorted for the same reason as in degroot.predicted_consensus: louvain
    # returns sets, and their iteration order shifts the last bit of modularity
    communities = [sorted(c) for c in louvain_communities(g, seed=seed)]

    return {
        "avg_clustering": nx.average_clustering(g),
        "giant_fraction": len(giant_nodes) / g.number_of_nodes(),
        "avg_path_length": (
            nx.average_shortest_path_length(giant) if len(giant_nodes) > 1 else 0.0
        ),
        "modularity": modularity(g, communities),
    }


STAT_KEYS = ["avg_clustering", "giant_fraction", "avg_path_length", "modularity"]
STAT_LABELS = {
    "avg_clustering": "average clustering",
    "giant_fraction": "giant component fraction",
    "avg_path_length": "average path length (giant)",
    "modularity": "modularity",
}


def er_prediction(n: int, p: float) -> dict:
    """Analytic G(N, p) values for the same N and density."""
    k_mean = p * (n - 1)

    # S = 0 is always a root of S = 1 - exp(-<k>S), so look just above zero
    def f(s):
        return s - (1.0 - np.exp(-k_mean * s))

    giant = brentq(f, 1e-9, 1.0) if k_mean > 1.0 else 0.0

    return {
        "k_mean": k_mean,
        "avg_clustering": p,
        "avg_path_length": np.log(n) / np.log(k_mean),
        "giant_fraction": giant,
    }


def er_ensemble(n: int, p: float, rng: np.random.Generator) -> list[dict]:
    return [
        graph_stats(nx.gnp_random_graph(n, p, seed=int(rng.integers(1 << 31))))
        for _ in range(N_NULL)
    ]


def configuration_ensemble(g: nx.Graph, rng: np.random.Generator) -> list[dict]:
    """Degree-preserving rewiring, ~10 double edge swaps per edge."""
    stats = []
    n_swaps = 10 * g.number_of_edges()

    for _ in range(N_NULL):
        h = g.copy()
        try:
            nx.double_edge_swap(h, nswap=n_swaps, max_tries=n_swaps * 20,
                                seed=int(rng.integers(1 << 31)))
        except nx.NetworkXAlgorithmError:
            pass  # too constrained to swap further, keep what we got
        stats.append(graph_stats(h))

    return stats


def summarise(real: dict, ensemble: list[dict]) -> dict:
    """Mean, sd and z-score of the real value against the null ensemble."""
    out = {}
    for key in STAT_KEYS:
        values = np.array([s[key] for s in ensemble])
        mean, sd = float(values.mean()), float(values.std())
        out[key] = {
            "real": real[key],
            "null_mean": mean,
            "null_sd": sd,
            "z_score": float((real[key] - mean) / sd) if sd > 1e-12 else None,
            "p_two_sided": float(
                (np.abs(values - mean) >= abs(real[key] - mean)).mean()
            ),
        }
    return out


def permutation_test(partition: dict, features, rng) -> dict:
    """Are Louvain's communities more opinion-homogeneous than chance?

    Statistic is the mean within-community variance of `features`. Labels are
    shuffled with the community sizes held fixed. Run once on all 60 question
    scores, which is what the graph was built from, and once on the four topic
    means, which is a much coarser summary.
    """
    sizes = {}
    for node, comm in partition.items():
        sizes[comm] = sizes.get(comm, 0) + 1

    real_communities = [c for c, size in sizes.items() if size >= MIN_COMMUNITY]
    members = [n for n, c in partition.items() if c in real_communities]
    labels = np.array([partition[n] for n in members])

    X = features.loc[members].to_numpy(dtype=float)

    def within_variance(lab: np.ndarray) -> float:
        return float(
            np.mean([X[lab == c].var(axis=0, ddof=0).mean() for c in real_communities])
        )

    observed = within_variance(labels)

    null = np.empty(N_PERMUTATIONS)
    shuffled = labels.copy()
    for i in range(N_PERMUTATIONS):
        rng.shuffle(shuffled)
        null[i] = within_variance(shuffled)

    p_value = float((null <= observed).mean())

    return {
        "n_features": X.shape[1],
        "n_communities_tested": len(real_communities),
        "community_sizes": {str(c): sizes[c] for c in real_communities},
        "n_respondents": len(members),
        "observed_within_variance": observed,
        "null_mean": float(null.mean()),
        "null_sd": float(null.std()),
        "z_score": float((observed - null.mean()) / null.std()),
        "p_value_one_sided": p_value,
        "significant_at_05": p_value < 0.05,
        "n_permutations": N_PERMUTATIONS,
        "_null_draws": null.tolist(),
    }


def plot_nulls(real: dict, er: list[dict], config: list[dict], pred: dict) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))

    for ax, key in zip(axes.ravel(), STAT_KEYS):
        er_vals = [s[key] for s in er]
        cfg_vals = [s[key] for s in config]

        ax.hist(er_vals, bins=30, alpha=0.65, color="#95a5a6", label="Erdos-Renyi")
        ax.hist(cfg_vals, bins=30, alpha=0.65, color="#5dade2",
                label="configuration model")
        ax.axvline(real[key], color="#c0392b", lw=2.2,
                   label=f"real = {real[key]:.3f}")
        if key in pred:
            ax.axvline(pred[key], color="#27ae60", ls="--", lw=1.8,
                       label=f"ER theory = {pred[key]:.3f}")

        ax.set_title(STAT_LABELS[key], fontsize=11)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.22)

    fig.suptitle(
        "The opinion network against two nulls: ER destroys the degrees, "
        "the configuration model keeps them",
        fontsize=12,
    )
    fig.tight_layout()
    C.save_figure(fig, "dynamics_nullmodels.png")
    plt.close(fig)


def plot_permutation(results: dict) -> None:
    fig, axes = plt.subplots(1, len(results), figsize=(6.5 * len(results), 5))
    axes = np.atleast_1d(axes)

    for ax, (label, result) in zip(axes, results.items()):
        null = np.array(result["_null_draws"])
        observed = result["observed_within_variance"]
        p = result["p_value_one_sided"]

        ax.hist(null, bins=60, color="#95a5a6", alpha=0.8,
                label=f"{result['n_permutations']:,} shuffled assignments")
        ax.axvline(observed, color="#c0392b", lw=2.4,
                   label=f"real partition = {observed:.4f}")

        verdict = "more homogeneous than chance" if p < 0.05 else "no better than chance"
        ax.set_xlabel("mean within-community variance")
        ax.set_ylabel("count")
        ax.set_title(
            f"{label}  ({result['n_features']} features)\n"
            f"{verdict}:  p = {p:.4f},  z = {result['z_score']:.2f}",
            fontsize=11,
        )
        ax.legend(fontsize=8)
        ax.grid(alpha=0.22)

    fig.suptitle(
        f"Do Louvain's {list(results.values())[0]['n_communities_tested']} communities "
        f"group people who actually agree?",
        fontsize=12,
    )
    fig.tight_layout()
    C.save_figure(fig, "dynamics_community_permutation.png")
    plt.close(fig)


def main() -> None:
    print("Parts C and D: null models")
    data = C.load_all()
    rng = np.random.default_rng(C.SEED)

    g = data["graphs"]["overall"]
    n = g.number_of_nodes()
    p = nx.density(g)

    real = graph_stats(g)
    pred = er_prediction(n, p)

    print(f"  building {N_NULL} ER graphs ...")
    er = er_ensemble(n, p, rng)
    print(f"  building {N_NULL} degree-preserving rewirings ...")
    config = configuration_ensemble(g, rng)

    plot_nulls(real, er, config, pred)

    print(f"  running {N_PERMUTATIONS:,} community label permutations ...")
    partition = data["metrics"]["overall"]["community"]["partition"]

    topic_means = C.topic_means(data["scores"], data["meta"])
    perms = {
        "all 60 question scores": permutation_test(
            partition, data["scores"].fillna(0.0), rng
        ),
        "4 topic means": permutation_test(
            partition, topic_means[[t.lower() for t in C.TOPICS]], rng
        ),
    }
    plot_permutation(perms)

    for result in perms.values():
        result.pop("_null_draws")  # too large to serialise

    C.write_results("nullmodels", {
        "n_null_graphs": N_NULL,
        "graph": {"n_nodes": n, "density": p, "k_mean": pred["k_mean"]},
        "real": real,
        "er_theory": pred,
        "vs_erdos_renyi": summarise(real, er),
        "vs_configuration_model": summarise(real, config),
        "community_permutation": perms,
    })

    print(f"\n  {'statistic':28s} {'real':>8s} {'ER':>8s} {'z':>8s} "
          f"{'config':>8s} {'z':>8s}")
    er_s, cfg_s = summarise(real, er), summarise(real, config)
    for key in STAT_KEYS:
        e, c = er_s[key], cfg_s[key]
        ez = f"{e['z_score']:8.1f}" if e["z_score"] is not None else f"{'n/a':>8s}"
        cz = f"{c['z_score']:8.1f}" if c["z_score"] is not None else f"{'n/a':>8s}"
        print(f"  {STAT_LABELS[key]:28s} {e['real']:8.3f} {e['null_mean']:8.3f} "
              f"{ez} {c['null_mean']:8.3f} {cz}")

    print()
    for label, result in perms.items():
        print(f"  permutation [{label:22s}] observed={result['observed_within_variance']:.4f} "
              f"null={result['null_mean']:.4f} z={result['z_score']:6.2f} "
              f"p={result['p_value_one_sided']:.4f} "
              f"{'SIGNIFICANT' if result['significant_at_05'] else 'not significant'}")


if __name__ == "__main__":
    main()
