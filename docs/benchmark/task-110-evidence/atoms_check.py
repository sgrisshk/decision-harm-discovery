"""TASK-110 step B: real, read-only atom-generation check. Rebuilds each seed's draw EXACTLY as
TASK-109's `run_blind_engine.py` did (same `v2_common.build_draw`, same `DiscoveryConfig()`
defaults) and calls the REAL, unmodified `policy_analytics.discovery.engine._atoms()` directly --
no copy, no edit, no monkeypatch of engine.py. This only imports and calls the existing function.

For each of the 10 non-reliable Core targets, checks whether every one of its canonical literals
(from `synthetic_benchmark_v2_targets.py`, parsed the same way the scorer/generator already do) is
present, verbatim, in the real atom pool `_atoms()` actually generates for that seed's real
development split. This directly answers S1 ("literal not expressible by the candidate language at
all" -- never true here, since every literal is a plain eq/ge clause the grammar supports) vs S2
("expressible in principle, but `_atoms` never generates this exact value/threshold for this
dataset").
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPOSITORY / "packages/analytics/src"),
    str(REPOSITORY / "packages/schemas/src"),
    str(REPOSITORY / "scripts"),
    str(REPOSITORY / "docs/benchmark/task-107-evidence"),
]

import v2_common as vc  # noqa: E402
from policy_analytics import synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics.discovery.engine import Condition, DiscoveryConfig, _atoms  # noqa: E402

OUT = Path(__file__).resolve().parent

TARGETS = ("C02", "C04", "C06", "C08", "C09", "C11", "C12", "C14", "C15", "H01")


def canonical_conditions(tid: str) -> list[Condition]:
    design = tg.design_index()[tid]
    out = []
    for c in design.conditions:  # scoring.CondSpec: feature, operator ('eq'/'ge'), value
        out.append(Condition(c.feature, c.operator, c.value))  # type: ignore[arg-type]
    return out


def main(seeds: list[int]) -> None:
    canon = {tid: canonical_conditions(tid) for tid in TARGETS}
    results: dict[int, dict] = {}
    for seed in seeds:
        with tempfile.TemporaryDirectory(prefix=f"task110-atoms-{seed}-") as tmp:
            draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
            config = DiscoveryConfig(seed=seed)
            development = draw.frame.filter(draw.frame["split_label"] == "development")
            atoms = _atoms(development, draw.features, config)
            atom_set = set(atoms)
            per_target = {}
            for tid in TARGETS:
                lits = canon[tid]
                presence = [
                    {
                        "feature": c.feature,
                        "operator": c.operator,
                        "value": c.value,
                        "present_as_atom": c in atom_set,
                    }
                    for c in lits
                ]
                per_target[tid] = {
                    "all_literals_present": all(p["present_as_atom"] for p in presence),
                    "literals": presence,
                }
            # also record, per numeric feature touched by our 10 targets, the actual quantile
            # thresholds _atoms generated this seed (for the distance/representation discussion).
            numeric_features = sorted(
                {c.feature for tid in TARGETS for c in canon[tid] if c.operator == "ge"}
            )
            quantile_thresholds = {
                feat: sorted({a.value for a in atoms if a.feature == feat and a.operator == "ge"})
                for feat in numeric_features
            }
            results[seed] = {
                "n_atoms": len(atoms),
                "per_target": per_target,
                "numeric_quantile_thresholds_ge": quantile_thresholds,
            }
        print(f"seed {seed} done, n_atoms={results[seed]['n_atoms']}", flush=True)
    (OUT / "atoms-check-raw.json").write_text(json.dumps(results, indent=1, sort_keys=True, default=str))
    print("wrote", OUT / "atoms-check-raw.json")

    # Aggregate: for each target, across seeds, is EVERY literal always present? Ever absent?
    summary = {}
    for tid in TARGETS:
        always = all(results[s]["per_target"][tid]["all_literals_present"] for s in seeds)
        never = all(not results[s]["per_target"][tid]["all_literals_present"] for s in seeds)
        per_literal_rate = {}
        lits = canon[tid]
        for i, c in enumerate(lits):
            key = f"{c.feature} {c.operator} {c.value}"
            n_present = sum(
                1 for s in seeds if results[s]["per_target"][tid]["literals"][i]["present_as_atom"]
            )
            per_literal_rate[key] = f"{n_present}/{len(seeds)}"
        summary[tid] = {
            "all_literals_present_every_seed": always,
            "all_literals_present_no_seed": never,
            "per_literal_presence_rate": per_literal_rate,
        }
    (OUT / "atoms-check-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    print("wrote", OUT / "atoms-check-summary.json")


if __name__ == "__main__":
    main(list(range(4001, 4031)))
