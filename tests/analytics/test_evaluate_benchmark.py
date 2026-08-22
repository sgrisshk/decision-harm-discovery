"""Tests for the TASK-028 benchmark evaluator's pure scoring logic.

Does not open `hidden_ground_truth.json` for anything beyond what the real evaluator run already
did (these are unit tests of the matching/parsing helpers on synthetic fixtures, not a re-run of
the scoring itself).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl
import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from evaluate_benchmark import (  # noqa: E402
    DEFAULT_DATASET_ROOT,
    DEFAULT_GROUND_TRUTH_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_VALIDATION_REPORT_PATH,
    MATCH_RECALL_THRESHOLD,
    _affected_ids,
    _attribution_narrowed_impact,
    _attribution_overlap_ids,
    _condition_from_dict,
    _display_path,
    _matches_trap,
    _parse_apparent_feature,
    _record_id_column,
    _scoreable_pattern_ids,
    _trap_apparent_conditions,
    _verify_evaluation_lineage,
    main,
    parse_args,
)

#: Travel's real, historical trap-condition dict, for tests that used to check against the module-
#: level `TRAP_APPARENT_CONDITIONS` constant (removed, `HANDOFF-065`) — now computed at run time by
#: `_trap_apparent_conditions`, so tests exercising `_matches_trap` build this fixture explicitly
#: instead of relying on module state.
_TRAVEL_TRAP_CONDITIONS: dict[str, tuple[str, str, object]] = {
    "T01": ("manager", "eq", "Manager 2"),
    "T02": ("supplier", "eq", "Atlas"),
    "T03": ("acquisition_channel", "eq", "paid_search"),
    "T04": ("payment_method", "eq", "bank_transfer"),
    "T05": ("manual_exception", "eq", True),
}

pytestmark = pytest.mark.analytics


def test_condition_from_dict_round_trips_fields() -> None:
    condition = _condition_from_dict({"feature": "discount_rate", "operator": "ge", "value": 0.12})
    assert condition.feature == "discount_rate"
    assert condition.operator == "ge"
    assert condition.value == 0.12


def test_matches_trap_detects_an_exact_apparent_condition() -> None:
    conditions = [
        {"feature": "manager", "operator": "eq", "value": "Manager 2"},
        {"feature": "discount_rate", "operator": "ge", "value": 0.1},
    ]
    assert _matches_trap(conditions, _TRAVEL_TRAP_CONDITIONS) == ["T01"]


def test_matches_trap_does_not_fire_on_the_opposite_polarity() -> None:
    # T05 is manual_exception == True; a candidate requiring manual_exception == False is a
    # different, non-trap condition and must not be flagged.
    conditions = [{"feature": "manual_exception", "operator": "eq", "value": False}]
    assert _matches_trap(conditions, _TRAVEL_TRAP_CONDITIONS) == []


def test_matches_trap_returns_empty_for_unrelated_conditions() -> None:
    conditions = [
        {"feature": "discount_rate", "operator": "ge", "value": 0.12},
        {"feature": "booking_lead_days", "operator": "lt", "value": 21},
    ]
    assert _matches_trap(conditions, _TRAVEL_TRAP_CONDITIONS) == []


def test_matches_trap_can_detect_multiple_traps_at_once() -> None:
    conditions = [
        {"feature": "manager", "operator": "eq", "value": "Manager 2"},
        {"feature": "supplier", "operator": "eq", "value": "Atlas"},
    ]
    assert sorted(_matches_trap(conditions, _TRAVEL_TRAP_CONDITIONS)) == ["T01", "T02"]


def test_matches_trap_works_against_non_travel_shaped_trap_ids() -> None:
    # HANDOFF-065: proves _matches_trap itself never assumed "T0N"-shaped ids — any trap_id string
    # a ground truth actually uses is matched the same way. Fictional feature/trap-id fixture
    # (deliberately not any real TASK-061 domain's actual trap identity — see ADR-048).
    conditions = [{"feature": "warehouse_zone", "operator": "eq", "value": "Zone 9"}]
    fictional_trap_conditions = {"XT01": ("warehouse_zone", "eq", "Zone 9")}
    assert _matches_trap(conditions, fictional_trap_conditions) == ["XT01"]


# --- HANDOFF-065: domain-neutral trap/pattern computation (TASK-028 half) ------------------------


def test_parse_apparent_feature_splits_on_the_first_equals_sign() -> None:
    assert _parse_apparent_feature("manager=Manager 2") == ("manager", "eq", "Manager 2")


def test_parse_apparent_feature_coerces_true_and_false_literals_to_bool() -> None:
    assert _parse_apparent_feature("manual_exception=true") == ("manual_exception", "eq", True)
    assert _parse_apparent_feature("expedited_shipping=false") == (
        "expedited_shipping",
        "eq",
        False,
    )


def test_trap_apparent_conditions_reproduces_travels_real_historical_dict() -> None:
    ground_truth = json.loads(
        (REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json").read_text(
            encoding="utf-8"
        )
    )
    assert _trap_apparent_conditions(ground_truth) == _TRAVEL_TRAP_CONDITIONS


def test_trap_apparent_conditions_does_not_silently_discard_non_travel_trap_ids() -> None:
    # A fully synthetic, in-memory ground truth (never any real TASK-061 domain's actual trap
    # identity — see ADR-048) shaped like a non-travel domain's confounding_traps block: non-"T0N"
    # trap ids, a boolean-valued apparent_feature.
    ground_truth = {
        "confounding_traps": [
            {"id": "XT01", "apparent_feature": "warehouse_zone=Zone 9"},
            {"id": "XT02", "apparent_feature": "expedited_shipping=true"},
        ]
    }
    computed = _trap_apparent_conditions(ground_truth)
    assert set(computed) == {"XT01", "XT02"}
    assert computed["XT02"] == ("expedited_shipping", "eq", True)


def test_affected_ids_locates_the_key_regardless_of_its_exact_name() -> None:
    assert _affected_ids({"id": "P01", "affected_booking_ids": ["b1", "b2"]}) == frozenset(
        {"b1", "b2"}
    )
    assert _affected_ids({"id": "X01", "affected_record_ids": ["rec1"]}) == frozenset({"rec1"})


def test_affected_ids_raises_when_no_key_matches_the_expected_shape() -> None:
    with pytest.raises(ValueError, match="affected_\\*_ids"):
        _affected_ids({"id": "P01", "name": "no ids field here"})


def test_record_id_column_reads_the_first_identifiers_partition_column() -> None:
    manifest = {"partitions": {"identifiers": {"columns": ["record_id", "group_id"]}}}
    assert _record_id_column(manifest) == "record_id"


def test_evaluation_lineage_rejects_cross_dataset_candidates() -> None:
    manifest = {
        "dataset_version": "fixture-v1",
        "dataset_identity_sha256": "a" * 64,
        "outcome_contract": {"version": "outcome-v1"},
    }
    candidates = {
        "dataset_version": "other-v1",
        "dataset_identity_sha256": "a" * 64,
        "outcome_contract_version": "outcome-v1",
        "candidates": [{"candidate_id": "C1"}],
    }
    validation = {
        "dataset_version": "fixture-v1",
        "dataset_identity_sha256": "a" * 64,
        "outcome_contract_version": "outcome-v1",
        "candidates_source": "fixture.json",
        "candidates": [{"candidate_id": "C1"}],
    }
    with pytest.raises(ValueError, match="candidate dataset_version"):
        _verify_evaluation_lineage(manifest, validation, candidates)


def test_evaluation_lineage_rejects_partial_candidate_family() -> None:
    manifest = {
        "dataset_version": "fixture-v1",
        "dataset_identity_sha256": "a" * 64,
        "outcome_contract": {"version": "outcome-v1"},
    }
    common = {
        "dataset_version": "fixture-v1",
        "dataset_identity_sha256": "a" * 64,
        "outcome_contract_version": "outcome-v1",
    }
    validation = {
        **common,
        "candidates_source": "fixture.json",
        "candidates": [{"candidate_id": "C1"}],
    }
    candidates = {**common, "candidates": [{"candidate_id": "C1"}, {"candidate_id": "C2"}]}
    with pytest.raises(ValueError, match="families do not match"):
        _verify_evaluation_lineage(manifest, validation, candidates)


def test_scoreable_pattern_ids_applies_the_power_floor_and_development_overlap_rule() -> None:
    ground_truth = {
        "patterns": [
            {"id": "X01", "affected_record_ids": [f"r{i}" for i in range(60)]},  # clears both
            {"id": "X02", "affected_record_ids": [f"r{i}" for i in range(10)]},  # below power floor
            {"id": "X03", "affected_record_ids": [f"z{i}" for i in range(60)]},  # zero dev overlap
        ]
    }
    development_split_ids = frozenset(f"r{i}" for i in range(60))
    assert _scoreable_pattern_ids(ground_truth, development_split_ids) == ("X01",)


def test_scoreable_pattern_ids_reproduces_travels_real_historical_seven_of_nine() -> None:
    # Cross-check against docs/benchmark/decision-gate.md's own §"Fixed denominators" reasoning:
    # P05 (n=23) excluded for being below the power floor, P07 excluded for zero development-split
    # rows — both now derived, not hand-transcribed.
    ground_truth = json.loads(
        (REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (
            REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/manifest.json"
        ).read_text(encoding="utf-8")
    )
    dataset_root = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
    frame = pl.concat(
        [pl.read_csv(dataset_root / "identifiers.csv"), pl.read_csv(dataset_root / "metadata.csv")],
        how="horizontal",
    )
    record_id_column = _record_id_column(manifest)
    development_split_ids = frozenset(
        frame.filter(frame["split_label"] == "development")[record_id_column].to_list()  # pyright: ignore[reportUnknownMemberType]
    )
    assert _scoreable_pattern_ids(ground_truth, development_split_ids) == (
        "P01",
        "P02",
        "P03",
        "P04",
        "P06",
        "P08",
        "P09",
    )


def test_match_recall_threshold_is_a_majority_bar_fixed_before_scoring() -> None:
    # Documents the preregistered choice (module docstring): 0.5, chosen once, not tuned to results.
    assert MATCH_RECALL_THRESHOLD == 0.5


# --- TASK-059: attribution-narrowed diagnostic helpers (synthetic fixtures only) -----------------


def test_attribution_overlap_ids_is_the_intersection_with_matched_patterns_only() -> None:
    exposed_ids = frozenset({"b1", "b2", "b3", "b4"})
    patterns_by_id = {
        "P01": {"affected_booking_ids": ["b2", "b3", "b9"]},
        "P02": {"affected_booking_ids": ["b4", "b10"]},
        "P03": {"affected_booking_ids": ["b1"]},  # not in matched_patterns -> must not contribute
    }
    overlap = _attribution_overlap_ids(exposed_ids, ["P01", "P02"], patterns_by_id)
    assert overlap == frozenset({"b2", "b3", "b4"})


def test_attribution_overlap_ids_is_empty_when_no_patterns_matched() -> None:
    exposed_ids = frozenset({"b1", "b2"})
    patterns_by_id = {"P01": {"affected_booking_ids": ["b1", "b2"]}}
    assert _attribution_overlap_ids(exposed_ids, [], patterns_by_id) == frozenset()


def test_attribution_narrowed_impact_scales_per_record_effect_by_overlap_n() -> None:
    per_record_effect = {"value": 100.0, "ci_low": 80.0, "ci_high": 130.0}
    point, ci = _attribution_narrowed_impact(per_record_effect, overlap_n=50)
    assert point == pytest.approx(5000.0)
    assert ci == (pytest.approx(4000.0), pytest.approx(6500.0))


def test_attribution_narrowed_impact_is_zero_for_an_empty_overlap() -> None:
    # A candidate can recover a pattern by recall (majority of the pattern's bookings) while still
    # sharing zero bookings with a *different* matched pattern's affected set — must not divide by
    # zero or otherwise error, just report zero narrowed impact for that population.
    per_record_effect = {"value": -42.0, "ci_low": -60.0, "ci_high": -20.0}
    point, ci = _attribution_narrowed_impact(per_record_effect, overlap_n=0)
    assert point == 0.0
    assert ci == (0.0, 0.0)


# --- CLI input-source parameterization (--dataset-root/--ground-truth) ---------------------------
#
# Mirrors --validation-report/--output's existing shape (ADR-025). No test here touches the six
# metrics' own logic — only which files parse_args()/main() read them from.


def test_parse_args_defaults_to_the_travel_benchmark() -> None:
    args = parse_args([])
    assert args.dataset_root == DEFAULT_DATASET_ROOT
    assert args.ground_truth == DEFAULT_GROUND_TRUTH_PATH
    assert args.validation_report == DEFAULT_VALIDATION_REPORT_PATH
    assert args.output == DEFAULT_OUTPUT_PATH
    assert args.force is False


def test_parse_args_accepts_explicit_dataset_root_and_ground_truth() -> None:
    args = parse_args(
        [
            "--dataset-root",
            "synthetic_data_domains/insurance/analytical",
            "--ground-truth",
            "synthetic_data_domains/insurance/evaluation/hidden_ground_truth.json",
        ]
    )
    assert args.dataset_root == Path("synthetic_data_domains/insurance/analytical")
    assert args.ground_truth == Path(
        "synthetic_data_domains/insurance/evaluation/hidden_ground_truth.json"
    )


def test_display_path_is_repo_relative_when_possible() -> None:
    assert _display_path(REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json") == (
        "synthetic_data/evaluation/hidden_ground_truth.json"
    )


def test_display_path_falls_back_to_absolute_outside_the_repository() -> None:
    outside = Path("/tmp/some-other-place/hidden_ground_truth.json")
    assert _display_path(outside) == str(outside)


def test_main_with_no_dataset_root_or_ground_truth_flags_reproduces_the_frozen_travel_result(
    tmp_path: Path,
) -> None:
    """The actual regression check: run `main()` passing only `--output` (redirected to a scratch
    path) — every other flag, including the new `--dataset-root`/`--ground-truth`, is left at its
    default — and confirm the six metrics match `artifacts/evaluation/
    task-028-benchmark-evaluation.json`'s already-frozen values exactly. Proves the input-source
    parameterization changed nothing about default (travel) behavior, not just that the new flags
    parse.
    """
    frozen = json.loads(
        (REPOSITORY / "artifacts/evaluation/task-028-benchmark-evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    output_path = tmp_path / "regression-check.json"

    main(["--output", str(output_path)])
    fresh = json.loads(output_path.read_text(encoding="utf-8"))
    fresh_metrics, frozen_metrics = fresh["metrics"], frozen["metrics"]

    assert fresh_metrics["top_k_precision"]["value"] == pytest.approx(
        frozen_metrics["top_k_precision"]["value"]
    )
    assert fresh_metrics["economic_weighted_recall"]["value"] == pytest.approx(
        frozen_metrics["economic_weighted_recall"]["value"]
    )
    assert (
        fresh_metrics["leakage_violations"]["value"]
        == frozen_metrics["leakage_violations"]["value"]
    )
    assert (
        fresh_metrics["confounder_trap_rejection"]["any_trap_promoted"]
        == frozen_metrics["confounder_trap_rejection"]["any_trap_promoted"]
    )
    # HANDOFF-065: the dynamically-computed trap/pattern id sets must exactly match what used to be
    # the hand-transcribed TRAP_APPARENT_CONDITIONS/SCOREABLE_PATTERN_IDS module constants.
    assert (
        fresh_metrics["confounder_trap_rejection"]["trap_promoted"]
        == frozen_metrics["confounder_trap_rejection"]["trap_promoted"]
    )
    assert (
        fresh_metrics["confounder_trap_rejection"]["trap_appeared_as_candidate"]
        == frozen_metrics["confounder_trap_rejection"]["trap_appeared_as_candidate"]
    )
    assert (
        fresh["methodology"]["scoreable_pattern_ids"]
        == (frozen["methodology"]["scoreable_pattern_ids"])
    )
    assert fresh_metrics["effect_direction_accuracy"]["value"] == pytest.approx(
        frozen_metrics["effect_direction_accuracy"]["value"]
    )
    assert fresh_metrics["economic_impact_estimation_error"]["median_relative_error"] == (
        pytest.approx(frozen_metrics["economic_impact_estimation_error"]["median_relative_error"])
    )

    # The dynamically-computed hash must equal the value that used to be hardcoded as
    # "ground_truth_sha256_expected" — proof the switch from a pinned literal to a computed digest
    # didn't silently change which file's hash gets reported for the default (travel) case.
    assert fresh["inputs"]["ground_truth_sha256"] == (
        "5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506"
    )
    assert fresh["inputs"]["dataset_root"] == (
        "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
    )
    assert fresh["inputs"]["ground_truth"] == "synthetic_data/evaluation/hidden_ground_truth.json"
