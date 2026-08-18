from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from policy_analytics.cleaning.canonical_schema import CANONICAL_SCHEMA_VERSION
from policy_analytics.cleaning.mapping import (
    ColumnMapping,
    FieldMapping,
    suggest_mapping,
    validate_mapping,
)
from policy_analytics.cleaning.normalize import CanonicalizationError, canonicalize
from policy_analytics.profiling.feature_timing import classify_columns
from policy_analytics.profiling.schema_profiler import profile_columns

pytestmark = pytest.mark.analytics

REPOSITORY = Path(__file__).resolve().parents[2]
CLEAN_BENCHMARK_CSV = REPOSITORY / "synthetic_data/reference/travel_bookings_clean.csv"
DIRTY_BENCHMARK_CSV = REPOSITORY / "synthetic_data/raw/travel_bookings_dirty.csv"
OLDER_FIXTURE_CSV = REPOSITORY / "tests/fixtures/synthetic_travel_bookings.csv"


def _pipeline(frame: pl.DataFrame):
    profiles = profile_columns(frame)
    classifications = classify_columns(profiles)
    return profiles, classifications


# --- suggest_mapping / validate_mapping on synthetic (all-canonical-named) input --------------


@pytest.mark.skipif(not CLEAN_BENCHMARK_CSV.exists(), reason="benchmark artifact not present")
def test_clean_benchmark_maps_every_column_with_no_validation_errors() -> None:
    frame = pl.read_csv(CLEAN_BENCHMARK_CSV, infer_schema_length=0)
    profiles, classifications = _pipeline(frame)
    mapping = suggest_mapping(profiles)

    assert len(mapping.fields) == 32
    assert mapping.schema_version == CANONICAL_SCHEMA_VERSION
    assert validate_mapping(mapping, classifications) == ()


@pytest.mark.skipif(not CLEAN_BENCHMARK_CSV.exists(), reason="benchmark artifact not present")
def test_clean_benchmark_canonicalizes_to_the_full_typed_schema() -> None:
    frame = pl.read_csv(CLEAN_BENCHMARK_CSV, infer_schema_length=0)
    profiles, classifications = _pipeline(frame)
    mapping = suggest_mapping(profiles)

    result = canonicalize(frame, mapping, classifications)

    assert result.frame.height == frame.height
    assert result.dropped_columns == ()
    assert result.schema_version == CANONICAL_SCHEMA_VERSION
    assert result.frame.schema["booking_date"] == pl.Date
    assert result.frame.schema["customer_price_eur"] == pl.Float64
    assert result.frame.schema["party_size"] == pl.Int64
    assert result.frame.schema["cancellation"] == pl.Boolean
    assert result.frame["booking_id"].n_unique() == frame.height


@pytest.mark.skipif(not DIRTY_BENCHMARK_CSV.exists(), reason="benchmark artifact not present")
def test_dirty_benchmark_fails_closed_on_unparseable_dates() -> None:
    """The deliberately dirty variant has real DD/MM/YYYY-corrupted booking_date values
    (TASK-007's own suspicious_count=127 for this column) — canonicalization must refuse to
    silently coerce or drop them, not paper over known-bad data."""
    frame = pl.read_csv(DIRTY_BENCHMARK_CSV, infer_schema_length=0)
    profiles, classifications = _pipeline(frame)
    mapping = suggest_mapping(profiles)

    with pytest.raises(CanonicalizationError, match="booking_date"):
        canonicalize(frame, mapping, classifications)


# --- a genuinely different raw schema (not just already-canonical names) ----------------------


def test_differently_named_fixture_suggests_aliased_partial_mapping() -> None:
    """tests/fixtures/synthetic_travel_bookings.csv uses different column names for the same
    concepts (customer_price, cost, gross_margin, ...) and is missing several canonical fields
    outright (customer_id, currency, support_cost_eur, contribution_margin_eur) — the realistic
    shape of what a real customer export will look like."""
    frame = pl.read_csv(OLDER_FIXTURE_CSV, infer_schema_length=0)
    profiles, _classifications = _pipeline(frame)
    mapping = suggest_mapping(profiles)

    assert mapping.source_for("customer_price_eur") == "customer_price"
    assert mapping.source_for("quoted_cost_eur") == "cost"
    assert mapping.source_for("gross_profit_eur") == "gross_margin"
    assert mapping.source_for("customer_id") is None  # genuinely absent, not guessed


def test_differently_named_fixture_fails_closed_on_missing_required_fields() -> None:
    frame = pl.read_csv(OLDER_FIXTURE_CSV, infer_schema_length=0)
    profiles, classifications = _pipeline(frame)
    mapping = suggest_mapping(profiles)

    errors = validate_mapping(mapping, classifications)
    assert len(errors) == 1
    assert "customer_id" in errors[0]
    assert "currency" in errors[0]
    assert "support_cost_eur" in errors[0]
    assert "contribution_margin_eur" in errors[0]

    with pytest.raises(CanonicalizationError):
        canonicalize(frame, mapping, classifications)


# --- validate_mapping safety checks, independent of suggest_mapping ----------------------------


def test_mapping_a_non_decision_time_source_onto_a_decision_time_field_is_rejected() -> None:
    """The one safety-critical cross-check: a source column TASK-008 classified OUTCOME (or
    anything but DECISION_TIME) must never be laundered into a canonical DECISION_TIME field,
    however the mapping was constructed — not just via `suggest_mapping`."""
    frame = pl.DataFrame(
        {"realized_profit": ["10.0", "20.0", "30.0"]},
    )
    profiles = profile_columns(frame)
    classifications = classify_columns(profiles)
    assert classifications[0].timing.value == "outcome"  # "profit" token -> OUTCOME

    bad_mapping = ColumnMapping(
        schema_version=CANONICAL_SCHEMA_VERSION,
        fields=(FieldMapping(canonical_name="destination", source_column="realized_profit"),),
    )
    errors = validate_mapping(bad_mapping, classifications)
    assert len(errors) >= 1
    assert any("refusing to launder" in error for error in errors)


def test_mapping_the_same_source_column_twice_is_rejected() -> None:
    frame = pl.DataFrame({"x": ["Rome", "Tokyo"]})
    profiles = profile_columns(frame)
    classifications = classify_columns(profiles)

    mapping = ColumnMapping(
        schema_version=CANONICAL_SCHEMA_VERSION,
        fields=(
            FieldMapping(canonical_name="destination", source_column="x"),
            FieldMapping(canonical_name="supplier", source_column="x"),
        ),
    )
    errors = validate_mapping(mapping, classifications)
    assert any("mapped to both" in error for error in errors)


def test_mapping_an_unknown_canonical_field_name_is_rejected() -> None:
    frame = pl.DataFrame({"x": ["Rome", "Tokyo"]})
    profiles = profile_columns(frame)
    classifications = classify_columns(profiles)

    mapping = ColumnMapping(
        schema_version=CANONICAL_SCHEMA_VERSION,
        fields=(FieldMapping(canonical_name="not_a_real_field", source_column="x"),),
    )
    errors = validate_mapping(mapping, classifications)
    assert any("not a canonical field" in error for error in errors)


def test_mapping_a_source_column_with_no_classification_is_rejected() -> None:
    mapping = ColumnMapping(
        schema_version=CANONICAL_SCHEMA_VERSION,
        fields=(FieldMapping(canonical_name="destination", source_column="ghost_column"),),
    )
    errors = validate_mapping(mapping, classifications=())
    assert any("no feature-timing classification" in error for error in errors)


# --- normalize.canonicalize on hand-built minimal frames ---------------------------------------


def test_canonicalize_rejects_unrecognized_boolean_values() -> None:
    frame = pl.DataFrame(
        {
            "booking_id": ["B1", "B2"],
            "customer_id": ["C1", "C1"],
            "booking_date": ["2024-01-01", "2024-01-02"],
            "customer_price_eur": ["100.0", "200.0"],
            "currency": ["EUR", "EUR"],
            "cancellation": ["True", "maybe"],
            "refund_amount_eur": ["0.0", "0.0"],
            "support_cost_eur": ["0.0", "0.0"],
            "additional_cost_eur": ["0.0", "0.0"],
            "gross_profit_eur": ["50.0", "60.0"],
            "contribution_margin_eur": ["40.0", "50.0"],
        }
    )
    profiles, classifications = _pipeline(frame)
    mapping = suggest_mapping(profiles)
    assert validate_mapping(mapping, classifications) == ()

    with pytest.raises(CanonicalizationError, match="not recognized as boolean"):
        canonicalize(frame, mapping, classifications)


def test_canonicalize_records_dropped_unmapped_source_columns() -> None:
    frame = pl.DataFrame(
        {
            "booking_id": ["B1", "B2"],
            "customer_id": ["C1", "C1"],
            "booking_date": ["2024-01-01", "2024-01-02"],
            "customer_price_eur": ["100.0", "200.0"],
            "currency": ["EUR", "EUR"],
            "cancellation": ["True", "False"],
            "refund_amount_eur": ["0.0", "0.0"],
            "support_cost_eur": ["0.0", "0.0"],
            "additional_cost_eur": ["0.0", "0.0"],
            "gross_profit_eur": ["50.0", "60.0"],
            "contribution_margin_eur": ["40.0", "50.0"],
            "internal_export_batch_id": ["B7", "B7"],
        }
    )
    profiles, classifications = _pipeline(frame)
    mapping = suggest_mapping(profiles)

    result = canonicalize(frame, mapping, classifications)
    assert result.dropped_columns == ("internal_export_batch_id",)
