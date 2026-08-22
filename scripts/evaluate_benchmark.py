"""CLI: score a frozen TASK-019 validation report against hidden ground truth (TASK-028).

Opens a `hidden_ground_truth.json` (`--ground-truth`, default: the travel benchmark's) — legitimate
only because this runs strictly after candidate commitment and validation are already frozen (the
blind boundary this protects is upstream, at discovery and validation time, not here). `--dataset-
root`/`--ground-truth` (mirroring `--validation-report`/`--output`, `ADR-025`) let this evaluator
run against any domain's own analytical dataset and ground truth instead of hardcoding travel's —
purely an input-source change; the matching statistic and all six metrics below are untouched.
Computes the six metrics
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

**`HANDOFF-065` (domain-neutral trap/pattern mapping, `TASK-028` half):** the historical
`TRAP_APPARENT_CONDITIONS`/`SCOREABLE_PATTERN_IDS` module constants were travel-hardcoded — a
literal `{feature: (feature, "eq", value)}` dict transcribed by hand from travel's own
`hidden_ground_truth.json`, and a literal 7-of-9 pattern-id tuple. Both are now computed from
whichever `ground_truth`/`frame` `--ground-truth`/`--dataset-root` point at, at run time:
`_trap_apparent_conditions` parses every `confounding_traps[].apparent_feature` string generically
(`"col=value"`, with `"true"`/`"false"` string coercion to `bool` — the same coercion travel's own
five trap entries already needed by hand); `_scoreable_pattern_ids` reimplements this file's own
`§"Fixed denominators"` rule generically (`affected_n >= ValidationThresholds.min_exposed_records`
*and* the pattern has at least one affected record in the `development` split) instead of a frozen
travel-specific tuple. Both were checked to reproduce travel's exact historical values byte-for-byte
before replacing the constants (`tests/analytics/test_evaluate_benchmark.py`). Two more small
generalizations ride along, needed for the same reason: the record-id column is read from
`manifest.json`'s own `partitions.identifiers.columns[0]` instead of a hardcoded `"booking_id"`
literal, and each pattern's affected-id list is located by key pattern (`affected_.*_ids`) since
travel's own key (`affected_booking_ids`) and every `TASK-061` domain's key (`affected_record_ids`)
differ.

**`TASK-059` addition (`HANDOFF-043` remediation part 1):** metric 6's governing number
(`metrics.economic_impact_estimation_error`) is unchanged — it still compares each matched
candidate's *whole-rule* reported historical impact against the matched pattern(s)' true impact,
exactly as `docs/benchmark/decision-gate.md` pre-registered it. A second, clearly-separate,
diagnostic-only sibling metric
(`metrics.economic_impact_estimation_error_attribution_narrowed_diagnostic`) is added alongside it:
same matched-candidate population, but the reported side is recomputed over just the booking IDs a
candidate's exposed set shares with its matched pattern's affected-record-id set (only knowable
here, against `hidden_ground_truth.json`, never for a real customer finding — `HANDOFF-043`, ML
Discovery dissent). **This diagnostic does not govern the decision gate and must not be substituted
for `economic_impact_estimation_error` when reading `docs/benchmark/decision-gate.md`'s bands** —
it exists to show how much of the whole-rule error is attributable to population dilution
(`task-029-benchmark-report-v1.md` §3.6) versus genuine per-booking effect misestimation, and, per
`HANDOFF-043`'s own warning, is not by itself sufficient grounds for a re-grade without `TASK-058`
(tighter candidates at search time) as well.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.validation.apply import (  # noqa: E402
    Condition,
    load_analytical_frame,
    rule_expr,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS  # noqa: E402

#: Defaults reproduce the historical travel-benchmark run exactly — `--dataset-root`/
#: `--ground-truth` (mirroring `--validation-report`/`--output`, `ADR-025`) let this evaluator run
#: against any other domain's analytical dataset and ground truth (e.g. a `TASK-061` domain, once
#: it has a discovery run of its own to score) without editing this file. The metric logic itself
#: (matching, the six metrics, the diagnostic) is untouched by this parameterization.
DEFAULT_DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
DEFAULT_GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
DEFAULT_VALIDATION_REPORT_PATH = (
    REPOSITORY / "artifacts/validation/task-019-official-20260816-015.json"
)
DEFAULT_OUTPUT_PATH = REPOSITORY / "artifacts/evaluation/task-028-benchmark-evaluation.json"

MATCH_RECALL_THRESHOLD = 0.5
TOP_K = 10
VALIDATED_LEVELS = (
    "predictive_association",
    "adjusted_observational_association",
    "quasi_causal_evidence",
    "experimental_evidence",
)
PROMOTED_READINESS = ("shadow_policy", "high_confidence")

#: `SCOREABLE_PATTERN_IDS`/`TRAP_APPARENT_CONDITIONS` used to be frozen, hand-transcribed travel
#: constants here. `HANDOFF-065` replaced both with `_scoreable_pattern_ids`/
#: `_trap_apparent_conditions` below, computed from whichever `ground_truth`/`frame` this run is
#: actually pointed at — see the module docstring's `HANDOFF-065` paragraph.
_AFFECTED_IDS_KEY = re.compile(r"^affected_.*_ids$")


def _record_id_column(manifest: dict[str, Any]) -> str:
    """The dataset's own per-record identifier column — always the first column of
    `manifest.json`'s `partitions.identifiers`
    (`policy_analytics.analytical_dataset.build_analytical_dataset`, `TASK-062`), never assumed.
    """
    return str(manifest["partitions"]["identifiers"]["columns"][0])


def _primary_outcome_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    contract = manifest.get("outcome_contract")
    if not isinstance(contract, dict):
        raise ValueError("analytical manifest has no outcome_contract")
    typed_contract = cast(dict[str, object], contract)
    primary_id = typed_contract.get("primary_outcome_id")
    definitions = typed_contract.get("definitions")
    if not isinstance(primary_id, str) or not isinstance(definitions, list):
        raise ValueError("analytical manifest has an invalid outcome_contract")
    matches: list[dict[str, Any]] = []
    for raw_definition in cast(list[object], definitions):
        if not isinstance(raw_definition, dict):
            continue
        definition = cast(dict[str, Any], raw_definition)
        if definition.get("outcome_id") == primary_id:
            matches.append(definition)
    if len(matches) != 1:
        raise ValueError("analytical manifest primary outcome is not uniquely defined")
    return matches[0]


def _verify_evaluation_lineage(
    manifest: dict[str, Any], validation: dict[str, Any], candidates: dict[str, Any]
) -> None:
    """Fail closed unless the frozen public artifacts belong to one lineage."""
    expected = {
        "dataset_version": manifest.get("dataset_version"),
        "dataset_identity_sha256": manifest.get("dataset_identity_sha256"),
        "outcome_contract_version": manifest.get("outcome_contract", {}).get("version"),
    }
    for field, value in expected.items():
        if validation.get(field) != value:
            raise ValueError(f"validation {field} does not match analytical manifest")
        if candidates.get(field) != value:
            raise ValueError(f"candidate {field} does not match analytical manifest")
    if validation.get("candidates_source") is None:
        raise ValueError("validation report does not identify its candidate source")
    validation_ids = [item.get("candidate_id") for item in validation.get("candidates", [])]
    candidate_ids = [item.get("candidate_id") for item in candidates.get("candidates", [])]
    if validation_ids != candidate_ids or len(validation_ids) != len(set(validation_ids)):
        raise ValueError("validation and candidate families do not match exactly")


def _affected_ids(pattern: dict[str, object]) -> frozenset[str]:
    """A ground-truth pattern's affected-record-id set, whatever its key is named — travel calls it
    `affected_booking_ids`; every `TASK-061` domain calls it `affected_record_ids`. Locating it by
    shape (`affected_*_ids`, exactly one match) instead of hardcoding either name is what lets this
    generalize without special-casing travel.
    """
    keys = [key for key in pattern if _AFFECTED_IDS_KEY.match(key)]
    if len(keys) != 1:
        raise ValueError(
            f"pattern {pattern.get('id')!r} has {len(keys)} keys matching affected_*_ids "
            f"(expected exactly 1): {keys}"
        )
    return frozenset(pattern[keys[0]])  # type: ignore[arg-type]


def _scoreable_pattern_ids(
    ground_truth: dict[str, object], development_split_ids: frozenset[str]
) -> tuple[str, ...]:
    """Generalizes this file's own preregistered `§"Fixed denominators"` rule (originally computed
    by hand once, for travel, as the frozen 7-of-9 `SCOREABLE_PATTERN_IDS` tuple):
    a pattern is scoreable for recall purposes iff it clears the power floor
    (`ValidationThresholds.min_exposed_records`, matching travel's stated reason for excluding P05,
    n=23) *and* has at least one affected record in the `development` split (matching travel's
    stated reason for excluding P07, which has zero — recall can only be computed against candidates
    fit on the development split). Verified to reproduce travel's exact historical
    `{P01,P02,P03,P04,P06,P08,P09}` before replacing the frozen tuple
    (`tests/analytics/test_evaluate_benchmark.py`).
    """
    scoreable: list[str] = []
    for pattern in ground_truth["patterns"]:  # type: ignore[union-attr]
        affected = _affected_ids(pattern)  # type: ignore[arg-type]
        if (
            len(affected) >= DEFAULT_THRESHOLDS.min_exposed_records
            and len(affected & development_split_ids) > 0
        ):
            scoreable.append(str(pattern["id"]))  # type: ignore[index]
    return tuple(sorted(scoreable))


def _parse_apparent_feature(raw: str) -> tuple[str, str, object]:
    """`"col=value"` -> `(col, "eq", value)`, coercing the literal strings `"true"`/`"false"` to
    `bool` (the only coercion travel's own five `confounding_traps` entries ever needed — T05's
    `manual_exception=true`). Verified to reproduce travel's exact historical
    `TRAP_APPARENT_CONDITIONS` dict before replacing it
    (`tests/analytics/test_evaluate_benchmark.py`).
    """
    feature, _, value = raw.partition("=")
    coerced: object = value
    if value == "true":
        coerced = True
    elif value == "false":
        coerced = False
    return (feature, "eq", coerced)


def _trap_apparent_conditions(
    ground_truth: dict[str, object],
) -> dict[str, tuple[str, str, object]]:
    return {
        str(trap["id"]): _parse_apparent_feature(str(trap["apparent_feature"]))  # type: ignore[index]
        for trap in ground_truth["confounding_traps"]  # type: ignore[union-attr]
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


def _display_path(path: Path) -> str:
    """Repo-relative when possible (matches every other path already written into this payload);
    falls back to the absolute path for a `--dataset-root`/`--ground-truth` value that lives
    outside the repository rather than raising.
    """
    try:
        return str(path.relative_to(REPOSITORY))
    except ValueError:
        return str(path)


def _matches_trap(
    conditions: list[dict[str, object]],
    trap_apparent_conditions: dict[str, tuple[str, str, object]],
) -> list[str]:
    condition_set = {(c["feature"], c["operator"], c["value"]) for c in conditions}
    return [
        trap_id
        for trap_id, apparent in trap_apparent_conditions.items()
        if apparent in condition_set
    ]


def _trap_rejection_note(
    scores: list[CandidateScore], trap_appeared: dict[str, bool], historical_travel: bool
) -> str:
    if historical_travel:
        return (
            "No trap's apparent_feature appears as a literal condition in any of the 15 persisted "
            "candidates, so no trap was promoted — but this is non-promotion by absence, not "
            "active "
            "rejection of a trap-shaped candidate by gate G06. All PASS candidates did "
            "independently clear G06 (manager x supplier stratified adjustment) as part of "
            "TASK-019, which is the closest active analog."
        )
    if not any(trap_appeared.values()):
        prefix = (
            "No trap's apparent_feature appears as a literal condition in any of the "
            f"{len(scores)} "
            "persisted candidates, so no trap was promoted — this is non-promotion by absence, "
            "not active rejection of a trap-shaped candidate by gate G06."
        )
    else:
        prefix = (
            "At least one trap's apparent_feature appeared as a literal condition in a persisted "
            "candidate — see trap_appeared_as_candidate/trap_promoted for whether a gate kept it "
            "from reaching promoted policy_readiness."
        )
    return prefix + (
        " G06 uses the manifest-bound, coverage-gated adjustment set outside the candidate's own "
        "conditions (validation contract >= 1.2.0, ADR-036/ADR-042/TASK-063)."
    )


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
        overlap |= exposed_ids & _affected_ids(patterns_by_id[pid])
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "CLI: score a frozen TASK-019 validation report against hidden ground truth (TASK-028)."
        )
    )
    parser.add_argument(
        "--validation-report",
        type=Path,
        default=DEFAULT_VALIDATION_REPORT_PATH,
        help="frozen TASK-019 output to score (default: the historical task-015 official run)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="where to write the frozen TASK-028 evaluation report",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help="analytical dataset root to re-evaluate candidate conditions against "
        "(default: the travel benchmark)",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=DEFAULT_GROUND_TRUTH_PATH,
        help="hidden_ground_truth.json to score against (default: the travel benchmark's)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow overwriting an existing output file",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    validation_report_path: Path = args.validation_report.resolve()
    output_path: Path = args.output.resolve()
    dataset_root: Path = args.dataset_root.resolve()
    ground_truth_path: Path = args.ground_truth.resolve()
    historical_travel_regression = (
        validation_report_path == DEFAULT_VALIDATION_REPORT_PATH.resolve()
        and dataset_root == DEFAULT_DATASET_ROOT.resolve()
        and ground_truth_path == DEFAULT_GROUND_TRUTH_PATH.resolve()
    )
    if output_path.exists() and not args.force:
        raise SystemExit(
            f"{output_path} already exists and is a frozen result. Refusing to overwrite it. "
            "Point --output at a new file, or pass --force with a clear reason recorded in "
            "TASKS.md/HANDOFFS.md — do not use --force to silently regrade the same result."
        )

    ground_truth_bytes = ground_truth_path.read_bytes()
    ground_truth = json.loads(ground_truth_bytes)
    validation = json.loads(validation_report_path.read_text(encoding="utf-8"))
    candidates_payload = json.loads(
        Path(validation["candidates_source"]).read_text(encoding="utf-8")
    )
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    _verify_evaluation_lineage(manifest, validation, candidates_payload)
    outcome_metadata = _primary_outcome_metadata(manifest)
    higher_is_worse = bool(outcome_metadata["higher_is_worse"])
    outcome_unit = str(outcome_metadata["unit"])

    record_id_column = _record_id_column(manifest)
    frame = load_analytical_frame(dataset_root)
    booking_ids = frame[record_id_column].to_list()
    development_split_ids = frozenset(
        frame.filter(frame["split_label"] == "development")[record_id_column].to_list()  # pyright: ignore[reportUnknownMemberType]
    )

    patterns_by_id = {p["id"]: p for p in ground_truth["patterns"]}
    scoreable_pattern_ids = _scoreable_pattern_ids(ground_truth, development_split_ids)
    trap_apparent_conditions = _trap_apparent_conditions(ground_truth)
    scoreable_total_impact = sum(
        patterns_by_id[pid]["true_effect"]["realized_economic_impact"]
        for pid in scoreable_pattern_ids
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
            affected = _affected_ids(pattern)
            recalls[pid] = len(exposed_ids & affected) / len(affected) if affected else 0.0
        matched = sorted(pid for pid, r in recalls.items() if r >= MATCH_RECALL_THRESHOLD)
        best_recall = max(recalls.values()) if recalls else 0.0

        matched_traps = _matches_trap(raw["conditions"], trap_apparent_conditions)
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
        if pid in scoreable_pattern_ids
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
        for trap_id in trap_apparent_conditions
    }
    trap_appeared_as_candidate = {
        trap_id: any(trap_id in s.matched_traps for s in scores)
        for trap_id in trap_apparent_conditions
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
        candidate_harmful = (raw_effect > 0) if higher_is_worse else (raw_effect < 0)
        true_directions = {
            patterns_by_id[pid]["true_effect"]["direction"] for pid in s.matched_patterns
        }
        unsupported_directions = true_directions - {"increase_is_harm", "decrease_is_harm"}
        if unsupported_directions:
            raise ValueError(
                f"unsupported ground-truth effect directions: {unsupported_directions}"
            )
        expected_raw_signs = {
            1 if direction == "increase_is_harm" else -1 for direction in true_directions
        }
        raw_sign = 1 if raw_effect > 0 else -1 if raw_effect < 0 else 0
        direction_correct = expected_raw_signs == {raw_sign}
        direction_results.append(
            {
                "candidate_id": s.candidate_id,
                "matched_patterns": s.matched_patterns,
                "candidate_effect_harmful": candidate_harmful,
                "ground_truth_harmful": True,
                "direction_correct": direction_correct,
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
        raw_economic_impact = report_by_id[s.candidate_id].get("economic_impact")
        if not isinstance(raw_economic_impact, dict):
            raise ValueError(f"candidate {s.candidate_id} has no bound economic impact")
        historical_impact = cast(dict[str, object], raw_economic_impact).get("historical_impact")
        if not isinstance(historical_impact, dict):
            raise ValueError(f"candidate {s.candidate_id} has no bound historical impact")
        typed_impact = cast(dict[str, object], historical_impact)
        if typed_impact.get("unit") != outcome_unit:
            raise ValueError(f"candidate {s.candidate_id} historical-impact unit mismatch")
        ci_low, ci_high = typed_impact.get("ci_low"), typed_impact.get("ci_high")
        if not isinstance(ci_low, int | float) or not isinstance(ci_high, int | float):
            raise ValueError(f"candidate {s.candidate_id} historical-impact CI is invalid")
        reported_point = (float(ci_low) + float(ci_high)) / 2  # midpoint of the 95% CI
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
    # matched pattern's affected-record-id set, scaled by the candidate's own reported per-record
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
            "scoreable_pattern_ids": list(scoreable_pattern_ids),
            "ranking_signal_for_top_k": (
                "economic_exposure (as reported by TASK-015), descending — TASK-016 candidate "
                "ranking has not run; this is a documented substitution, not TASK-016's output"
            ),
            "attribution_narrowed_diagnostic": (
                "TASK-059 (HANDOFF-043 remediation part 1): "
                "metrics.economic_impact_estimation_error_attribution_narrowed_diagnostic is a "
                "benchmark-evaluation-only sibling of metric 6, computed only because "
                "hidden_ground_truth.json's affected-record-id sets are available here. It does "
                "NOT govern docs/benchmark/decision-gate.md and must not replace "
                "metrics.economic_impact_estimation_error when reading that document's bands."
            ),
        },
        "inputs": {
            "validation_report": _display_path(validation_report_path),
            "candidates_source": validation["candidates_source"],
            "dataset_root": _display_path(dataset_root),
            "ground_truth": _display_path(ground_truth_path),
            "ground_truth_sha256": hashlib.sha256(ground_truth_bytes).hexdigest(),
            "dataset_version": manifest["dataset_version"],
            "dataset_identity_sha256": manifest["dataset_identity_sha256"],
            "outcome_contract_version": manifest["outcome_contract"]["version"],
            "outcome_id": outcome_metadata["outcome_id"],
            "outcome_unit": outcome_unit,
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
                "note": _trap_rejection_note(
                    scores, trap_appeared_as_candidate, historical_travel_regression
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {_display_path(output_path)}")
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
