"""TASK-107 Phase 2b: stability of the engine atom grid across the design-check seeds
(covariates only; real `_atoms` builder; no oracle, no engine search). Prints, per numeric feature and
grid value, in how many design-check seeds the value is a grid atom, so target thresholds can be put
on-grid by construction rather than by inspection of oracle results."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grid_explore import grid  # noqa: E402

SEEDS = range(int(sys.argv[1]), int(sys.argv[2]) + 1)
counts: dict[str, Counter[tuple[str, object]]] = {}
for seed in SEEDS:
    for feature, atoms in grid(seed).items():
        counts.setdefault(feature, Counter()).update(atoms)
n = len(list(SEEDS))
print(f"seeds: {n}")
for feature, counter in sorted(counts.items()):
    if feature in {"customer_price_eur", "quoted_cost_eur"}:
        print(feature, "continuous (grid moves per draw), not used by any target")
        continue
    print(feature, {f"{op} {value}": c for (op, value), c in sorted(counter.items(), key=str)})
