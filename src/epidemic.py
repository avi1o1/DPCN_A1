"""
SIS epidemic threshold on the opinion network.

Treats "holds a strong opinion" as an infection that spreads along similarity
edges. The quenched mean-field threshold is (beta/gamma)_c = 1/lambda_max, and
the heterogeneous mean-field one is <k>/<k^2>, which sees only the degrees.

All five networks have the same 87 nodes and 375 edges, because the top-10%
edge rule fixes the count regardless of the similarity distribution. Any
difference in lambda_max is therefore pure wiring, which makes this a
controlled comparison. A discrete-time SIS sweep checks where the transition
actually lands.

Writes `data/dynamics_metrics.json["epidemic"]` and two figures.
"""

from __future__ import annotations

import numpy as np
import networkx as nx
import matplotlib.pyplot as plt

import common as C

N_RUNS = 40
N_STEPS = 400
BURN_IN = 300
GAMMA = 0.2
SEED_FRACTION = 0.10
N_SWEEP = 26
ENDEMIC_CUTOFF = 0.02


def spectral_thresholds(g: nx.Graph, nodes: list[str]) -> dict:
    """Epidemic threshold from the adjacency spectrum and from the degrees."""
    A = C.adjacency(g, nodes)
    eigenvalues = np.linalg.eigvalsh(A)
    lambda_max = float(eigenvalues[-1])

    k = A.sum(axis=1)
    k_mean = float(k.mean())
    k2_mean = float((k ** 2).mean())

    return {
        "lambda_max": lambda_max,
        "threshold_qmf": 1.0 / lambda_max,
        "threshold_hmf": k_mean / k2_mean,
        "k_mean": k_mean,
        "k2_mean": k2_mean,
        "heterogeneity_ratio": k2_mean / k_mean ** 2,
        "n_edges": int(A.sum() // 2),
    }


def simulate_sis(
    A: np.ndarray,
    beta: float,
    gamma: float,
    rng: np.random.Generator,
    n_runs: int = N_RUNS,
    n_steps: int = N_STEPS,
    burn_in: int = BURN_IN,
    seed_fraction: float = SEED_FRACTION,
) -> float:
    """Mean steady-state infected fraction over the nodes in the passed matrix.

    Each step an infected node recovers with probability gamma, and a
    susceptible node with m infected neighbours is infected with probability
    1 - (1 - beta)^m.
    """
    n = A.shape[0]
    n_seed = max(1, int(round(seed_fraction * n)))
    prevalence = []

    for _ in range(n_runs):
        infected = np.zeros(n, dtype=bool)
        infected[rng.choice(n, size=n_seed, replace=False)] = True

        tail = []
        for t in range(n_steps):
            if not infected.any():
                break  # absorbing state

            n_infected_neighbours = A @ infected.astype(float)
            infect_prob = 1.0 - (1.0 - beta) ** n_infected_neighbours

            newly_infected = (~infected) & (rng.random(n) < infect_prob)
            recovered = infected & (rng.random(n) < gamma)

            infected = (infected & ~recovered) | newly_infected

            if t >= burn_in:
                tail.append(infected.mean())

        prevalence.append(np.mean(tail) if tail else 0.0)

    return float(np.mean(prevalence))


def sweep(g: nx.Graph, nodes: list[str], threshold: float, rng) -> dict:
    """Steady-state prevalence across beta/gamma, on the giant component."""
    giant_nodes = max(nx.connected_components(g), key=len)
    order = [n for n in nodes if n in giant_nodes]
    A = C.adjacency(g.subgraph(giant_nodes), order)

    ratios = np.linspace(0.2, 4.0, N_SWEEP) * threshold
    prevalence = [
        simulate_sis(A, beta=r * GAMMA, gamma=GAMMA, rng=rng) for r in ratios
    ]

    took_hold = [r / threshold for r, p in zip(ratios, prevalence) if p > ENDEMIC_CUTOFF]
    measured = float(took_hold[0]) if took_hold else None

    return {
        "giant_size": len(giant_nodes),
        "ratios": ratios.tolist(),
        "prevalence": prevalence,
        "gamma": GAMMA,
        "endemic_cutoff": ENDEMIC_CUTOFF,
        "measured_threshold_over_predicted": measured,
    }


def plot_thresholds(spectra: dict) -> None:
    names = C.NETWORKS
    lam = [spectra[n]["lambda_max"] for n in names]
    qmf = [spectra[n]["threshold_qmf"] for n in names]
    hmf = [spectra[n]["threshold_hmf"] for n in names]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    bars = axes[0].bar(names, lam, color="#8e44ad")
    for bar, v in zip(bars, lam):
        axes[0].text(bar.get_x() + bar.get_width() / 2, v + 0.15, f"{v:.2f}",
                     ha="center", fontsize=9)
    axes[0].set_ylabel(r"$\lambda_{max}$ of the adjacency matrix")
    axes[0].set_title(
        "Same 87 nodes and 375 edges in every network,\nso this is wiring alone",
        fontsize=11,
    )
    axes[0].tick_params(axis="x", rotation=20)
    axes[0].grid(alpha=0.25, axis="y")

    width = 0.38
    pos = np.arange(len(names))
    axes[1].bar(pos - width / 2, qmf, width, label=r"$1/\lambda_{max}$  (wiring)",
                color="#8e44ad")
    axes[1].bar(pos + width / 2, hmf, width, label=r"$\langle k\rangle/\langle k^2\rangle$  (degrees only)",
                color="#d2b4de")
    axes[1].set_xticks(pos)
    axes[1].set_xticklabels(names, rotation=20)
    axes[1].set_ylabel(r"epidemic threshold  $(\beta/\gamma)_c$")
    axes[1].set_title("Lower threshold means an opinion spreads more easily", fontsize=11)
    axes[1].legend(fontsize=9)
    axes[1].grid(alpha=0.25, axis="y")

    fig.tight_layout()
    C.save_figure(fig, "dynamics_sis_threshold.png")
    plt.close(fig)


def plot_sweep(sweeps: dict, spectra: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    colours = {"overall": "#2980b9", "technology": "#e67e22"}

    for name, colour in colours.items():
        s = sweeps[name]
        thr = spectra[name]["threshold_qmf"]
        x = np.array(s["ratios"]) / thr
        ax.plot(x, s["prevalence"], "o-", color=colour, ms=4.5, lw=1.6,
                label=f"{name}  (giant = {s['giant_size']} nodes)")

    ax.axvline(1.0, color="#c0392b", ls="--", lw=1.6,
               label=r"predicted threshold $\beta/\gamma = 1/\lambda_{max}$")
    ax.set_xlabel(r"$(\beta/\gamma)\ /\ (\beta/\gamma)_c$")
    ax.set_ylabel("steady-state infected fraction of the giant component")
    ax.set_title(
        "SIS on the opinion network: a sharp transition, sitting above the\n"
        r"mean-field bound $1/\lambda_{max}$ as finite-size theory expects",
        fontsize=12,
    )
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    C.save_figure(fig, "dynamics_sis_sweep.png")
    plt.close(fig)


def main() -> None:
    print("Part B: SIS epidemic threshold")
    data = C.load_all()
    rng = np.random.default_rng(C.SEED)

    spectra = {
        name: spectral_thresholds(data["graphs"][name], data["nodes"])
        for name in C.NETWORKS
    }

    sweeps = {
        name: sweep(data["graphs"][name], data["nodes"],
                    spectra[name]["threshold_qmf"], rng)
        for name in ["overall", "technology"]
    }

    plot_thresholds(spectra)
    plot_sweep(sweeps, spectra)

    C.write_results("epidemic", {
        "settings": {
            "n_runs": N_RUNS, "n_steps": N_STEPS, "burn_in": BURN_IN,
            "gamma": GAMMA, "seed_fraction": SEED_FRACTION,
        },
        "spectral": spectra,
        "sweeps": sweeps,
    })

    for name, sw in sweeps.items():
        m = sw["measured_threshold_over_predicted"]
        print(f"  {name:12s} simulated transition at {m:.2f}x the 1/lambda_max bound")

    for name in C.NETWORKS:
        s = spectra[name]
        print(
            f"  {name:12s} lambda_max={s['lambda_max']:6.3f} "
            f"1/lambda_max={s['threshold_qmf']:.4f} "
            f"<k>/<k2>={s['threshold_hmf']:.4f} "
            f"<k>={s['k_mean']:.2f} het={s['heterogeneity_ratio']:.3f}"
        )


if __name__ == "__main__":
    main()
