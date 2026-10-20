"""Analysis 1: complement contamination tested by common random numbers.

For each seed, the v2 generator is drawn three ways with byte-identical covariates and per-row
outcome streams (the generator's common-random-numbers design): no planted target, one target alone,
and the full 20-target composite. For every literal of every Core target, the real `_metric` contrast
on the development split is computed in all three. Because only the rows of planted targets differ,
`delta(composite) - delta(alone)` is exactly the contribution of the other nineteen targets.

Read-only: imports the frozen engine and generator; edits nothing.
  run --seeds A B --out F [--procs N]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPOSITORY / "packages/analytics/src"),
    str(REPOSITORY / "packages/schemas/src"),
    str(REPOSITORY / "docs/benchmark/task-107-evidence"),
]

import v2_common as vc  # noqa: E402
from policy_analytics.discovery.engine import Condition, _metric  # noqa: E402  # pyright: ignore[reportPrivateUsage]
from policy_analytics.outcomes import primary_outcome  # noqa: E402

tg = vc.tg
CORE = ("C02", "C04", "C06", "C07", "C08", "C09", "C11", "C12", "C14", "C15", "H01")


def literals(tid: str) -> list[tuple[Condition, ...]]:
    conds = [Condition(c.feature, c.operator, c.value) for c in tg.design_index()[tid].conditions]  # type: ignore[arg-type]
    rules = [(c,) for c in conds]
    if len(conds) > 1:
        rules.append(tuple(sorted(conds)))
    return rules


def contrasts(frame: Any, rules: list[tuple[Condition, ...]]) -> dict[str, dict[str, float]]:
    outcome = primary_outcome()
    out: dict[str, dict[str, float]] = {}
    for rule in rules:
        m = _metric(frame, rule, outcome, "development")
        key = " & ".join(f"{c.feature} {c.operator} {c.value}" for c in rule)
        out[key] = {"harm": m.harm_per_booking, "n": m.n_exposed} if m else {"harm": float("nan"), "n": 0}
    return out


def run_seed(seed: int) -> dict[str, Any]:
    index = tg.design_index()
    result: dict[str, Any] = {"seed": seed, "targets": {}}
    with tempfile.TemporaryDirectory(prefix=f"contam-{seed}-") as tmp:
        root = Path(tmp)
        composite = vc.build_draw(seed, root / "all", tg.DESIGNS)
        empty = vc.build_draw(seed, root / "none", ())
        for tid in CORE:
            rules = literals(tid)
            alone = vc.build_draw(seed, root / tid, (index[tid],))
            result["targets"][tid] = {
                "none": contrasts(empty.frame, rules),
                "alone": contrasts(alone.frame, rules),
                "composite": contrasts(composite.frame, rules),
            }
    print(f"seed {seed} done", flush=True)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--seeds", type=int, nargs=2, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    with Pool(a.procs) as pool:
        data = pool.map(run_seed, range(a.seeds[0], a.seeds[1] + 1))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
