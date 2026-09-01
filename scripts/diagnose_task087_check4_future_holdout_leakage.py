"""TASK-087 Check 4 diagnostic: does `future_holdout` leak into candidate SELECTION, before any
economic-impact "prediction" is ever computed?

Design-only task (`TASK-087`). This script does not modify `discovery.engine`, `apply.py`,
`economic_impact.py`, or any gate/threshold. It calls the real, unmodified `discover_candidates`
twice with two `DiscoveryConfig` *parameter overrides* (never a source edit) — matching TASK-084
Branch 1's own ablation discipline (`scripts/diagnose_task084_branch1_engine_regression.py`) — and
compares the resulting top-K candidate sets directly.

**What this checks, and why it matters for TASK-087's central criterion.** The central criterion
requires that "the realized comparator must become available ONLY AFTER [prediction] time" and that
no design may let "the comparator side use information the production prediction itself could not
have used." A calibration design following TASK-085 §8.3's sketch would use `future_holdout`'s own
realized per-record effect as that comparator. This script asks a logically prior question: by the
time a candidate rule is even selected into the discovery engine's top-K output (i.e., before
`apply.py`/`economic_impact.py` ever computes an O1 "prediction" for it), has `future_holdout`
already been consulted for that exact rule?

Direct code trace (read, not modified): `discovery/engine.py`'s `_temporal_consistency` (line ~410)
computes `_metric(frame, rule, outcome, "future_holdout")` -- i.e. it reads `future_holdout`'s own
sign for every candidate rule in the pool being considered for top-K selection. Its result feeds
`_apply_stability_credit` (line ~430), producing `effective_score = development_score * (1 +
stability_credit_weight * temporal_consistency)`, which is what `_greedy_diverse_select` actually
ranks and thresholds on (via `relevance_floor_percentile`) to decide the top-K set. `DiscoveryConfig`'s
own default is `stability_credit_weight=0.5` (non-zero), and `scripts/run_discovery.py` -- the real
official-run entrypoint -- does not override it, so this is the actual, current, unconditional
default for every real candidate this project's discovery pipeline has ever produced.

This script empirically checks whether that theoretical channel has a *measurable* effect on which
candidates exist at all, by running discovery twice on the same dataset/seed/every-other-config,
varying only `stability_credit_weight` (0.5, the real default, vs 0.0, which `_apply_stability_credit`
mathematically reduces to `effective_score == development_score` unconditionally -- a run in which
`future_holdout` is still *computed* per rule for reporting, but provably never influences selection).

Usage: uv run python scripts/diagnose_task087_check4_future_holdout_leakage.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402

from policy_analytics.discovery.engine import DiscoveryConfig, discover_candidates  # noqa: E402
from policy_analytics.outcomes import outcome_definition_from_manifest  # noqa: E402

SEED = 1729
DATASET_V110 = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
OUT_PATH = REPOSITORY / "docs/benchmark/task-087-check4-future-holdout-leakage-raw.json"


def _load_frame_and_features() -> tuple[pl.DataFrame, tuple[str, ...], dict[str, Any]]:
    manifest = json.loads((DATASET_V110 / "manifest.json").read_text(encoding="utf-8"))
    features = pl.read_csv(DATASET_V110 / "features.csv", try_parse_dates=False)
    outcomes = pl.read_csv(DATASET_V110 / "outcomes.csv", try_parse_dates=False)
    metadata = pl.read_csv(DATASET_V110 / "metadata.csv", try_parse_dates=False)
    if not (features.height == outcomes.height == metadata.height):
        raise ValueError("analytical partitions are not row-aligned")
    frame = pl.concat([features, outcomes, metadata.select("split_label")], how="horizontal")
    timing = manifest["feature_timing"]
    feature_columns = tuple(
        column
        for column in features.columns
        if timing.get(column, {}).get("classification") == "DECISION_TIME"
    )
    feature_columns = tuple(
        name for name in feature_columns if name not in {"booking_date", "travel_date"}
    )
    return frame, feature_columns, manifest


def _rule_key(raw_candidate: dict[str, Any]) -> tuple[tuple[str, str, object], ...]:
    conditions = cast(list[dict[str, object]], raw_candidate["conditions"])
    return tuple(
        sorted((str(c["feature"]), str(c["operator"]), c["value"]) for c in conditions)
    )


def _run(weight: float, frame: pl.DataFrame, feature_columns: tuple[str, ...], outcome: Any) -> dict[str, Any]:
    config = DiscoveryConfig(seed=SEED, stability_credit_weight=weight)
    result = discover_candidates(frame, feature_columns, outcome, config)
    raw_candidates = cast(list[dict[str, Any]], result["candidates"])
    rules = [_rule_key(c) for c in raw_candidates]
    return {
        "stability_credit_weight": weight,
        "evaluated_hypotheses": result["search"]["evaluated_hypotheses"],
        "top_k_count": len(rules),
        "rule_keys": rules,
    }


def main() -> None:
    frame, feature_columns, manifest = _load_frame_and_features()
    outcome, outcome_contract_version = outcome_definition_from_manifest(manifest, DATASET_V110)

    default_run = _run(0.5, frame, feature_columns, outcome)  # real, unconditional shipped default
    zero_run = _run(0.0, frame, feature_columns, outcome)  # provably future_holdout-blind selection

    default_set = {tuple(r) for r in default_run["rule_keys"]}
    zero_set = {tuple(r) for r in zero_run["rule_keys"]}
    only_in_default = sorted(default_set - zero_set, key=str)
    only_in_zero = sorted(zero_set - default_set, key=str)
    shared = default_set & zero_set

    result = {
        "task": "TASK-087",
        "check": 4,
        "claim_tested": (
            "future_holdout is already consulted (via stability_credit_weight, discovery/engine.py's "
            "_temporal_consistency -> _apply_stability_credit -> _greedy_diverse_select path) during "
            "candidate SELECTION, before any O1 'prediction' is computed by apply.py/economic_impact.py "
            "-- and this measurably changes which candidates are ever selected, under the real, "
            "unconditional shipped default (stability_credit_weight=0.5, unmodified by "
            "scripts/run_discovery.py, the real official-run entrypoint)."
        ),
        "dataset": "travel-bookings-analytical-v1.1.0",
        "seed": SEED,
        "outcome_contract_version": outcome_contract_version,
        "default_run": {
            k: v for k, v in default_run.items() if k != "rule_keys"
        },
        "zero_weight_run": {
            k: v for k, v in zero_run.items() if k != "rule_keys"
        },
        "top_k_set_shared_count": len(shared),
        "top_k_set_only_in_default_count": len(only_in_default),
        "top_k_set_only_in_zero_weight_count": len(only_in_zero),
        "only_in_default_rules": only_in_default,
        "only_in_zero_weight_rules": only_in_zero,
        "leakage_has_measurable_selection_effect": bool(only_in_default or only_in_zero),
        "interpretation": (
            "If top_k_set_only_in_default_count and/or top_k_set_only_in_zero_weight_count are "
            "nonzero, discovery's real, unconditional default configuration provably changes which "
            "candidate rules are ever selected depending on future_holdout's own sign for each rule "
            "-- i.e. future_holdout is not merely 'unused by convention' by the time a candidate "
            "reaches validation/economic-impact computation, it is a real, measured input to which "
            "candidates exist to be evaluated at all. This directly bears on TASK-087's Check 4: any "
            "calibration metric using future_holdout's realized value as its comparator, run against "
            "candidates produced by the real, current default pipeline, would not be checking a "
            "genuinely blind, prospective comparator -- the comparator side already influenced which "
            "candidate the predicted side is being asked to predict."
        ),
    }
    print(json.dumps(result, indent=2))
    OUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
