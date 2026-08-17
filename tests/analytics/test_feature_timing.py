from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import polars as pl
import pytest
from policy_analytics.profiling.feature_timing import classify_columns, classify_feature_timing
from policy_analytics.profiling.schema_profiler import (
    ColumnProfile,
    profile_column,
    profile_columns,
)
from policy_schemas.domain import FeatureTiming

pytestmark = pytest.mark.analytics

REPOSITORY = Path(__file__).resolve().parents[2]
BENCHMARK_CSV = REPOSITORY / "synthetic_data/raw/travel_bookings_dirty.csv"
BENCHMARK_FEATURE_TIMING = REPOSITORY / "synthetic_data/metadata/feature_timing.json"


def _profile(name: str, values: Sequence[str | None]) -> ColumnProfile:
    return profile_column(name, list(values))


# --- per-tier unit tests --------------------------------------------------------------------


def test_id_suffixed_column_is_identifier_regardless_of_cardinality() -> None:
    """`customer_id` repeats across bookings (low cardinality) — a real column this exact bug
    would have hit if identifier detection relied only on the TASK-007 profiler's own
    high-cardinality-driven "identifier" guess, which `customer_id` does not clear."""
    profile = _profile("customer_id", ["CUST-1", "CUST-1", "CUST-2", "CUST-2"])
    assert profile.semantic_type_guess != "identifier"  # sanity: the profiler alone would miss it
    result = classify_feature_timing(profile)
    assert result.timing is FeatureTiming.IDENTIFIER


def test_high_cardinality_id_column_is_identifier() -> None:
    profile = _profile("booking_id", [f"SYN-{i}" for i in range(50)])
    assert classify_feature_timing(profile).timing is FeatureTiming.IDENTIFIER


def test_currency_name_is_metadata() -> None:
    profile = _profile("currency", ["EUR", "EUR", "USD"])
    assert classify_feature_timing(profile).timing is FeatureTiming.METADATA


@pytest.mark.parametrize(
    "name",
    [
        "gross_profit_eur",
        "net_profit_eur",
        "contribution_margin_eur",
        "operating_margin",
        "margin",
        "refund_amount_eur",
        "support_cost_eur",
        "additional_cost_eur",
        "cancellation",
        "repeat_purchase_180d",
        "churn_flag",
    ],
)
def test_realized_outcome_names_are_outcome(name: str) -> None:
    profile = _profile(name, ["1.0", "2.0", "3.0"])
    assert classify_feature_timing(profile).timing is FeatureTiming.OUTCOME


@pytest.mark.parametrize(
    "name,values",
    [
        ("refund_date", ["2025-01-01", "2025-02-02"]),
        ("last_modified_at", ["2025-01-01", "2025-02-02"]),
        ("booking_changes", ["0", "1"]),
        ("support_cases", ["0", "2"]),
    ],
)
def test_post_decision_event_names_are_post_decision(name: str, values: list[str]) -> None:
    assert classify_feature_timing(_profile(name, values)).timing is FeatureTiming.POST_DECISION


def test_identifier_naming_wins_over_a_post_decision_event_keyword() -> None:
    """`dispute_ticket_id` names both a post-decision event ("dispute") and an identifier (ends in
    "_id") — the identifier tier is checked first and must win, since an ID column is a join key,
    never an explanatory feature of any timing."""
    profile = _profile("dispute_ticket_id", ["T-1", "T-2", "T-3"])
    assert classify_feature_timing(profile).timing is FeatureTiming.IDENTIFIER


def test_refund_amount_is_outcome_but_refund_date_is_post_decision() -> None:
    """The same "refund" root resolves to two different classifications depending on whether the
    column names a realized amount or an event date — the exact ambiguity this module's docstring
    calls out."""
    amount = _profile("refund_amount_eur", ["0.0", "120.5"])
    date = _profile("refund_date", ["2025-01-01", None])
    assert classify_feature_timing(amount).timing is FeatureTiming.OUTCOME
    assert classify_feature_timing(date).timing is FeatureTiming.POST_DECISION


@pytest.mark.parametrize(
    "name,values",
    [
        ("destination", ["Rome", "Tokyo", "Rome", "Rome", "Tokyo"]),
        ("booking_date", ["2024-01-01", "2024-06-01"]),
        ("customer_price_eur", ["100.0", "200.0"]),
        ("quoted_cost_eur", ["80.0", "150.0"]),
        ("discount_rate", ["0.05", "0.1"]),
        ("party_size", ["1", "2", "3"]),
        ("trip_duration_days", ["3", "7"]),
        ("manual_exception", ["True", "False"]),
    ],
)
def test_decision_time_attribute_names_are_decision_time(name: str, values: list[str]) -> None:
    profile = _profile(name, values)
    assert classify_feature_timing(profile).timing is FeatureTiming.DECISION_TIME


def test_unrecognized_column_name_defaults_to_unknown_not_decision_time() -> None:
    """The safety-critical default: a column with no matching rule must never be silently admitted
    as DECISION_TIME (engineering rules: "never allow unknown ... fields into explanatory features
    silently")."""
    profile = _profile("x_field_7", ["3.14159", "2.71828", "1.41421"])
    assert classify_feature_timing(profile).timing is FeatureTiming.UNKNOWN


def test_classify_columns_preserves_order_and_length() -> None:
    profiles = (
        _profile("booking_id", ["A", "B"]),
        _profile("x_unrecognized", ["1", "2"]),
        _profile("currency", ["EUR", "EUR"]),
    )
    results = classify_columns(profiles)
    assert [r.column_name for r in results] == ["booking_id", "x_unrecognized", "currency"]
    assert [r.timing for r in results] == [
        FeatureTiming.IDENTIFIER,
        FeatureTiming.UNKNOWN,
        FeatureTiming.METADATA,
    ]


def test_classification_is_deterministic() -> None:
    profile = _profile("support_cost_eur", ["10.0", "20.0"])
    first = classify_feature_timing(profile)
    second = classify_feature_timing(profile)
    assert first == second


# --- benchmark ground-truth regression -------------------------------------------------------


@pytest.mark.skipif(
    not (BENCHMARK_CSV.exists() and BENCHMARK_FEATURE_TIMING.exists()),
    reason="synthetic benchmark artifacts not present in this checkout",
)
def test_matches_benchmark_expected_feature_timing() -> None:
    """TASK-008's own done condition: benchmark classification matches expected metadata. Reads
    only public schema metadata (`synthetic_data/metadata/feature_timing.json`), never
    `synthetic_data/evaluation/hidden_ground_truth.json` — no restricted artifact is opened."""
    frame = pl.read_csv(BENCHMARK_CSV, infer_schema_length=0)
    profiles = profile_columns(frame)
    classifications = {c.column_name: c.timing for c in classify_columns(profiles)}

    expected = {
        column["name"]: FeatureTiming[column["classification"]]
        for column in json.loads(BENCHMARK_FEATURE_TIMING.read_text())["columns"]
    }

    assert set(classifications) == set(expected)
    mismatches = {
        name: (expected[name], classifications[name])
        for name in expected
        if classifications[name] != expected[name]
    }
    assert mismatches == {}


@pytest.mark.skipif(
    not (BENCHMARK_CSV.exists() and BENCHMARK_FEATURE_TIMING.exists()),
    reason="synthetic benchmark artifacts not present in this checkout",
)
def test_no_leaky_benchmark_column_is_ever_classified_decision_time() -> None:
    """Stronger, independent safety property than exact-match above: even if a future rule change
    regresses which non-decision-time bucket a column lands in, no column the benchmark's own
    generator marks IDENTIFIER/POST_DECISION/OUTCOME/METADATA may ever come out DECISION_TIME."""
    frame = pl.read_csv(BENCHMARK_CSV, infer_schema_length=0)
    profiles = profile_columns(frame)
    classifications = {c.column_name: c.timing for c in classify_columns(profiles)}

    expected = {
        column["name"]: column["classification"]
        for column in json.loads(BENCHMARK_FEATURE_TIMING.read_text())["columns"]
    }

    leaked = [
        name
        for name, expected_classification in expected.items()
        if expected_classification != "DECISION_TIME"
        and classifications[name] is FeatureTiming.DECISION_TIME
    ]
    assert leaked == []
