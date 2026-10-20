"""Analysis 2: diagnostic sweep of the volume exponent alpha in S_alpha = Delta * n**alpha / c(k).

Runs the real, unmodified `discover_candidates` with `DiscoveryConfig(population_score_exponent=alpha)`
(an existing configuration field; `engine.py` is not edited) on the composite v2 draw, and scores each
of the 15 candidates against the 11 Core targets with the real scorer's geometry: Coverage
(recall >= 0.5) and the *metric part* of Specific (exposure Jaccard >= 0.5, effective-condition
precision 1, credited target). Validation is not run, so "Specific" here omits the
`predictive_association` clause; at alpha = 0.5 validation removed 0.57 of 15 candidates per seed on
average (TASK-109). Diagnostic only: not a proposal for a new default.
  run --seeds A B --alphas a1 a2 ... --dir D [--procs N];  merge --dir D --out F
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPOSITORY / "packages/analytics/src"),
    str(REPOSITORY / "packages/schemas/src"),
    str(REPOSITORY / "scripts"),
    str(REPOSITORY / "docs/benchmark/task-107-evidence"),
    str(REPOSITORY / "docs/benchmark/task-109-evidence"),
]

import run_blind_engine as rbe  # noqa: E402
import v2_common as vc  # noqa: E402
from policy_analytics.discovery.engine import DiscoveryConfig, discover_candidates  # noqa: E402
from policy_analytics.outcomes import primary_outcome  # noqa: E402

tg = vc.tg
scoring = vc.scoring


def run_one(seed: int, alpha: float) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"alpha-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        config = replace(DiscoveryConfig(seed=seed), population_score_exponent=alpha)
        doc = discover_candidates(draw.frame, draw.features, primary_outcome(), config)
        targets = [t for t in rbe.targets_for_draw(draw) if t.assessed and t.stratum == "core"]
        cands = []
        coverage: set[str] = set()
        specific: set[str] = set()
        for raw in doc["candidates"]:
            conds = tuple(
                scoring.CondSpec(str(c["feature"]), str(c["operator"]), c["value"])
                for c in raw["conditions"]
            )
            exposed = draw.space.rule_mask(conds)
            eff = scoring.effective_rule(draw.space, conds)
            pms = {t.target_id: scoring.pair_metrics(draw.space, eff.conditions, exposed, t) for t in targets}
            covers = sorted(tid for tid, pm in pms.items() if pm.recall >= scoring.CONSTANTS.coverage_recall)
            credited = max(sorted(pms), key=lambda tid: pms[tid].j_e)
            spec = scoring.metric_specific(pms[credited], scoring.CONSTANTS.theta_j, scoring.CONSTANTS.theta_p)
            coverage.update(covers)
            if spec:
                specific.add(credited)
            cands.append({
                "conditions": [f"{c.feature} {c.operator} {c.value}" for c in conds],
                "n_exposed_development": raw["development"]["n_exposed"],
                "harm_per_booking": raw["development"]["harm_per_booking"],
                "n_targets_covered": len(covers),
                "best_j": pms[credited].j_e,
                "credited": credited,
                "metric_specific": spec,
            })
    print(f"seed {seed} alpha {alpha} done", flush=True)
    return {"seed": seed, "alpha": alpha, "coverage_targets": sorted(coverage),
            "metric_specific_targets": sorted(specific), "candidates": cands,
            "evaluated_hypotheses": doc["search"]["evaluated_hypotheses"]}


def run_job(seed: int, alpha: float, out_dir: Path) -> str:
    """One (seed, alpha) job written to its own file, so a failure or restart loses nothing."""
    path = out_dir / f"alpha-{alpha:g}-seed-{seed}.json"
    if path.exists():
        return f"skip {path.name}"
    try:
        result = run_one(seed, alpha)
    except Exception as exc:  # noqa: BLE001 - reported, never silently dropped
        return f"FAILED {path.name}: {exc!r}"
    path.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return f"ok {path.name}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "merge"])
    ap.add_argument("--seeds", type=int, nargs=2)
    ap.add_argument("--alphas", type=float, nargs="+")
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    a.dir.mkdir(parents=True, exist_ok=True)
    if a.cmd == "merge":
        data = [json.loads(f.read_text()) for f in sorted(a.dir.glob("alpha-*.json"))]
        a.out.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"merged {len(data)} jobs into {a.out}")
        return
    for al in a.alphas:
        DiscoveryConfig(population_score_exponent=al)  # fail fast on an invalid alpha, before any job
    jobs = [(s, al, a.dir) for al in a.alphas for s in range(a.seeds[0], a.seeds[1] + 1)]
    with Pool(a.procs) as pool:
        for line in pool.starmap(run_job, jobs, chunksize=1):
            print(line, flush=True)


if __name__ == "__main__":
    main()
