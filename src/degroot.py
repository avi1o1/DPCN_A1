"""
DeGroot opinion dynamics on the similarity network.

Each respondent starts at their real mean score and repeatedly replaces it with
the average of their neighbours, x(t+1) = D^-1 A x(t). The update matrix is
row-stochastic, so the disagreement decays like its second largest eigenvalue
modulus and the map converges only while that modulus is below 1. Reports the
per-component consensus, the isolated respondents who never move, the bipartite
components that oscillate for ever, and convergence speed against the algebraic
connectivity of the normalized Laplacian.

Writes `data/dynamics_metrics.json["degroot"]` and three figures.
"""

from __future__ import annotations

import numpy as np
import networkx as nx
import matplotlib.pyplot as plt

import common as C

# Education's giant component has mu_2 = 0.736, so it needs ~67 steps to reach
# TOL and roughly twice that on the lazy map, which halves the spectral gap.
N_STEPS = 300
TOL = 1e-9
LAZY_ALPHA = 0.5


def stochastic_matrix(A: np.ndarray, alpha: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Row-normalized adjacency. Isolated nodes get an identity row and stay put.

    `alpha` is the laziness: 1.0 is the plain map, 0.5 damps bipartite oscillation.
    """
    degrees = A.sum(axis=1)
    isolated = degrees == 0

    P = np.zeros_like(A)
    safe = ~isolated
    P[safe] = A[safe] / degrees[safe, None]
    P[isolated, np.where(isolated)[0]] = 1.0

    if alpha != 1.0:
        P = (1.0 - alpha) * np.eye(A.shape[0]) + alpha * P

    return P, isolated


def simulate(P: np.ndarray, x0: np.ndarray, steps: int = N_STEPS) -> np.ndarray:
    traj = np.empty((steps + 1, x0.size))
    traj[0] = x0
    for t in range(steps):
        traj[t + 1] = P @ traj[t]
    return traj


def predicted_consensus(
    g: nx.Graph, nodes: list[str], x0: np.ndarray, A: np.ndarray
) -> np.ndarray:
    """Closed-form fixed point per component: the degree-weighted average.

    Degrees come from `A` rather than `g.degree()` so the weighted run is checked
    against weighted degrees.
    """
    index = {node: i for i, node in enumerate(nodes)}
    degrees = A.sum(axis=1)

    target = x0.copy()
    for component in nx.connected_components(g):
        # sorted, because connected_components yields sets and Python randomizes
        # string hashing per process. An unsorted order changes the summation
        # order below and moves the last bit of the result between runs.
        idx = sorted(index[n] for n in component)
        k = degrees[idx]
        if k.sum() == 0:
            continue
        target[idx] = float(k @ x0[idx] / k.sum())
    return target


def component_report(g: nx.Graph) -> dict:
    comps = sorted(nx.connected_components(g), key=len, reverse=True)
    nontrivial = [c for c in comps if len(c) > 1]
    bipartite = [len(c) for c in nontrivial if nx.is_bipartite(g.subgraph(c))]

    return {
        "component_sizes": [len(c) for c in nontrivial],
        "n_isolated": sum(1 for c in comps if len(c) == 1),
        "bipartite_component_sizes": bipartite,
        "n_oscillating_nodes": int(sum(bipartite)),
    }


def spectral_summary(g: nx.Graph, nodes: list[str], alpha: float = 1.0) -> dict:
    """Spectral gap and algebraic connectivity of the largest component.

    Uses the symmetric S = D^-1/2 A D^-1/2, which shares eigenvalues with
    D^-1 A but keeps them real. The normalized Laplacian is I - S.
    """
    giant_nodes = max(nx.connected_components(g), key=len)
    giant = g.subgraph(giant_nodes)
    order = [n for n in nodes if n in giant_nodes]

    A = C.adjacency(giant, order)
    d = A.sum(axis=1)
    d_inv_sqrt = 1.0 / np.sqrt(d)
    S = A * d_inv_sqrt[:, None] * d_inv_sqrt[None, :]

    mu = np.sort(np.linalg.eigvalsh(S))[::-1]
    if alpha != 1.0:
        mu = (1.0 - alpha) + alpha * mu

    mu_2, mu_min = float(mu[1]), float(mu[-1])
    slem = max(abs(mu_2), abs(mu_min))

    return {
        "giant_size": len(giant_nodes),
        "mu_2": mu_2,
        "mu_min": mu_min,
        "slem": slem,
        "algebraic_connectivity_normalized": 1.0 - mu_2,
        "spectral_gap": 1.0 - slem,
        "giant_is_bipartite": nx.is_bipartite(giant),
        "predicted_halflife": float(np.log(0.5) / np.log(slem)) if 0 < slem < 1 else None,
    }


def convergence_time(traj: np.ndarray, target: np.ndarray, idx=None, tol: float = TOL) -> int:
    """First step where every tracked opinion is within tol of its limit, else -1."""
    sl = slice(None) if idx is None else idx
    err = np.abs(traj[:, sl] - target[sl]).max(axis=1)
    hits = np.where(err < tol)[0]
    return int(hits[0]) if hits.size else -1


def run_network(name: str, data: dict, weighted: bool = False) -> dict:
    g = data["graphs"][name]
    nodes = data["nodes"]

    A = C.adjacency(g, nodes, weighted=weighted)
    x0 = C.initial_opinions(data["scores"], data["meta"], topic="overall")
    target = predicted_consensus(g, nodes, x0, A)

    P, isolated = stochastic_matrix(A)
    P_lazy, _ = stochastic_matrix(A, alpha=LAZY_ALPHA)

    traj = simulate(P, x0)
    traj_lazy = simulate(P_lazy, x0)

    giant_nodes = max(nx.connected_components(g), key=len)
    giant_idx = [i for i, n in enumerate(nodes) if n in giant_nodes]

    comps = component_report(g)
    spec = spectral_summary(g, nodes)
    spec_lazy = spectral_summary(g, nodes, alpha=LAZY_ALPHA)

    summary = {
        "weighted": weighted,
        "n_components": nx.number_connected_components(g),
        "n_moving": int((~isolated).sum()),
        **comps,
        "consensus_giant": float(target[giant_idx][0]),
        "x0_mean": float(x0.mean()),
        "x0_mean_giant": float(x0[giant_idx].mean()),
        "x0_mean_isolated": float(x0[isolated].mean()) if isolated.any() else None,
        "spread_initial": float(x0.max() - x0.min()),
        "spread_final_giant": float(traj[-1][giant_idx].max() - traj[-1][giant_idx].min()),
        "steps_to_converge_giant": convergence_time(traj, target, giant_idx),
        "steps_to_converge_all": convergence_time(traj, target),
        "giant_matches_closed_form": bool(
            np.abs(traj[-1][giant_idx] - target[giant_idx]).max() < 1e-6
        ),
        "steps_to_converge_all_lazy": convergence_time(traj_lazy, target),
        "lazy_matches_closed_form": bool(np.abs(traj_lazy[-1] - target).max() < 1e-6),
        "slem_lazy": spec_lazy["slem"],
        **spec,
    }
    return summary, traj, traj_lazy, target, isolated


def plot_trajectories(results: dict) -> None:
    names = ["overall", "technology"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)

    for ax, name in zip(axes, names):
        summary, traj, _, _, isolated = results[name]
        steps = np.arange(traj.shape[0])

        osc = summary["n_oscillating_nodes"]
        # nodes still moving at the end are the ones stuck oscillating
        swinging = np.abs(traj[-1] - traj[-2]) > 1e-6

        for i in range(traj.shape[1]):
            if isolated[i]:
                ax.plot(steps, traj[:, i], color="#c0392b", lw=0.8, alpha=0.4, zorder=1)
            elif swinging[i]:
                ax.plot(steps, traj[:, i], color="#e67e22", lw=1.3, alpha=0.95, zorder=4)
            else:
                ax.plot(steps, traj[:, i], color="#2980b9", lw=0.8, alpha=0.55, zorder=2)

        ax.axhline(
            summary["consensus_giant"], color="#154360", ls="--", lw=1.6, zorder=3,
            label=f"giant consensus = {summary['consensus_giant']:.3f}",
        )
        ax.plot([], [], color="#2980b9", lw=1.5,
                label=f"converges ({summary['n_moving'] - osc})")
        ax.plot([], [], color="#c0392b", lw=1.5,
                label=f"isolated, never moves ({summary['n_isolated']})")
        if osc:
            ax.plot([], [], color="#e67e22", lw=1.5,
                    label=f"bipartite, oscillates forever ({osc})")

        ax.set_title(
            f"{name}   {summary['n_components']} components, "
            f"giant converges in {summary['steps_to_converge_giant']} steps"
        )
        ax.set_xlabel("iteration t")
        ax.set_xlim(0, 45)
        ax.legend(fontsize=8, loc="center right")
        ax.grid(alpha=0.25)

    axes[0].set_ylabel("opinion  x(t)")
    fig.suptitle(
        "DeGroot dynamics: consensus is local, and 40% of the class never joins it",
        fontsize=12,
    )
    fig.tight_layout()
    C.save_figure(fig, "dynamics_degroot_trajectories.png")
    plt.close(fig)


def plot_bipartite_fix(results: dict, nodes: list[str]) -> None:
    """The 3-node bipartite component in `technology`, plain map vs lazy map."""
    summary, traj, traj_lazy, target, isolated = results["technology"]
    swinging = np.where(np.abs(traj[-1] - traj[-2]) > 1e-6)[0]
    steps = np.arange(traj.shape[0])

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), sharey=True)

    for ax, data_, title in [
        (axes[0], traj, r"plain map,  $\mu_{min} = -1$"),
        (axes[1], traj_lazy, r"lazy map $a=1/2$,  $\mu_{min} = 0$"),
    ]:
        for i in swinging:
            ax.plot(steps, data_[:, i], lw=1.6, marker="o", ms=2.5,
                    label=f"respondent {nodes[i]}")
        ax.axhline(target[swinging[0]], color="#154360", ls="--", lw=1.5,
                   label=f"degree-weighted limit = {target[swinging[0]]:.3f}")
        ax.set_title(title)
        ax.set_xlabel("iteration t")
        ax.set_xlim(0, 20)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)

    axes[0].set_ylabel("opinion  x(t)")
    fig.suptitle(
        "A bipartite component never converges under the plain averaging map "
        f"(technology, {len(swinging)} respondents)",
        fontsize=12,
    )
    fig.tight_layout()
    C.save_figure(fig, "dynamics_degroot_bipartite.png")
    plt.close(fig)


def plot_convergence(results: dict) -> None:
    names = C.NETWORKS
    lam2 = [results[n][0]["algebraic_connectivity_normalized"] for n in names]
    steps = [results[n][0]["steps_to_converge_giant"] for n in names]
    slem = [results[n][0]["slem"] for n in names]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    axes[0].scatter(lam2, steps, s=90, color="#2980b9", zorder=3)
    for n, x, y in zip(names, lam2, steps):
        axes[0].annotate(n, (x, y), textcoords="offset points", xytext=(7, 5), fontsize=9)
    axes[0].set_xlabel(r"algebraic connectivity  $\lambda_2 = 1 - \mu_2$")
    axes[0].set_ylabel("iterations for giant component to converge")
    axes[0].set_title("Better connected components reach consensus faster")
    axes[0].grid(alpha=0.25)

    bars = axes[1].bar(names, slem, color="#5499c7")
    axes[1].axhline(1.0, color="#c0392b", ls="--", lw=1.4,
                    label=r"stability limit $|\mu| = 1$")
    for bar, v in zip(bars, slem):
        axes[1].text(bar.get_x() + bar.get_width() / 2, v + 0.012, f"{v:.3f}",
                     ha="center", fontsize=9)
    axes[1].set_ylim(0, 1.12)
    axes[1].set_ylabel("SLEM of $P = D^{-1}A$ on the giant component")
    axes[1].set_title("All five giant components are stable maps (SLEM < 1)")
    axes[1].tick_params(axis="x", rotation=20)
    axes[1].legend(fontsize=9)
    axes[1].grid(alpha=0.25, axis="y")

    fig.tight_layout()
    C.save_figure(fig, "dynamics_degroot_convergence.png")
    plt.close(fig)


def main() -> None:
    print("Part A: DeGroot dynamics")
    data = C.load_all()

    results = {name: run_network(name, data) for name in C.NETWORKS}
    weighted = {name: run_network(name, data, weighted=True)[0] for name in C.NETWORKS}

    plot_trajectories(results)
    plot_bipartite_fix(results, data["nodes"])
    plot_convergence(results)

    C.write_results("degroot", {
        "n_steps": N_STEPS,
        "tolerance": TOL,
        "lazy_alpha": LAZY_ALPHA,
        "unweighted": {name: results[name][0] for name in C.NETWORKS},
        "weighted": weighted,
    })

    for name in C.NETWORKS:
        r = results[name][0]
        print(
            f"  {name:12s} comps={r['n_components']:3d} iso={r['n_isolated']:3d} "
            f"osc={r['n_oscillating_nodes']:2d} consensus={r['consensus_giant']:.4f} "
            f"giant_steps={r['steps_to_converge_giant']:3d} "
            f"lazy_all={r['steps_to_converge_all_lazy']:3d} "
            f"lam2={r['algebraic_connectivity_normalized']:.4f} "
            f"ok={r['giant_matches_closed_form'] and r['lazy_matches_closed_form']}"
        )


if __name__ == "__main__":
    main()
