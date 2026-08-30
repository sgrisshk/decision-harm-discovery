"""TASK-084 branches 2+3 diagnostic: case-level error decomposition and residual forensics.

Diagnosis only (`ADR-085`/`TASK-084`). Does not change the estimator, `economic_impact.py`,
`scripts/evaluate_benchmark.py`'s own metric-6 definition, or any gate. Reuses the real, unmodified
`policy_analytics.validation.apply`/`policy_analytics.outcomes` functions for every quantity
computed here -- no reimplemented estimator logic.

**Step 1 (branch 2 substrate).** Reproduces `TASK-083`'s frozen `candidates.json`
(`/private/tmp/policy-blind-runs/task-083-official-20260830-001/frozen/candidates.json` -- the same
gitignored-`artifacts/`-workaround path `ADR-084` used, disclosed again here) through the real,
unmodified `scripts/validate_candidates.py` -> `scripts/evaluate_benchmark.py` pipeline, to a scratch
path, exactly as `ADR-084` did. `TASK-073`'s own frozen candidates were checked for and are NOT
reachable in this worktree (only `task-083-official-20260830-001` exists under
`/private/tmp/policy-blind-runs/`) -- the same disclosed `artifacts/`-absent limitation
`TASK-075`/`TASK-078`/`TASK-079`/`ADR-084` already recorded, not silently worked around.

**Step 2 (branch 2, decomposition).** For every ground-truth-matched candidate, builds a real
case-level table: exposed_n (candidate's own full rule population), overlap_n (candidate's exposed
set intersected with its matched pattern's true affected-record-id set), dilution factor, overlap
fraction, and SIGNED (not just absolute) relative error for three variants of the reported side:
  (i)   whole-rule       -- the official, decision-gate-governing metric 6 number (unchanged).
  (ii)  attribution-narrowed -- TASK-059's existing diagnostic (population-only correction: same
        diluted per-record effect, just multiplied by overlap_n instead of the full exposed count).
  (iii) doubly-narrowed   -- NEW in this script: per-record effect itself recomputed from the real
        `summarize_group`/`raw_difference`/`harm_score`/`cluster_bootstrap_replicates` functions
        restricted to just the overlap population as "exposed" (comparison = everyone outside the
        overlap, the same convention `apply.py` already uses), then scaled by overlap_n. This is
        the estimator's own logic, re-run on a narrower input population -- not a new method.

**Step 3 (branch 3, residual characterization).** Compares (ii) vs (iii): if the attribution-narrowed
diagnostic's residual (73.6% median, per ADR-084) is mostly closed by (iii), the residual is still
substantially a DILUTION effect -- just one TASK-059's specific narrowing (population-count-only)
does not remove, because it reuses the whole-rule's own diluted per-record effect estimate
unchanged. If (iii) leaves a comparable residual to (ii), the remaining error is NOT explained by
population mismatch in either form and is a separate estimator/heterogeneity issue. Both outcomes
are real, reportable findings; this script does not presuppose which one holds.

Ground truth is opened only for diagnostic decomposition, matching every prior forensic task in this
chain (`TASK-069`/`070`/`075`/`078`/`079`) -- never for a production-facing narrowing or estimator
change.

Usage: uv run python scripts/diagnose_task084_branch2_3_error_decomposition.py
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

import polars as pl  # noqa: E402

from policy_analytics.outcomes import harm_score, raw_difference, summarize_group  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    BOOTSTRAP_SEED,
    DEFAULT_THRESHOLDS,
    DIAGNOSTIC_BOOTSTRAP_REPS,
    cluster_bootstrap_replicates,
    cluster_cells,
    load_analytical_frame,
    percentile_ci,
    rule_expr,
)

import evaluate_benchmark as eb  # noqa: E402

FROZEN_CANDIDATES = Path(
    "/private/tmp/policy-blind-runs/task-083-official-20260830-001/frozen/candidates.json"
)
FROZEN_METRICS = Path(
    "/private/tmp/policy-blind-runs/task-083-official-20260830-001/frozen/discovery_metrics.json"
)
DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"

SCRATCH_ROOT = Path(
    "<scratch>"
    "f82f6987-cd7b-429c-b576-4ad2d17b9dba/scratchpad/task084/branch2_3"
)


def _run_checked(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=REPOSITORY, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {' '.join(cmd)}")


def _reproduce_task083() -> tuple[dict[str, Any], dict[str, Any]]:
    """Reproduce TASK-083's frozen candidates through the real validate/evaluate pipeline."""
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    validation_output = SCRATCH_ROOT / "validation-report.json"
    evaluation_output = SCRATCH_ROOT / "evaluation-report.json"
    if not validation_output.exists():
        _run_checked(
            [
                sys.executable,
                str(REPOSITORY / "scripts/validate_candidates.py"),
                "--candidates",
                str(FROZEN_CANDIDATES),
                "--metrics",
                str(FROZEN_METRICS),
                "--dataset-root",
                str(DATASET_ROOT),
                "--output",
                str(validation_output),
                "--analysis-run-id",
                "task084-branch2-reproduction-of-task083",
                "--blind-compliant",
                "--founder-block-lifted",
            ]
        )
    if not evaluation_output.exists():
        _run_checked(
            [
                sys.executable,
                str(REPOSITORY / "scripts/evaluate_benchmark.py"),
                "--validation-report",
                str(validation_output),
                "--output",
                str(evaluation_output),
                "--dataset-root",
                str(DATASET_ROOT),
                "--ground-truth",
                str(GROUND_TRUTH_PATH),
            ]
        )
    validation = json.loads(validation_output.read_text(encoding="utf-8"))
    evaluation = json.loads(evaluation_output.read_text(encoding="utf-8"))
    return validation, evaluation


def main() -> None:
    validation, evaluation = _reproduce_task083()

    # --- Reproduction sanity check against ADR-084's own published numbers -----------------------
    metrics = evaluation["metrics"]
    sanity = {
        "top10_precision": metrics["top_k_precision"]["value"],
        "economic_weighted_recall": metrics["economic_weighted_recall"]["value"],
        "any_trap_promoted": metrics["confounder_trap_rejection"]["any_trap_promoted"],
        "direction_accuracy": metrics["effect_direction_accuracy"]["value"],
        "median_impact_error": metrics["economic_impact_estimation_error"]["median_relative_error"],
        "median_attribution_narrowed_error": metrics[
            "economic_impact_estimation_error_attribution_narrowed_diagnostic"
        ]["median_relative_error"],
    }
    print("=== reproduction sanity check (should match ADR-084/TASK-083's published numbers) ===")
    print(json.dumps(sanity, indent=2))

    # --- Load frame + ground truth for the doubly-narrowed re-estimate ---------------------------
    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    patterns_by_id = {p["id"]: p for p in ground_truth["patterns"]}
    outcome_metadata = eb._primary_outcome_metadata(manifest)
    record_id_column = eb._record_id_column(manifest)
    frame = load_analytical_frame(DATASET_ROOT)
    booking_ids = frame[record_id_column].to_list()

    class _Outcome:
        outcome_id = str(outcome_metadata["outcome_id"])
        column = str(outcome_metadata["column"])
        unit = str(outcome_metadata["unit"])
        higher_is_worse = bool(outcome_metadata["higher_is_worse"])
        harm_multiplier = 1 if bool(outcome_metadata["higher_is_worse"]) else -1

    outcome = _Outcome()

    candidates_payload = json.loads(FROZEN_CANDIDATES.read_text(encoding="utf-8"))
    raw_by_id = {c["candidate_id"]: c for c in candidates_payload["candidates"]}
    report_by_id = {c["candidate_id"]: c for c in validation["candidates"]}

    impact_details = {
        d["candidate_id"]: d for d in metrics["economic_impact_estimation_error"]["details"]
    }
    attribution_details = {
        d["candidate_id"]: d
        for d in metrics["economic_impact_estimation_error_attribution_narrowed_diagnostic"][
            "details"
        ]
        if "candidate_id" in d
    }

    # matched, validated candidates -- same population metric 6 governs
    matched_candidate_ids = sorted(impact_details.keys())

    case_table: list[dict[str, Any]] = []
    for cid in matched_candidate_ids:
        raw = raw_by_id[cid]
        conditions = [eb._condition_from_dict(c) for c in raw["conditions"]]
        mask = frame.select(rule_expr(conditions).alias("m"))["m"]
        exposed_ids = frozenset(
            bid for bid, exposed in zip(booking_ids, mask.to_list(), strict=True) if exposed
        )
        matched_patterns = cast(list[str], impact_details[cid]["matched_patterns"])
        overlap_ids: frozenset[str] = frozenset()
        pattern_affected_total = 0
        for pid in matched_patterns:
            affected = eb._affected_ids(patterns_by_id[pid])
            overlap_ids |= exposed_ids & affected
            pattern_affected_total += len(affected)

        exposed_n = len(exposed_ids)
        overlap_n = len(overlap_ids)
        dilution = exposed_n / overlap_n if overlap_n else float("inf")
        overlap_fraction = overlap_n / exposed_n if exposed_n else 0.0
        recall_of_true_pattern = overlap_n / pattern_affected_total if pattern_affected_total else 0.0

        truth_impact = float(impact_details[cid]["matched_ground_truth_impact_eur"])
        whole_rule_reported = float(impact_details[cid]["reported_exposure_ci_midpoint_eur"])
        whole_rule_signed_error = (
            (whole_rule_reported - truth_impact) / truth_impact if truth_impact else None
        )

        attrib = attribution_details.get(cid)
        attrib_reported = float(attrib["attribution_narrowed_impact_point_eur"]) if attrib else None
        attrib_signed_error = (
            (attrib_reported - truth_impact) / truth_impact
            if (attrib_reported is not None and truth_impact)
            else None
        )

        # --- doubly-narrowed: recompute the per-record effect ITSELF over just the overlap
        # population (comparison = everyone outside the overlap), using the real estimator
        # functions, not a reimplementation.
        overlap_mask = pl.Series(
            "m", [bid in overlap_ids for bid in booking_ids]
        )
        if overlap_n == 0 or overlap_n == len(booking_ids):
            doubly_narrowed_reported = None
            doubly_narrowed_signed_error = None
            doubly_narrowed_per_record = None
        else:
            exposed_group = frame.filter(overlap_mask)[outcome.column].to_list()
            comparison_group = frame.filter(~overlap_mask)[outcome.column].to_list()
            exposed_summary = summarize_group(exposed_group, outcome)
            comparison_summary = summarize_group(comparison_group, outcome)
            if exposed_summary.mean is None or comparison_summary.mean is None:
                doubly_narrowed_reported = None
                doubly_narrowed_signed_error = None
                doubly_narrowed_per_record = None
            else:
                diff = raw_difference(exposed_summary, comparison_summary)
                doubly_narrowed_per_record = harm_score(diff, outcome)
                # CI via the same cluster-bootstrap procedure economic_impact.py's own reported
                # point (a CI midpoint, not the raw statistic) uses -- for exact-convention
                # comparability with whole_rule_reported/attrib_reported above, both of which are
                # also CI midpoints, not raw point estimates.
                clusters = cluster_cells(frame, overlap_mask, outcome.column, manifest["clustering"]["column"])
                rng = random.Random(BOOTSTRAP_SEED)
                reps = cluster_bootstrap_replicates(clusters, DIAGNOSTIC_BOOTSTRAP_REPS, rng)
                per_record_reps = [d * outcome.harm_multiplier for d in reps]
                if per_record_reps:
                    ci_low, ci_high = percentile_ci(per_record_reps, DEFAULT_THRESHOLDS.confidence_level)
                    ci_low_scaled, ci_high_scaled = ci_low * overlap_n, ci_high * overlap_n
                    point_scaled = doubly_narrowed_per_record * overlap_n
                    lo = min(ci_low_scaled, ci_high_scaled, point_scaled)
                    hi = max(ci_low_scaled, ci_high_scaled, point_scaled)
                    doubly_narrowed_reported = (lo + hi) / 2
                else:
                    doubly_narrowed_reported = doubly_narrowed_per_record * overlap_n
                doubly_narrowed_signed_error = (
                    (doubly_narrowed_reported - truth_impact) / truth_impact if truth_impact else None
                )

        case_table.append(
            {
                "candidate_id": cid,
                "matched_patterns": matched_patterns,
                "exposed_n_full_rule": exposed_n,
                "overlap_n": overlap_n,
                "pattern_affected_total": pattern_affected_total,
                "dilution_factor": dilution,
                "overlap_fraction_of_rule": overlap_fraction,
                "recall_of_true_pattern": recall_of_true_pattern,
                "truth_impact_eur": truth_impact,
                "whole_rule_reported_eur": whole_rule_reported,
                "whole_rule_signed_relative_error": whole_rule_signed_error,
                "whole_rule_abs_relative_error": impact_details[cid]["relative_error"],
                "attribution_narrowed_reported_eur": attrib_reported,
                "attribution_narrowed_signed_relative_error": attrib_signed_error,
                "attribution_narrowed_abs_relative_error": (
                    abs(attrib_signed_error) if attrib_signed_error is not None else None
                ),
                "doubly_narrowed_per_record_effect_eur": doubly_narrowed_per_record,
                "doubly_narrowed_reported_eur": doubly_narrowed_reported,
                "doubly_narrowed_signed_relative_error": doubly_narrowed_signed_error,
                "doubly_narrowed_abs_relative_error": (
                    abs(doubly_narrowed_signed_error)
                    if doubly_narrowed_signed_error is not None
                    else None
                ),
            }
        )

    # --- correlations (dilution vs error, at each stage of narrowing) ----------------------------
    def _pearson(xs: list[float], ys: list[float]) -> float | None:
        n = len(xs)
        if n < 2:
            return None
        mean_x, mean_y = sum(xs) / n, sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x == 0 or var_y == 0:
            return None
        return cov / (var_x * var_y) ** 0.5

    dilutions = [c["dilution_factor"] for c in case_table]
    whole_abs = [c["whole_rule_abs_relative_error"] for c in case_table]
    attrib_abs = [
        c["attribution_narrowed_abs_relative_error"]
        for c in case_table
        if c["attribution_narrowed_abs_relative_error"] is not None
    ]
    dilutions_for_attrib = [
        c["dilution_factor"]
        for c in case_table
        if c["attribution_narrowed_abs_relative_error"] is not None
    ]
    doubly_abs = [
        c["doubly_narrowed_abs_relative_error"]
        for c in case_table
        if c["doubly_narrowed_abs_relative_error"] is not None
    ]
    dilutions_for_doubly = [
        c["dilution_factor"]
        for c in case_table
        if c["doubly_narrowed_abs_relative_error"] is not None
    ]

    def _median(values: list[float]) -> float | None:
        if not values:
            return None
        s = sorted(values)
        mid = len(s) // 2
        return s[mid] if len(s) % 2 == 1 else (s[mid - 1] + s[mid]) / 2

    summary = {
        "n_matched_candidates": len(case_table),
        "median_whole_rule_abs_error": _median(whole_abs),
        "median_attribution_narrowed_abs_error": _median(attrib_abs),
        "median_doubly_narrowed_abs_error": _median(doubly_abs),
        "pearson_dilution_vs_whole_rule_abs_error": _pearson(dilutions, whole_abs),
        "pearson_dilution_vs_attribution_narrowed_abs_error": _pearson(
            dilutions_for_attrib, attrib_abs
        ),
        "pearson_dilution_vs_doubly_narrowed_abs_error": _pearson(
            dilutions_for_doubly, doubly_abs
        ),
        "n_whole_rule_overestimates": sum(
            1 for c in case_table if (c["whole_rule_signed_relative_error"] or 0) > 0
        ),
        "n_attribution_narrowed_overestimates": sum(
            1
            for c in case_table
            if c["attribution_narrowed_signed_relative_error"] is not None
            and c["attribution_narrowed_signed_relative_error"] > 0
        ),
        "n_attribution_narrowed_underestimates": sum(
            1
            for c in case_table
            if c["attribution_narrowed_signed_relative_error"] is not None
            and c["attribution_narrowed_signed_relative_error"] < 0
        ),
        "n_doubly_narrowed_overestimates": sum(
            1
            for c in case_table
            if c["doubly_narrowed_signed_relative_error"] is not None
            and c["doubly_narrowed_signed_relative_error"] > 0
        ),
        "n_doubly_narrowed_underestimates": sum(
            1
            for c in case_table
            if c["doubly_narrowed_signed_relative_error"] is not None
            and c["doubly_narrowed_signed_relative_error"] < 0
        ),
    }
    print("=== summary ===")
    print(json.dumps(summary, indent=2))

    out = {
        "sanity_check_against_ADR_084": sanity,
        "summary": summary,
        "case_table": case_table,
    }
    out_path = REPOSITORY / "docs/benchmark/task-084-branch2-3-error-decomposition-raw.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=False), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
