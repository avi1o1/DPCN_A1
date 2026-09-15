"""
Independent checks of every mathematical claim in this folder.

Nothing here reads `data/dynamics_metrics.json`. Each check recomputes a
quantity a different way from the scripts that produced it, then compares. A
claim that only agrees with itself is not checked, so where networkx has its own
implementation we compare against that instead.

Note that networkx defaults to weight="weight" while this analysis uses the
unweighted matrix throughout, so the comparisons below pass weight=None. That
difference is the reason two of these checks failed the first time they were
written, and it was the test that was wrong, not the analysis.

Run `python verify.py`. Exit code is 0 when every check passes.
"""

from __future__ import annotations

import os
import subprocess
import sys

import numpy as np
import networkx as nx

import common as C
import degroot as D
import epidemic as E
import nullmodels as N
import sensitivity as S

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    mark = "pass" if condition else "FAIL"
    print(f"  [{mark}] {name}" + (f"   {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{title}")


def main() -> int:
    data = C.load_all()
    nodes = data["nodes"]
    g = data["graphs"]["overall"]
    A = C.adjacency(g, nodes)
    x0 = C.initial_opinions(data["scores"], data["meta"])

    section("1. The averaging map")
    P, isolated = D.stochastic_matrix(A)
    check("P is row-stochastic", np.allclose(P.sum(axis=1), 1.0))
    check("P is non-negative", bool((P >= 0).all()))

    # independent route to the limit: raise P to a high power instead of iterating
    limit_matpow = np.linalg.matrix_power(P, 1000) @ x0
    limit_closed = D.predicted_consensus(g, nodes, x0, A)
    check(
        "closed-form limit == P^1000 @ x0",
        np.abs(limit_matpow - limit_closed).max() < 1e-9,
        f"max diff {np.abs(limit_matpow - limit_closed).max():.2e}",
    )

    check(
        "isolated respondents never move",
        np.allclose(limit_matpow[isolated], x0[isolated]),
        f"{int(isolated.sum())} isolated",
    )

    giant = max(nx.connected_components(g), key=len)
    gi = sorted(i for i, n in enumerate(nodes) if n in giant)
    k = A.sum(axis=1)
    q0 = k[gi] @ x0[gi] / k[gi].sum()
    q5 = k[gi] @ (np.linalg.matrix_power(P, 5) @ x0)[gi] / k[gi].sum()
    check(
        "degree-weighted mean is conserved",
        abs(q0 - q5) < 1e-12,
        f"{q0:.12f} vs {q5:.12f}",
    )

    section("2. Spectral identities")
    sub = g.subgraph(giant)
    order = [n for n in nodes if n in giant]
    Ag = C.adjacency(sub, order)
    d = Ag.sum(axis=1)
    Sm = Ag * (1 / np.sqrt(d))[:, None] * (1 / np.sqrt(d))[None, :]
    mu = np.sort(np.linalg.eigvalsh(Sm))

    eig_P = np.sort(np.linalg.eigvals(Ag / d[:, None]).real)
    check(
        "eig(D^-1 A) == eig(D^-1/2 A D^-1/2)",
        np.abs(mu - eig_P).max() < 1e-9,
    )
    check("largest eigenvalue is exactly 1", abs(mu[-1] - 1) < 1e-10, f"{mu[-1]:.12f}")

    lap = nx.normalized_laplacian_matrix(sub, nodelist=order, weight=None).toarray()
    check(
        "normalized Laplacian eigenvalues == 1 - mu",
        np.abs(np.sort(np.linalg.eigvalsh(lap)) - np.sort(1 - mu)).max() < 1e-9,
    )

    section("3. Bipartite components")
    mismatches = []
    for name in C.NETWORKS:
        gg = data["graphs"][name]
        for comp in nx.connected_components(gg):
            if len(comp) < 2:
                continue
            sg = gg.subgraph(comp)
            o = [n for n in nodes if n in comp]
            Ac = C.adjacency(sg, o)
            dc = Ac.sum(axis=1)
            Sc = Ac * (1 / np.sqrt(dc))[:, None] * (1 / np.sqrt(dc))[None, :]
            mu_min = float(np.linalg.eigvalsh(Sc).min())
            if nx.is_bipartite(sg) != (abs(mu_min + 1) < 1e-9):
                mismatches.append((name, len(comp), mu_min))
    check(
        "bipartite <=> mu_min == -1, every component of all 5 networks",
        not mismatches,
        f"{len(mismatches)} mismatches" if mismatches else "",
    )

    section("4. The lazy map")
    alpha = D.LAZY_ALPHA
    P_lazy, _ = D.stochastic_matrix(A, alpha=alpha)
    S_lazy = alpha * Sm + (1 - alpha) * np.eye(len(Sm))
    check(
        "lazy eigenvalues == (1-a) + a*mu",
        np.abs(np.sort(np.linalg.eigvalsh(S_lazy)) - np.sort((1 - alpha) + alpha * mu)).max() < 1e-10,
    )
    check(
        "lazy map reaches the same fixed point",
        np.abs(np.linalg.matrix_power(P_lazy, 4000) @ x0 - limit_closed).max() < 1e-8,
    )

    section("5. Adjacency spectrum and the SIS threshold")
    for name in ["overall", "environment"]:
        gg = data["graphs"][name]
        mine = E.spectral_thresholds(gg, nodes)["lambda_max"]
        theirs = float(np.sort(nx.adjacency_spectrum(gg, weight=None).real)[-1])
        check(
            f"{name}: lambda_max matches networkx",
            abs(mine - theirs) < 1e-6,
            f"{mine:.6f} vs {theirs:.6f}",
        )

    section("6. Erdos-Renyi predictions")
    n, p = g.number_of_nodes(), nx.density(g)
    pred = N.er_prediction(n, p)
    kbar = pred["k_mean"]
    check(
        "<k> = p(N-1) matches the real average degree",
        abs(kbar - A.sum(axis=1).mean()) < 1e-9,
        f"{kbar:.4f}",
    )
    Sgiant = pred["giant_fraction"]
    residual = abs(Sgiant - (1 - np.exp(-kbar * Sgiant)))
    check(
        "giant fraction solves S = 1 - exp(-<k>S)",
        residual < 1e-9,
        f"S={Sgiant:.6f}, residual {residual:.1e}",
    )
    sim_C = np.mean(
        [nx.average_clustering(nx.gnp_random_graph(n, p, seed=s)) for s in range(200)]
    )
    check(
        "C_ER = p, against 200 simulated graphs",
        abs(sim_C - p) < 0.01,
        f"theory {p:.4f} vs simulated {sim_C:.4f}",
    )

    section("7. Configuration model")
    h = g.copy()
    nx.double_edge_swap(h, nswap=10 * g.number_of_edges(),
                        max_tries=10 ** 7, seed=C.SEED)
    check(
        "degree sequence unchanged after rewiring",
        sorted(dd for _, dd in h.degree()) == sorted(dd for _, dd in g.degree()),
    )
    check("edge count unchanged", h.number_of_edges() == g.number_of_edges())
    check(
        "wiring actually changed",
        set(map(frozenset, h.edges())) != set(map(frozenset, g.edges())),
    )

    section("8. Threshold sweep reproduces the published graphs")
    try:
        S.verify_baseline(data)
        ok = True
    except AssertionError as exc:
        ok, _ = False, print(f"   {exc}")
    check("q=0.90 rebuild matches data/graphs/*.graphml edge for edge", ok)

    section("9. Determinism across processes")
    # connected_components yields sets, and Python randomizes string hashing per
    # process, so the same component can iterate in a different order each run.
    # That moves the last bit of a floating-point sum. predicted_consensus and
    # graph_stats sort to avoid it. Check that by running the same computation
    # in fresh processes under different hash seeds.
    snippet = (
        "import numpy as np, common as C, degroot as D, nullmodels as N;"
        "d=C.load_all(); nodes=d['nodes']; g=d['graphs']['overall'];"
        "A=C.adjacency(g,nodes); x0=C.initial_opinions(d['scores'],d['meta']);"
        "print(repr(float(D.predicted_consensus(g,nodes,x0,A).sum())),"
        "repr(float(N.graph_stats(g)['modularity'])))"
    )
    outputs = set()
    for seed in ("0", "1", "2", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        result = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True, text=True, cwd=str(C.SRC_DIR), env=env,
        )
        outputs.add(result.stdout.strip())
    check(
        "results are bit-identical across 4 different hash seeds",
        len(outputs) == 1,
        f"{len(outputs)} distinct result(s)",
    )

    print(f"\n{'=' * 62}")
    print(f"  {len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"    FAILED: {name}")
    print(f"{'=' * 62}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
