"""TASK-114 Step 1 -- nested-refinement chain construction and measurement (`H114`, `ADR-115`).

READ-ONLY. For every (seed, Core target) pair across the already-committed `4001-4030`
(`docs/benchmark/task-109-evidence/engine-raw/`) and `4101-4130` baseline-only
(`docs/benchmark/task-112-evidence/step5-paired-4101-4130/baseline-seed-*.json`) data where a
"broad" candidate in that seed's real, committed final top-15 covers the target (Coverage,
recall >= 0.5) via a CLEAN subset of the target's own canonical literals (no extraneous,
off-target conditions), this script:

  1. Identifies the broad candidate (fewest conditions, i.e. most general, if more than one
     qualifies) straight from the committed raw data -- no re-running of search/beam/selection.
  2. Builds the nested chain `broad -> +literal -> +literal -> ... -> canonical`, adding the
     target's own remaining canonical literals one at a time, in the canonical rule's own
     declared order (`synthetic_benchmark_v2_targets.DESIGNS`).
  3. At EVERY step of the chain, measures using the real, frozen, UNMODIFIED
     `discovery-engine-v0.6.2` functions directly (`_metric`, `_eligible`, `_development_score`,
     `_exposed_rows` -- called, never copied or re-derived) plus the real, unmodified
     `benchmark_v2_scoring.py` functions (`effective_rule`, `pair_metrics`, `metric_specific`) for
     Coverage/recall, the Specific-metric exposure-Jaccard (`j_e`), and literal-match cp/cr. NO
     new scoring formula of any kind is introduced anywhere in this script.

Validation (`run_validation`, contract 1.3.0) is handled by `step1b_validate_chains.py` as a
separate pass (batched once per seed, reusing this step's output) -- not duplicated here.

Engine sha256 is verified before and after every invocation of this script.
"""
# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parents[3]
ANALYTICS_SRC = REPO / "packages/analytics/src"
SCHEMAS_SRC = REPO / "packages/schemas/src"
SCRIPTS = REPO / "scripts"
T107_EVIDENCE = REPO / "docs/benchmark/task-107-evidence"
T109_RAW = REPO / "docs/benchmark/task-109-evidence/engine-raw"
T112_BASELINE = REPO / "docs/benchmark/task-112-evidence/step5-paired-4101-4130"
OUT_DIR = Path(__file__).resolve().parent / "step1-chains-raw"

ENGINE_PATH = ANALYTICS_SRC / "policy_analytics/discovery/engine.py"
EXPECTED_ENGINE_SHA256 = "fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549"

sys.path[:0] = [str(ANALYTICS_SRC), str(SCHEMAS_SRC), str(SCRIPTS), str(T107_EVIDENCE)]


def _verify_engine() -> str:
    digest = hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest()
    if digest != EXPECTED_ENGINE_SHA256:
        raise SystemExit(f"engine.py sha256 mismatch: got {digest}, expected {EXPECTED_ENGINE_SHA256}")
    return digest


_verify_engine()

import polars as pl  # noqa: E402
import v2_common as vc  # noqa: E402
import policy_analytics.discovery.engine as engine  # noqa: E402
import policy_analytics.synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics import benchmark_v2_scoring as scoring  # noqa: E402
from policy_analytics.outcomes import primary_outcome  # noqa: E402

if engine.DISCOVERY_METHOD_VERSION != "discovery-engine-v0.6.2":
    raise SystemExit(f"unexpected engine version: {engine.DISCOVERY_METHOD_VERSION}")

FINAL_CORE: tuple[str, ...] = ("C02", "C04", "C06", "C07", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
COVERAGE_RECALL = scoring.CONSTANTS.coverage_recall  # 0.5, real constant, not re-chosen here
DESIGN_INDEX = tg.design_index()


def canonical_conditions(target_id: str) -> tuple[scoring.CondSpec, ...]:
    """Canonical literals in the target design's own declared order (NOT re-sorted)."""
    design = DESIGN_INDEX[target_id]
    return tuple(scoring.CondSpec(c.feature, c.operator, c.value) for c in design.conditions)


CHAINABLE_TARGETS = tuple(t for t in FINAL_CORE if len(canonical_conditions(t)) >= 2)
NON_CHAINABLE_TARGETS = tuple(t for t in FINAL_CORE if t not in CHAINABLE_TARGETS)


def _load_seed_doc(seed: int) -> dict[str, Any]:
    if 4001 <= seed <= 4030:
        path = T109_RAW / f"seed-{seed}.json"
    elif 4101 <= seed <= 4130:
        path = T112_BASELINE / f"baseline-seed-{seed}.json"
    else:
        raise ValueError(f"seed {seed} outside the authorized ranges 4001-4030 / 4101-4130")
    return json.loads(path.read_text(encoding="utf-8"))


def _literal_matches(cond: dict[str, Any], canon: scoring.CondSpec) -> bool:
    """`_compatible`+`nested` specialized to a single discovered condition vs one canonical
    literal: eq requires identical (feature, value); ge/lt requires same feature+operator only,
    since two threshold slices on the same totally-ordered column are ALWAYS nested regardless of
    the specific threshold value (this is a property of `ge`/`lt` semantics, not an approximation
    introduced here) -- mathematically identical to `benchmark_v2_scoring.conditions_match`'s own
    `_compatible` + `nested` for this exact case (same feature, same direction, both non-empty row
    sets, which every real discovered atom and every real canonical literal always have)."""
    if cond["feature"] != canon.feature:
        return False
    if canon.operator == "eq":
        return cond["operator"] == "eq" and cond["value"] == canon.value
    if canon.operator in ("ge", "lt"):
        return cond["operator"] == canon.operator
    return False


def _find_broad_candidates(
    seed_doc: dict[str, Any], target_id: str, canon: tuple[scoring.CondSpec, ...]
) -> dict[str, Any]:
    """Scan the seed's real, committed final top-15 for CLEAN broad candidates covering
    `target_id`: every one of the candidate's own conditions matches a distinct canonical literal
    (no extraneous, off-target condition), and at least one canonical literal remains unmatched.
    Returns the chosen broad candidate (fewest conditions; tie-break lowest candidate_id) plus the
    full list of all candidates that covered the target, for transparency."""
    engine_by_id = {c["candidate_id"]: c for c in seed_doc["engine"]["candidates"]}
    clean_broad: list[dict[str, Any]] = []
    all_covering: list[dict[str, Any]] = []
    for sc in seed_doc["score"]["candidates"]:
        pm = sc["per_target"].get(target_id)
        if pm is None or pm["recall"] < COVERAGE_RECALL:
            continue
        cid = sc["candidate_id"]
        econd = engine_by_id[cid]["conditions"]  # list of {feature, operator, value} dicts
        all_covering.append({"candidate_id": cid, "conditions": econd, "recall": pm["recall"]})
        matched = [lit for lit in canon if any(_literal_matches(c, lit) for c in econd)]
        matched_set = {id(m) for m in matched}  # canon literals are distinct objects per target
        unmatched_conditions = [
            c for c in econd if not any(_literal_matches(c, lit) for lit in canon)
        ]
        is_clean = len(unmatched_conditions) == 0 and len(matched) == len(econd)
        if is_clean and len(matched_set) < len(canon):
            clean_broad.append(
                {
                    "candidate_id": cid,
                    "conditions": econd,
                    "recall": pm["recall"],
                    "n_matched_canonical_literals": len(matched_set),
                }
            )
    chosen = None
    if clean_broad:
        chosen = sorted(clean_broad, key=lambda c: (len(c["conditions"]), c["candidate_id"]))[0]
    return {"chosen_broad_candidate": chosen, "all_clean_broad_candidates": clean_broad,
            "all_covering_candidates": all_covering}


def _build_chain_steps(
    broad_conditions: list[dict[str, Any]], canon: tuple[scoring.CondSpec, ...]
) -> list[list[dict[str, Any]]]:
    matched_canon_idx = {
        i for i, lit in enumerate(canon) if any(_literal_matches(c, lit) for c in broad_conditions)
    }
    remaining = [lit for i, lit in enumerate(canon) if i not in matched_canon_idx]
    steps = [list(broad_conditions)]
    current = list(broad_conditions)
    for lit in remaining:
        current = current + [{"feature": lit.feature, "operator": lit.operator, "value": lit.value}]
        steps.append(list(current))
    return steps


def _to_engine_conditions(step_conditions: list[dict[str, Any]]) -> tuple[engine.Condition, ...]:
    return tuple(
        sorted(engine.Condition(c["feature"], c["operator"], c["value"]) for c in step_conditions)
    )


def _to_condspecs(step_conditions: list[dict[str, Any]]) -> tuple[scoring.CondSpec, ...]:
    return tuple(scoring.CondSpec(c["feature"], c["operator"], c["value"]) for c in step_conditions)


def _measure_step(
    draw: "vc.Draw",
    outcome: Any,
    config: "engine.DiscoveryConfig",
    development: pl.DataFrame,
    step_conditions: list[dict[str, Any]],
    target: "scoring.Target",
) -> dict[str, Any]:
    econd = _to_engine_conditions(step_conditions)
    cs = _to_condspecs(step_conditions)
    metric = engine._metric(draw.frame, econd, outcome, "development")
    eligible = engine._eligible(metric, config)
    dev_score = (
        engine._development_score(metric, len(econd), config) if metric is not None else None
    )
    exposed_rows_dev = engine._exposed_rows(development, econd)

    exposed_mask = draw.space.rule_mask(cs)
    eff = scoring.effective_rule(draw.space, cs, scoring.CONSTANTS.nu)
    pm = scoring.pair_metrics(draw.space, eff.conditions, exposed_mask, target)
    is_specific = scoring.metric_specific(pm, scoring.CONSTANTS.theta_j, scoring.CONSTANTS.theta_p)

    return {
        "conditions": step_conditions,
        "n_conditions": len(step_conditions),
        "engine_metric_development": None
        if metric is None
        else {
            "n_population": metric.n_population,
            "n_exposed": metric.n_exposed,
            "support": metric.support,
            "exposed_mean": metric.exposed_mean,
            "comparison_mean": metric.comparison_mean,
            "harm_per_booking": metric.harm_per_booking,
            "historical_exposure": metric.historical_exposure,
        },
        "eligible": eligible,
        "development_score": dev_score,
        "n_exposed_rows_development_split": len(exposed_rows_dev),
        "benchmark_v2_scoring": {
            "effective_conditions": [
                {"feature": c.feature, "operator": c.operator, "value": c.value}
                for c in eff.conditions
            ],
            "dropped_vacuous_conditions": [
                {"feature": c.feature, "operator": c.operator, "value": c.value}
                for c in eff.dropped
            ],
            "recall": pm.recall,
            "precision": pm.precision,
            "j_e": pm.j_e,
            "cp": pm.cp,
            "cr": pm.cr,
            "n_effective": pm.n_effective,
            "n_exposed_full_dataset": pm.n_exposed,
            "covers_target_recall_ge_0_5": pm.recall >= COVERAGE_RECALL,
            "metric_specific_j_ge_theta_j_and_cp_ge_theta_p": is_specific,
        },
    }


def build_for_seed(seed: int) -> dict[str, Any]:
    seed_doc = _load_seed_doc(seed)
    results: dict[str, Any] = {"seed": seed, "targets": {}}

    with tempfile.TemporaryDirectory(prefix=f"task114-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        outcome = primary_outcome()
        config = engine.DiscoveryConfig(seed=seed)
        development = draw.frame.filter(pl.col("split_label") == "development")

        for target_id in NON_CHAINABLE_TARGETS:
            results["targets"][target_id] = {
                "chainable": False,
                "reason": "canonical target has a single literal; max_conditions=3 leaves no "
                "second true-to-target literal to add -- excluded from chain construction, not a "
                "qualifying or non-qualifying case either way.",
            }

        for target_id in CHAINABLE_TARGETS:
            canon = canonical_conditions(target_id)
            design = DESIGN_INDEX[target_id]
            target = scoring.Target(
                target_id=target_id,
                stratum="core",
                conditions=canon,
                affected=draw.masks[target_id],
                canonical_in_language=canon,
                assessed=True,
            )
            found = _find_broad_candidates(seed_doc, target_id, canon)
            entry: dict[str, Any] = {
                "chainable": True,
                "canonical_rule": design.rule,
                "canonical_literal_count": len(canon),
                "all_covering_candidates": found["all_covering_candidates"],
                "all_clean_broad_candidates": found["all_clean_broad_candidates"],
            }
            chosen = found["chosen_broad_candidate"]
            if chosen is None:
                entry["has_qualifying_broad_candidate"] = False
                results["targets"][target_id] = entry
                continue
            entry["has_qualifying_broad_candidate"] = True
            entry["chosen_broad_candidate"] = chosen
            steps = _build_chain_steps(chosen["conditions"], canon)
            entry["chain_steps"] = [
                _measure_step(draw, outcome, config, development, step, target) for step in steps
            ]
            results["targets"][target_id] = entry

    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for seed in args.seeds:
        out_path = OUT_DIR / f"seed-{seed}.json"
        if out_path.exists():
            print(f"seed {seed}: already built, skipping")
            continue
        print(f"seed {seed}: building chains...", flush=True)
        result = build_for_seed(seed)
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        n_qualifying = sum(
            1
            for t in result["targets"].values()
            if t.get("chainable") and t.get("has_qualifying_broad_candidate")
        )
        print(f"  wrote {out_path} ({n_qualifying}/{len(CHAINABLE_TARGETS)} targets have a qualifying broad candidate)")

    final_digest = _verify_engine()
    print(f"engine.py sha256 after run: {final_digest} (unchanged)")


if __name__ == "__main__":
    main()
