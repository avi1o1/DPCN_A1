"""
Check that every number written in report/VARUN.md matches the code output.

A writeup goes stale the moment a parameter changes and a table does not. This
parses the markdown tables and the quoted figures out of the document and
compares each one against `data/dynamics_metrics.json` and `data/metrics.json`.

Each value is compared at the precision the document actually states, so 0.627
must round correctly from the stored float rather than match it exactly.

The claims at the end are statements the document makes in prose, for example
that the topic ordering holds at every threshold. Those are checked as booleans.

Run `python check_docs.py` after `run_all.py`. Exit code is 0 when the document
agrees with the data.
"""

from __future__ import annotations

import json
import re
import sys

import common as C

BAD: list[str] = []
CHECKED = 0


def eq(label: str, doc, real, tol: float | None = None) -> None:
    """Compare at the precision the document states, unless told otherwise."""
    global CHECKED
    CHECKED += 1
    doc = str(doc).strip()
    if tol is None:
        decimals = len(doc.split(".")[1]) if "." in doc else 0
        tol = 0.5 * 10 ** (-decimals) + 1e-12
    if abs(float(doc) - float(real)) > tol:
        BAD.append(f"{label}: document says {doc}, code says {real}")


def claim(label: str, condition: bool) -> None:
    global CHECKED
    CHECKED += 1
    if not condition:
        BAD.append(f"claim is false: {label}")


def table(md: str, first_header_cell: str) -> list[list[str]]:
    """Rows of the markdown table whose header starts with the given cell."""
    for block in re.findall(r"((?:^\|.*\|\s*$\n)+)", md, re.M):
        lines = [line.strip() for line in block.strip().split("\n")]
        if lines[0].lstrip("| ").startswith(first_header_cell):
            return [[c.strip() for c in line.strip("|").split("|")] for line in lines[2:]]
    raise SystemExit(f"no table starting with '{first_header_cell}' in the document")


def main() -> int:
    results = json.loads(C.RESULTS_JSON.read_text())
    metrics = C.load_metrics()
    md = (C.ROOT / "report" / "VARUN.md").read_text(encoding="utf-8")

    degroot = results["degroot"]["unweighted"]
    spectral = results["epidemic"]["spectral"]
    nulls = results["nullmodels"]
    perms = nulls["community_permutation"]
    sweep = {
        float(q): row
        for q, row in results["threshold_sensitivity"]["sweeps"]["overall"].items()
    }

    for r in table(md, "Network | λ₂"):
        n, d = r[0], degroot[r[0]]
        eq(f"{n} lambda2", r[1], d["algebraic_connectivity_normalized"])
        eq(f"{n} slem", r[2], d["slem"])
        eq(f"{n} steps", r[3], d["steps_to_converge_giant"])
        eq(f"{n} giant size", r[4], d["giant_size"])
        eq(f"{n} consensus", r[5], d["consensus_giant"])

    for r in table(md, "Network | λ_max"):
        n, s = r[0], spectral[r[0]]
        eq(f"{n} lambda_max", r[1], s["lambda_max"])
        eq(f"{n} threshold", r[2], s["threshold_qmf"])
        eq(f"{n} k/k2", r[3], s["threshold_hmf"])
        eq(f"{n} giant size", r[4], degroot[n]["giant_size"])

    stat_key = {
        "Average clustering": "avg_clustering",
        "Giant fraction": "giant_fraction",
        "Average path length": "avg_path_length",
        "Modularity": "modularity",
    }
    for r in table(md, "Statistic | Real"):
        k = stat_key[r[0]]
        sign = lambda v: v.replace("+", "").replace("−", "-")
        eq(f"{k} real", r[1], nulls["real"][k])
        eq(f"{k} er mean", r[2], nulls["vs_erdos_renyi"][k]["null_mean"])
        eq(f"{k} er z", sign(r[3]), nulls["vs_erdos_renyi"][k]["z_score"], 0.06)
        eq(f"{k} config mean", r[4], nulls["vs_configuration_model"][k]["null_mean"])
        eq(f"{k} config z", sign(r[5]), nulls["vs_configuration_model"][k]["z_score"], 0.06)

    for r in table(md, "Features tested"):
        p = perms["all 60 question scores"] if "60" in r[0] else perms["4 topic means"]
        eq(f"permutation {r[0]} observed", r[1], p["observed_within_variance"])
        eq(f"permutation {r[0]} null", r[2], p["null_mean"])
        eq(f"permutation {r[0]} z", r[3].replace("−", "-"), p["z_score"], 0.02)
        if "<" not in r[4]:
            eq(f"permutation {r[0]} p", r[4], p["p_value_one_sided"])

    for r in table(md, "Quantile kept"):
        q = float(r[0])
        eq(f"q={q} edges", r[1], sweep[q]["n_edges"])
        eq(f"q={q} isolated", r[2], sweep[q]["n_isolates"])
        eq(f"q={q} giant", r[3], sweep[q]["giant_fraction"])
        eq(f"q={q} clustering", r[4], sweep[q]["avg_clustering"])

    overall = degroot["overall"]
    for label, doc, real in [
        ("37 components", 37, overall["n_components"]),
        ("36 isolated", 36, overall["n_isolated"]),
        ("51 in the giant", 51, overall["giant_size"]),
        ("consensus 1.409", 1.409, overall["consensus_giant"]),
        ("connected start 1.309", 1.309, overall["x0_mean_giant"]),
        ("isolated start 0.872", 0.872, overall["x0_mean_isolated"]),
        ("weighted consensus 1.4099", 1.4099,
         results["degroot"]["weighted"]["overall"]["consensus_giant"]),
        ("er clustering 0.100", 0.100, nulls["er_theory"]["avg_clustering"]),
        ("er path length 2.073", 2.073, nulls["er_theory"]["avg_path_length"]),
        ("er giant 0.9998", 0.9998, nulls["er_theory"]["giant_fraction"]),
        ("average degree 8.62", 8.62, nulls["graph"]["k_mean"]),
    ]:
        eq(label, doc, real)

    ordering = results["threshold_sensitivity"]["topic_ordering_holds_at_every_cut"]
    claim("topic ordering holds at every cut", all(ordering.values()))
    claim("8 respondents still isolated at q=0.50", sweep[0.5]["n_isolates"] == 8)
    claim("every slem below 1", all(d["slem"] < 1 for d in degroot.values()))
    claim("overall has no bipartite component",
          overall["n_oscillating_nodes"] == 0)
    claim("the other four each have one",
          all(degroot[n]["n_oscillating_nodes"] > 0
              for n in ["technology", "education", "ethics", "environment"]))
    claim("60-question permutation is significant",
          perms["all 60 question scores"]["significant_at_05"])
    claim("topic-mean permutation is not significant",
          not perms["4 topic means"]["significant_at_05"])
    claim("all five networks have 375 edges",
          all(m["structure"]["n_edges"] == 375 for m in metrics.values()))

    # AVIRAL.md quotes population means with missing answers removed from the
    # average, not replaced by 0. Check his four topics reproduce that way, so
    # the two documents in the report do not silently disagree.
    scores, meta = C.load_scores(), C.load_meta()
    skipped = C.topic_means(scores, meta, impute_zero=False)
    for topic, mean, sd in [("technology", 0.99, 0.37), ("education", 0.91, 0.35),
                            ("ethics", 1.28, 0.45), ("environment", 1.37, 0.47)]:
        eq(f"AVIRAL.md {topic} mean", mean, skipped[topic].mean())
        eq(f"AVIRAL.md {topic} sd", sd, skipped[topic].std())

    print(f"  checked {CHECKED} numbers and claims across both writeups")
    print(f"  mismatches: {len(BAD)}")
    for entry in BAD:
        print(f"    {entry}")
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
