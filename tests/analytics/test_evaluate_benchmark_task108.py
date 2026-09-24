"""TASK-108 (`ADR-106` Decision 1): the scorer's trap-vs-pattern classification.

Spec: `docs/benchmark/task-108-scorer-trap-classification-spec.md`. All rule fixtures are read from
the real travel `hidden_ground_truth.json` (tracked), so a change to a pattern's rule or a trap's
apparent feature fails these tests instead of silently drifting.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "scripts"))

import evaluate_benchmark  # noqa: E402
from evaluate_benchmark import (  # noqa: E402
    _genuine_trap_matches,
    _matches_trap,
    _parse_pattern_rule,
    _trap_apparent_conditions,
    main,
)

pytestmark = pytest.mark.analytics

_TRAVEL_GT = json.loads(
    (REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json").read_text(encoding="utf-8")
)
_TRAVEL_PATTERNS: dict[str, dict[str, object]] = {p["id"]: p for p in _TRAVEL_GT["patterns"]}
_TRAVEL_TRAPS = _trap_apparent_conditions(_TRAVEL_GT)


def _cond(feature: str, operator: str, value: object) -> dict[str, object]:
    return {"feature": feature, "operator": operator, "value": value}


#: The exact ground-truth rule of each overlapping pattern, as candidate conditions.
_P03_EXACT = [
    _cond("installments", "ge", 3),
    _cond("customer_type", "eq", "new"),
    _cond("acquisition_channel", "eq", "paid_search"),
]
_P04_EXACT = [
    _cond("supplier", "eq", "Atlas"),
    _cond("trip_duration_days", "ge", 14),
    _cond("booking_month", "eq", 12),
]
_P06_EXACT = [
    _cond("destination", "eq", "Tokyo"),
    _cond("booking_lead_days", "lt", 10),
    _cond("payment_method", "eq", "bank_transfer"),
]
_OVERLAP_CASES = [
    ("P03", _P03_EXACT, "T03"),
    ("P04", _P04_EXACT, "T02"),
    ("P06", _P06_EXACT, "T04"),
]


def _genuine(conditions: list[dict[str, object]], matched: list[str]) -> list[str]:
    # Looked up through the module so the mutation test can swap the implementation.
    return evaluate_benchmark._genuine_trap_matches(  # pyright: ignore[reportPrivateUsage]
        conditions, matched, _TRAVEL_TRAPS, _TRAVEL_PATTERNS
    )


def _is_true_pattern(conditions: list[dict[str, object]], matched: list[str]) -> bool:
    # Mirrors main(): `is_true_pattern = bool(matched) and not matched_traps`.
    return bool(matched) and not _genuine(conditions, matched)


@pytest.mark.parametrize(("pid", "conditions", "trap_id"), _OVERLAP_CASES)
def test_exact_overlap_pattern_rule_recovers_its_pattern_and_is_not_a_trap(
    pid: str, conditions: list[dict[str, object]], trap_id: str
) -> None:
    # The overlap is real: literal containment alone still flags the trap ...
    assert _matches_trap(conditions, _TRAVEL_TRAPS) == [trap_id]
    # ... but the classification does not, so the candidate is a true pattern.
    assert _genuine(conditions, [pid]) == []
    assert _is_true_pattern(conditions, [pid])


def test_old_precise_p06_candidate_is_no_longer_a_trap() -> None:
    # Flagged T04 in the archived v0.2.0/v0.3.1/v0.4.1/v0.5.0 evaluations.
    conditions = [
        _cond("booking_lead_days", "lt", 23.0),
        _cond("destination", "eq", "Tokyo"),
        _cond("payment_method", "eq", "bank_transfer"),
    ]
    assert _genuine(conditions, ["P06"]) == []


def test_p05_exact_rule_with_boolean_literal_is_not_a_trap() -> None:
    conditions = [
        _cond("manager", "eq", "Manager 4"),
        _cond("manual_exception", "eq", True),
        _cond("customer_price_eur", "ge", 3500),
    ]
    assert _matches_trap(conditions, _TRAVEL_TRAPS) == ["T05"]
    assert _genuine(conditions, ["P05"]) == []


@pytest.mark.parametrize(
    ("conditions", "matched", "trap_id"),
    [
        # Bare apparent-feature rules stay traps even when they recall-match the pattern.
        ([_cond("supplier", "eq", "Atlas")], ["P04"], "T02"),
        ([_cond("acquisition_channel", "eq", "paid_search")], ["P03"], "T03"),
        ([_cond("payment_method", "eq", "bank_transfer")], ["P06"], "T04"),
        # Shapes of the archived TASK-073/TASK-083-era trap candidates (task-060/-064 evaluations;
        # TASK-073 promoted the first and third to shadow_policy): the literal plus a feature
        # that is not part of the pattern stays a trap, with and without a matched pattern.
        (
            [_cond("acquisition_channel", "eq", "paid_search"), _cond("discount_rate", "ge", 0.08)],
            [],
            "T03",
        ),
        (
            [_cond("acquisition_channel", "eq", "paid_search"), _cond("discount_rate", "ge", 0.03)],
            ["P03"],
            "T03",
        ),
        (
            [_cond("discount_rate", "ge", 0.05), _cond("payment_method", "eq", "bank_transfer")],
            ["P06"],
            "T04",
        ),
        # A feature of some other matched pattern does not exempt: the matched pattern must itself
        # contain the trap's literal.
        (
            [_cond("payment_method", "eq", "bank_transfer"), _cond("supplier", "eq", "BlueWing")],
            ["P01"],
            "T04",
        ),
        # A trap with no overlapping pattern at all.
        (
            [_cond("manager", "eq", "Manager 2"), _cond("destination", "eq", "Tokyo")],
            ["P06"],
            "T01",
        ),
    ],
)
def test_genuine_trap_candidates_remain_traps(
    conditions: list[dict[str, object]], matched: list[str], trap_id: str
) -> None:
    assert _genuine(conditions, matched) == [trap_id]
    assert not _is_true_pattern(conditions, matched)


def test_exemption_is_per_trap_a_second_trap_still_fires() -> None:
    conditions = [*_P03_EXACT, _cond("supplier", "eq", "Atlas")]
    # T03 exempt (P03 recovered with its own extra features); T02's literal is not in P03's rule.
    assert _genuine(conditions, ["P03"]) == ["T02"]


def test_pattern_rule_parser_reads_real_rules() -> None:
    features, literals = _parse_pattern_rule(_TRAVEL_PATTERNS["P04"]["rule"])
    assert features == {"supplier", "trip_duration_days", "booking_month"}
    assert literals == {("supplier", "eq", "Atlas")}
    features, literals = _parse_pattern_rule(_TRAVEL_PATTERNS["P05"]["rule"])
    assert ("manual_exception", "eq", True) in literals
    assert features == {"manager", "manual_exception", "customer_price_eur"}


def test_pattern_rule_parser_fails_closed() -> None:
    assert _parse_pattern_rule(None) == (frozenset(), frozenset())
    assert _parse_pattern_rule("this is not a rule") == (frozenset(), frozenset())
    # A pattern with no parsable rule can never exempt a trap match.
    assert _genuine_trap_matches(_P06_EXACT, ["P06"], _TRAVEL_TRAPS, {"P06": {"id": "P06"}}) == [
        "T04"
    ]


def test_mutation_reverting_the_fix_fails_the_overlap_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revert the fix in-test (classification = literal containment, the pre-TASK-108 behavior):
    every overlap case flips back to trap, so the tests above genuinely detect the fix."""

    def reverted(
        conditions: list[dict[str, object]],
        matched_patterns: list[str],
        trap_apparent_conditions: dict[str, tuple[str, str, object]],
        patterns_by_id: dict[str, dict[str, object]],
    ) -> list[str]:
        return _matches_trap(conditions, trap_apparent_conditions)

    monkeypatch.setattr(evaluate_benchmark, "_genuine_trap_matches", reverted)
    for pid, conditions, trap_id in _OVERLAP_CASES:
        assert _genuine(conditions, [pid]) == [trap_id]
        assert not _is_true_pattern(conditions, [pid])


@pytest.mark.parametrize(
    ("conditions", "matched"),
    [
        ([_cond("discount_rate", "ge", 0.12)], ["P01"]),
        ([_cond("manager", "eq", "Manager 2")], []),
        ([_cond("payment_method", "eq", "bank_transfer")], []),
        ([_cond("supplier", "eq", "Atlas"), _cond("manager", "eq", "Manager 2")], ["P04"]),
        ([_cond("supplier", "eq", "Atlas"), _cond("destination", "eq", "Tokyo")], ["P04"]),
        ([], []),
    ],
)
def test_without_trap_pattern_overlap_classification_equals_literal_containment(
    conditions: list[dict[str, object]], matched: list[str]
) -> None:
    assert _genuine(conditions, matched) == _matches_trap(conditions, _TRAVEL_TRAPS)


@pytest.mark.parametrize("run", ["run1", "run2"])
def test_scoring_output_is_unchanged_on_task103_evidence(run: str, tmp_path: Path) -> None:
    """End-to-end: replay the committed TASK-103 evidence (candidate sets with no trap/pattern
    overlap) through the real `main()`; `candidate_scores`, `metrics` and `methodology` must equal
    the archived evaluation exactly. Uses only tracked files."""
    base = REPOSITORY / "docs/benchmark/task-103-evidence" / run
    validation = json.loads((base / "validation.json").read_text(encoding="utf-8"))
    validation["candidates_source"] = str(base / "candidates.json")
    validation_path = tmp_path / "validation.json"
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    output_path = tmp_path / "evaluation.json"

    main(
        [
            "--validation-report",
            str(validation_path),
            "--output",
            str(output_path),
            "--dataset-root",
            str(REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"),
        ]
    )
    fresh = json.loads(output_path.read_text(encoding="utf-8"))
    archived = json.loads((base / "evaluation.json").read_text(encoding="utf-8"))
    assert fresh["candidate_scores"] == archived["candidate_scores"]
    assert fresh["metrics"] == archived["metrics"]
    assert fresh["methodology"] == archived["methodology"]
