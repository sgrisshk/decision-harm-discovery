"""CLI: score a frozen TASK-019 validation report against hidden ground truth (TASK-028).

Opens `synthetic_data/evaluation/hidden_ground_truth.json` — legitimate only because this runs
strictly after candidate commitment and validation are already frozen (the blind boundary this
protects is upstream, at discovery and validation time, not here). Computes the six metrics
`docs/benchmark/decision-gate.md` is scoped against: Top-K precision, economic-weighted recall,
confounder trap rejection, leakage violations, effect direction accuracy, and economic impact
estimation error. Writes one frozen, versioned report; does not edit the decision gate document.

**Matching statistic (Statistics' methodological call, delegated by decision-gate.md §"True pattern
match"):** a candidate C recovers pattern P if recall(P by C) = |C.exposed ∩ P.affected| /
|P.affected| >= MATCH_RECALL_THRESHOLD (0.5 — a majority of the pattern's affected bookings fall
inside the candidate's exposed population). This is chosen once, here, before computing any overlap
number, and is not adjusted afterward. Recall, not precision or Jaccard, is the primary statistic
because interpretable discovery is expected to return broader, more actionable rules than the exact
injected condition — a rule capturing most of a pattern's affected population is a real recovery
even if it also covers unrelated bookings; that dilution is instead visible in the impact-error
metric, where it belongs.

**`TASK-059` addition (`HANDOFF-043` remediation part 1):** metric 6's governing number
(`metrics.economic_impact_estimation_error`) is unchanged — it still compares each matched
candidate's *whole-rule* reported historical impact against the matched pattern(s)' true impact,
exactly as `docs/benchmark/decision-gate.md` pre-registered it. A second, clearly-separate,
diagnostic-only sibling metric
(`metrics.economic_impact_estimation_error_attribution_narrowed_diagnostic`) is added alongside it:
same matched-candidate population, but the reported side is recomputed over just the booking IDs a
candidate's exposed set shares with its matched pattern's `affected_booking_ids` (only knowable
here, against `hidden_ground_truth.json`, never for a real customer finding — `HANDOFF-043`, ML
Discovery dissent). **This diagnostic does not govern the decision gate and must not be substituted
for `economic_impact_estimation_error` when reading `docs/benchmark/decision-gate.md`'s bands** —
it exists to show how much of the whole-rule error is attributable to population dilution
(`task-029-benchmark-report-v1.md` §3.6) versus genuine per-booking effect misestimation, and, per
`HANDOFF-043`'s own warning, is not by itself sufficient grounds for a re-grade without `TASK-058`
(tighter candidates at search time) as well.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.validation.apply import (  # noqa: E402
    Condition,
    load_analytical_frame,
    rule_expr,
)

DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
VALIDATION_REPORT_PATH = REPOSITORY / "artifacts/validation/task-019-official-20260816-015.json"
OUTPUT_PATH = REPOSITORY / "artifacts/evaluation/task-028-benchmark-evaluation.json"

MATCH_RECALL_THRESHOLD = 0.5
TOP_K = 10
SCOREABLE_PATTERN_IDS = (
    "P01",
    "P02",
    "P03",
    "P04",
    "P06",
    "P08",
    "P09",
)  # P05, P07 excluded, §"Fixed denominators"
VALIDATED_LEVELS = (
    "predictive_association",
    "adjusted_observational_association",
    "quasi_causal_evidence",
    "experimental_evidence",
)
PROMOTED_READINESS = ("shadow_policy", "high_confidence")

TRAP_APPARENT_CONDITIONS: dict[str, tuple[str, str, object]] = {
    # trap_id -> (feature, operator, value) matching the trap's stated "apparent_feature" exactly.
    "T01": ("manager", "eq", "Manager 2"),
    "T02": ("supplier", "eq", "Atlas"),
    "T03": ("acquisition_channel", "eq", "paid_search"),
    "T04": ("payment_method", "eq", "bank_transfer"),
    "T05": ("manual_exception", "eq", True),
}


@dataclass(frozen=True, slots=True)
class CandidateScore:
    candidate_id: str
    pattern_definition: str
    economic_exposure_reported: float
    evidence_level: str | None
    policy_readiness: str
    exposed_n_full_cohort: int
    matched_patterns: list[str]
    best_pattern_recall: float
    matched_traps: list[str]
    is_true_pattern: bool
    is_trap: bool
    is_noise: bool


def _condition_from_dict(raw: dict[str, object]) -> Condition:
    return Condition(str(raw["feature"]), raw["operator"], raw["value"])  # type: ignore[arg-type]


def _matches_trap(conditions: list[dict[str, object]]) -> list[str]:
    condition_set = {(c["feature"], c["operator"], c["value"]) for c in conditions}
    return [
        trap_id
        for trap_id, apparent in TRAP_APPARENT_CONDITIONS.items()
        if apparent in condition_set
    ]


def _attribution_overlap_ids(
    exposed_ids: frozenset[str],
    matched_patterns: list[str],
    patterns_by_id: dict[str, dict[str, object]],
) -> frozenset[str]:
    """Bookings a candidate's exposed set shares with any of its matched patterns' truth-labeled
    affected population — the `TASK-059` attribution-narrowed diagnostic's population.
    """
    overlap: frozenset[str] = frozenset()
    for pid in matched_patterns:
        overlap |= exposed_ids & frozenset(patterns_by_id[pid]["affected_booking_ids"])  # type: ignore[index]
    return overlap


def _attribution_narrowed_impact(
    per_record_effect: dict[str, object], overlap_n: int
) -> tuple[float, tuple[float, float]]:
    """Scale a candidate's own reported per-record effect by a narrower population — the same
    linear scaling `economic_impact.py` already uses for
    `historical_impact = per_record_effect x affected_records`, just over `overlap_n` instead of
    the candidate's full exposed population. No new estimation method; only computable here
    because `overlap_n` requires `hidden_ground_truth.json`.
    """
    point = float(per_record_effect["value"]) * overlap_n  # type: ignore[arg-type]
    ci = (
        float(per_record_effect["ci_low"]) * overlap_n,  # type: ignore[arg-type]
        float(per_record_effect["ci_high"]) * overlap_n,  # type: ignore[arg-type]
    )
    return point, ci


def main() -> None:
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION_REPORT_PATH.read_text(encoding="utf-8"))
    candidates_payload = json.loads(
        Path(validation["candidates_source"]).read_text(encoding="utf-8")
    )

    frame = load_analytical_frame(DATASET_ROOT)
    booking_ids = frame["booking_id"].to_list()

    patterns_by_id = {p["id"]: p for p in ground_truth["patterns"]}
    scoreable_total_impact = sum(
        patterns_by_id[pid]["true_effect"]["realized_economic_impact"]
        for pid in SCOREABLE_PATTERN_IDS
    )

    report_by_id = {c["candidate_id"]: c for c in validation["candidates"]}
    raw_by_id = {c["candidate_id"]: c for c in candidates_payload["candidates"]}

    scores: list[CandidateScore] = []
    exposed_ids_by_candidate: dict[str, frozenset[str]] = {}
    for candidate_id, raw in raw_by_id.items():
        conditions = [_condition_from_dict(c) for c in raw["conditions"]]
        mask = frame.select(rule_expr(conditions).alias("m"))["m"].to_list()
        exposed_ids = frozenset(
            bid for bid, exposed in zip(booking_ids, mask, strict=True) if exposed
        )
        exposed_ids_by_candidate[candidate_id] = exposed_ids

        recalls: dict[str, float] = {}
        for pid, pattern in patterns_by_id.items():
            affected = frozenset(pattern["affected_booking_ids"])
            recalls[pid] = len(exposed_ids & affected) / len(affected) if affected else 0.0
        matched = sorted(pid for pid, r in recalls.items() if r >= MATCH_RECALL_THRESHOLD)
        best_recall = max(recalls.values()) if recalls else 0.0

        matched_traps = _matches_trap(raw["conditions"])
        report = report_by_id[candidate_id]["validation_report"]

        scores.append(
            CandidateScore(
                candidate_id=candidate_id,
                pattern_definition=report["pattern_definition"],
                economic_exposure_reported=raw["economic_exposure"],
                evidence_level=report["evidence_level"],
                policy_readiness=report["policy_readiness"],
                exposed_n_full_cohort=len(exposed_ids),
                matched_patterns=matched,
                best_pattern_recall=best_recall,
                matched_traps=matched_traps,
                is_true_pattern=bool(matched) and not matched_traps,
                is_trap=bool(matched_traps),
                is_noise=not matched and not matched_traps,
            )
        )

    # --- Metric 1: Top-K precision --------------------------------------------------------------
    ranked = sorted(scores, key=lambda s: (-s.economic_exposure_reported, s.candidate_id))
    top_k = ranked[:TOP_K]
    top_k_true_pattern_count = sum(1 for s in top_k if s.is_true_pattern)
    top_k_precision = top_k_true_pattern_count / len(top_k) if top_k else 0.0

    # --- Metric 2: economic-weighted recall -------------------------------------------------------
    recovered_scoreable_patterns = {
        pid
        for s in scores
        if s.evidence_level in VALIDATED_LEVELS and not s.is_trap
        for pid in s.matched_patterns
        if pid in SCOREABLE_PATTERN_IDS
    }
    recovered_impact = sum(
        patterns_by_id[pid]["true_effect"]["realized_economic_impact"]
        for pid in recovered_scoreable_patterns
    )
    economic_weighted_recall = (
        recovered_impact / scoreable_total_impact if scoreable_total_impact else 0.0
    )

    # --- Metric 3: confounder trap rejection ------------------------------------------------------
    trap_promoted = {
        trap_id: any(
            trap_id in s.matched_traps and s.policy_readiness in PROMOTED_READINESS for s in scores
        )
        for trap_id in TRAP_APPARENT_CONDITIONS
    }
    trap_appeared_as_candidate = {
        trap_id: any(trap_id in s.matched_traps for s in scores)
        for trap_id in TRAP_APPARENT_CONDITIONS
    }
    any_trap_promoted = any(trap_promoted.values())

    # --- Metric 4: leakage violations ------------------------------------------------------------
    leakage_violations = sum(
        1
        for c in report_by_id.values()
        for g in c["validation_report"]["gate_results"]
        if g["gate_id"] == "G01_TARGET_LEAKAGE" and g["outcome"] == "fail"
    )

    # --- Metric 5: effect direction accuracy (validated findings only) ----------------------------
    validated_matched = [
        s for s in scores if s.evidence_level in VALIDATED_LEVELS and s.matched_patterns
    ]
    direction_results: list[dict[str, object]] = []
    for s in validated_matched:
        raw_effect = raw_by_id[s.candidate_id]["raw_effect"]
        # Every scoreable pattern here is decrease_is_harm; candidate raw_effect < 0 means the
        # exposed group's contribution margin is lower -> harmful -> direction-correct.
        candidate_harmful = raw_effect < 0
        true_directions = {
            patterns_by_id[pid]["true_effect"]["direction"] for pid in s.matched_patterns
        }
        expected_harmful = true_directions == {"decrease_is_harm"}
        direction_results.append(
            {
                "candidate_id": s.candidate_id,
                "matched_patterns": s.matched_patterns,
                "candidate_effect_harmful": candidate_harmful,
                "ground_truth_harmful": expected_harmful,
                "direction_correct": candidate_harmful == expected_harmful,
            }
        )
    direction_correct_count = sum(1 for r in direction_results if r["direction_correct"])
    direction_accuracy = (
        direction_correct_count / len(direction_results) if direction_results else None
    )

    # --- Metric 6: economic impact estimation error (validated, matched findings only) ------------
    impact_errors: list[dict[str, object]] = []
    relative_errors: list[float] = []
    for s in validated_matched:
        reported = report_by_id[s.candidate_id]["diagnostics"]["historical_exposure_ci_eur"]
        reported_point = (float(reported[0]) + float(reported[1])) / 2  # midpoint of the 95% CI
        truth_impact = float(
            sum(
                patterns_by_id[pid]["true_effect"]["realized_economic_impact"]
                for pid in s.matched_patterns
            )
        )
        relative_error = abs(reported_point - truth_impact) / truth_impact if truth_impact else None
        if relative_error is not None:
            relative_errors.append(relative_error)
        impact_errors.append(
            {
                "candidate_id": s.candidate_id,
                "matched_patterns": s.matched_patterns,
                "reported_exposure_ci_midpoint_eur": reported_point,
                "matched_ground_truth_impact_eur": truth_impact,
                "relative_error": relative_error,
            }
        )
    sorted_errors = sorted(relative_errors)
    median_impact_error: float | None = None
    if sorted_errors:
        midpoint = len(sorted_errors) // 2
        median_impact_error = (
            sorted_errors[midpoint]
            if len(sorted_errors) % 2 == 1
            else (sorted_errors[midpoint - 1] + sorted_errors[midpoint]) / 2
        )

    # --- Diagnostic (TASK-059, benchmark-evaluation-only, does not govern the decision gate):
    # attribution-narrowed economic impact error. Same matched-candidate population as metric 6,
    # but the reported side uses only the bookings a candidate's exposed set shares with its
    # matched pattern's affected_booking_ids, scaled by the candidate's own reported per-record
    # effect — the same linear scaling `economic_impact.py` already uses for
    # `historical_impact = per_record_effect x affected_records`, just over a narrower population.
    # Only possible here, against hidden_ground_truth.json; no analog exists for a real finding.
    attribution_details: list[dict[str, object]] = []
    attribution_relative_errors: list[float] = []
    for s in validated_matched:
        economic_impact = report_by_id[s.candidate_id].get("economic_impact")
        if economic_impact is None:
            attribution_details.append(
                {
                    "candidate_id": s.candidate_id,
                    "skipped_reason": (
                        "validation report has no economic_impact field (pre-HANDOFF-025 "
                        "artifact) - cannot compute a per-record-effect-scaled narrowed estimate"
                    ),
                }
            )
            continue
        overlap_ids = _attribution_overlap_ids(
            exposed_ids_by_candidate[s.candidate_id], s.matched_patterns, patterns_by_id
        )
        overlap_n = len(overlap_ids)
        per_record = economic_impact["per_record_effect"]
        narrowed_point, narrowed_ci = _attribution_narrowed_impact(per_record, overlap_n)
        truth_impact = float(
            sum(
                patterns_by_id[pid]["true_effect"]["realized_economic_impact"]
                for pid in s.matched_patterns
            )
        )
        narrowed_relative_error = (
            abs(narrowed_point - truth_impact) / truth_impact if truth_impact else None
        )
        if narrowed_relative_error is not None:
            attribution_relative_errors.append(narrowed_relative_error)
        attribution_details.append(
            {
                "candidate_id": s.candidate_id,
                "matched_patterns": s.matched_patterns,
                "attribution_narrowed_n": overlap_n,
                "exposed_n_full_cohort": s.exposed_n_full_cohort,
                "per_record_effect_eur": per_record["value"],
                "attribution_narrowed_impact_point_eur": narrowed_point,
                "attribution_narrowed_impact_ci_eur": list(narrowed_ci),
                "matched_ground_truth_impact_eur": truth_impact,
                "relative_error": narrowed_relative_error,
            }
        )
    sorted_attribution_errors = sorted(attribution_relative_errors)
    median_attribution_narrowed_error: float | None = None
    if sorted_attribution_errors:
        midpoint = len(sorted_attribution_errors) // 2
        median_attribution_narrowed_error = (
            sorted_attribution_errors[midpoint]
            if len(sorted_attribution_errors) % 2 == 1
            else (sorted_attribution_errors[midpoint - 1] + sorted_attribution_errors[midpoint]) / 2
        )

    payload = {
        "status": "FROZEN",
        "frozen_at": datetime.now(UTC).isoformat(),
        "task": "TASK-028",
        "methodology": {
            "match_recall_threshold": MATCH_RECALL_THRESHOLD,
            "top_k": TOP_K,
            "scoreable_pattern_ids": list(SCOREABLE_PATTERN_IDS),
            "ranking_signal_for_top_k": (
                "economic_exposure (as reported by TASK-015), descending — TASK-016 candidate "
                "ranking has not run; this is a documented substitution, not TASK-016's output"
            ),
            "attribution_narrowed_diagnostic": (
                "TASK-059 (HANDOFF-043 remediation part 1): "
                "metrics.economic_impact_estimation_error_attribution_narrowed_diagnostic is a "
                "benchmark-evaluation-only sibling of metric 6, computed only because "
                "hidden_ground_truth.json's affected_booking_ids are available here. It does NOT "
                "govern docs/benchmark/decision-gate.md and must not replace "
                "metrics.economic_impact_estimation_error when reading that document's bands."
            ),
        },
        "inputs": {
            "validation_report": str(VALIDATION_REPORT_PATH.relative_to(REPOSITORY)),
            "candidates_source": validation["candidates_source"],
            "ground_truth_sha256_expected": (
                "5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506"
            ),
        },
        "candidate_scores": [asdict(s) for s in scores],
        "metrics": {
            "top_k_precision": {
                "value": top_k_precision,
                "true_pattern_count": top_k_true_pattern_count,
                "k": len(top_k),
                "top_k_candidate_ids": [s.candidate_id for s in top_k],
            },
            "economic_weighted_recall": {
                "value": economic_weighted_recall,
                "recovered_scoreable_patterns": sorted(recovered_scoreable_patterns),
                "recovered_impact_eur": recovered_impact,
                "scoreable_total_impact_eur": scoreable_total_impact,
            },
            "confounder_trap_rejection": {
                "any_trap_promoted": any_trap_promoted,
                "trap_promoted": trap_promoted,
                "trap_appeared_as_candidate": trap_appeared_as_candidate,
                "note": (
                    "No trap's apparent_feature appears as a literal condition in any of the 15 "
                    "persisted candidates, so no trap was promoted — but this is non-promotion by "
                    "absence, not active rejection of a trap-shaped candidate by gate G06. All "
                    "PASS candidates did independently clear G06 (manager x supplier stratified "
                    "adjustment) as part of TASK-019, which is the closest active analog."
                ),
            },
            "leakage_violations": {"value": leakage_violations},
            "effect_direction_accuracy": {
                "value": direction_accuracy,
                "correct": direction_correct_count,
                "total": len(direction_results),
                "details": direction_results,
            },
            "economic_impact_estimation_error": {
                "median_relative_error": median_impact_error,
                "details": impact_errors,
            },
            "economic_impact_estimation_error_attribution_narrowed_diagnostic": {
                "note": (
                    "DIAGNOSTIC ONLY - does not govern docs/benchmark/decision-gate.md. See "
                    "methodology.attribution_narrowed_diagnostic and TASK-059/HANDOFF-043."
                ),
                "median_relative_error": median_attribution_narrowed_error,
                "details": attribution_details,
            },
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPOSITORY)}")
    print(f"Top-{TOP_K} precision: {top_k_precision:.0%} ({top_k_true_pattern_count}/{len(top_k)})")
    print(f"Economic-weighted recall: {economic_weighted_recall:.1%}")
    print(f"Any trap promoted: {any_trap_promoted}")
    print(f"Leakage violations: {leakage_violations}")
    print(f"Direction accuracy: {direction_accuracy}")
    print(f"Median impact error (whole-rule, governs decision-gate): {median_impact_error}")
    print(
        "Median impact error (attribution-narrowed, DIAGNOSTIC ONLY, TASK-059): "
        f"{median_attribution_narrowed_error}"
    )


if __name__ == "__main__":
    main()
