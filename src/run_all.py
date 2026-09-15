"""
Run the whole dynamics analysis end to end.

Each part also runs on its own and writes to its own key in
`data/dynamics_metrics.json`, so order does not matter. Takes about 90
seconds, almost all of it the degree-preserving rewirings in nullmodels.py.
"""

from __future__ import annotations

import time

import degroot
import epidemic
import nullmodels
import sensitivity

PARTS = [
    ("A  DeGroot dynamics", degroot.main),
    ("B  SIS epidemic threshold", epidemic.main),
    ("C+D  null models", nullmodels.main),
    ("--  threshold sensitivity", sensitivity.main),
]


def main() -> None:
    start = time.time()

    for label, run in PARTS:
        print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
        run()

    print(f"\n{'=' * 70}")
    print(f"done in {time.time() - start:.0f}s")
    print("results  -> data/dynamics_metrics.json")
    print("figures  -> figures/dynamics_*.png")


if __name__ == "__main__":
    main()
