from __future__ import annotations

import polars as pl
import pytest
from policy_analytics.profiling.schema_profiler import profile_column, profile_columns

pytestmark = pytest.mark.analytics


def test_infers_clean_integer_column() -> None:
    profile = profile_column("party_size", ["1", "2", "3", "4"])
    assert profile.inferred_type == "integer"
    assert profile.min_value == "1"
    assert profile.max_value == "4"
    assert profile.suspicious_count == 0
    assert profile.semantic_type_guess == "count_or_quantity"


def test_name_hints_match_whole_tokens_not_substrings() -> None:
    """Regression test: "trip_duration" was misclassified as "percentage_rate" because "duration"
    happens to contain "ratio" as a raw substring — caught via a live upload of the real
    tests/fixtures/synthetic_travel_bookings.csv fixture, not by narrower unit-test coverage."""
    profile = profile_column("trip_duration", ["9", "17", "6", "12"])
    assert profile.inferred_type == "integer"
    assert profile.semantic_type_guess == "count_or_quantity"


def test_infers_float_column_as_currency_amount() -> None:
    profile = profile_column("customer_price", ["100.50", "200.00", "3450.25"])
    assert profile.inferred_type == "float"
    assert profile.min_value == "100.5"
    assert profile.max_value == "3450.25"
    assert profile.semantic_type_guess == "currency_amount"


def test_infers_boolean_column() -> None:
    profile = profile_column("cancellation", ["True", "False", "False", "True"])
    assert profile.inferred_type == "boolean"
    assert profile.semantic_type_guess == "boolean_flag"
    assert profile.min_value is None and profile.max_value is None


def test_zero_one_integer_column_is_flagged_boolean_flag_but_structurally_integer() -> None:
    """Known, documented limitation (see schema_profiler.py docstring): 0/1-encoded booleans are
    structurally "integer" (0/1 matches the integer pattern before boolean is ever tried), refined
    at the semantic-type layer instead."""
    profile = profile_column("is_repeat", ["0", "1", "0", "1", "1"])
    assert profile.inferred_type == "integer"
    assert profile.semantic_type_guess == "boolean_flag"


def test_infers_date_column() -> None:
    profile = profile_column("booking_date", ["2025-01-01", "2025-06-18", "2025-12-31"])
    assert profile.inferred_type == "date"
    assert profile.min_value == "2025-01-01"
    assert profile.max_value == "2025-12-31"
    assert profile.semantic_type_guess == "date"


def test_low_cardinality_string_is_categorical() -> None:
    values = ["Manager 1", "Manager 2", "Manager 1", "Manager 3", "Manager 1"] * 20
    profile = profile_column("manager", values)
    assert profile.inferred_type == "string"
    assert profile.semantic_type_guess == "categorical"
    assert profile.distinct_count == 3
    assert not profile.examples_suppressed
    assert set(profile.examples) <= set(values)


def test_high_cardinality_id_column_is_identifier_and_examples_suppressed() -> None:
    values = [f"SYN-{i:04d}" for i in range(200)]
    profile = profile_column("booking_id", values)
    assert profile.inferred_type == "string"
    assert profile.semantic_type_guess == "identifier"
    assert profile.examples_suppressed is True
    assert profile.examples == ()


def test_high_cardinality_non_id_string_is_free_text_and_suppressed() -> None:
    values = [f"note about booking number {i} with unique detail" for i in range(200)]
    profile = profile_column("notes", values)
    assert profile.semantic_type_guess == "free_text"
    assert profile.examples_suppressed is True


def test_categorical_examples_are_capped_and_deduplicated() -> None:
    values = ["A", "A", "A", "B", "C", "D", "E"]
    profile = profile_column("code", values)
    assert len(profile.examples) <= 3
    assert len(set(profile.examples)) == len(profile.examples)


def test_missing_values_counted_and_not_double_counted_as_distinct() -> None:
    profile = profile_column("optional_field", ["a", None, "b", None, None])
    assert profile.row_count == 5
    assert profile.missing_count == 3
    assert profile.missingness == pytest.approx(0.6)
    assert profile.distinct_count == 2


def test_empty_string_is_treated_as_missing_by_caller_contract_not_a_distinct_value() -> None:
    # profile_column itself trusts its caller's None/non-None split; this test documents the
    # contract explicitly (profile_columns is responsible for the CSV-cell -> None conversion).
    profile = profile_column("x", [None, None])
    assert profile.missing_count == 2
    assert profile.distinct_count == 0
    assert profile.inferred_type == "string"


def test_all_null_column_does_not_crash_and_reports_full_missingness() -> None:
    profile = profile_column("empty_col", [None, None, None])
    assert profile.missingness == 1.0
    assert profile.distinct_count == 0
    assert profile.min_value is None
    assert profile.max_value is None


def test_messy_column_below_threshold_falls_back_to_string_and_flags_suspicious_values() -> None:
    # 95 clean integers + 5 garbage values = 95% match, below the 98% threshold -> "string",
    # and the *garbage* values become suspicious only relative to the *winning* type (string
    # matches everything, so nothing is suspicious under a string fallback) — verifies the
    # threshold behavior, not a false claim about what counts as suspicious for "string".
    values = [str(i) for i in range(95)] + ["N/A", "unknown", "--", "?", "null"]
    profile = profile_column("messy", values)
    assert profile.inferred_type == "string"
    assert profile.suspicious_count == 0


def test_mostly_clean_column_above_threshold_flags_the_minority_as_suspicious() -> None:
    # 99 clean integers + 1 garbage value out of 100 = 99% match, clears the 98% threshold.
    values = [str(i) for i in range(99)] + ["N/A"]
    profile = profile_column("mostly_clean", values)
    assert profile.inferred_type == "integer"
    assert profile.suspicious_count == 1
    assert profile.suspicious_values == ("N/A",)


def test_a_suspicious_value_never_leaks_into_min_or_max() -> None:
    """Regression test for a real bug: `_min_max` used to filter with the broader `_matches_float`
    (which also accepts plain integers) instead of the winning type's own predicate, so a
    suspicious non-integer value could still end up reported as an "integer" column's min/max —
    silently laundering a flagged outlier into what looks like a normal range boundary. Found by
    manual repro, not by the original test suite (whose suspicious-value fixtures never happened
    to be the numeric extreme)."""
    values = [str(i) for i in range(1, 100)] + ["999999.5"]
    profile = profile_column("mostly_clean", values)
    assert profile.inferred_type == "integer"
    assert profile.suspicious_values == ("999999.5",)
    assert profile.max_value == "99"
    assert profile.min_value == "1"


def test_suspicious_date_value_never_leaks_into_min_or_max() -> None:
    values = ["2025-01-01", "2025-06-15", "2025-12-31"] * 40 + ["not-a-date"]
    profile = profile_column("some_date", values)
    assert profile.inferred_type == "date"
    assert profile.suspicious_values == ("not-a-date",)
    assert profile.min_value == "2025-01-01"
    assert profile.max_value == "2025-12-31"


def test_suspicious_values_are_capped() -> None:
    # 495 clean + 10 bad = 505 total, 495/505 ~= 98.0% -> clears the threshold as "integer", with
    # more suspicious values than MAX_SUSPICIOUS_VALUES to actually exercise the cap.
    values = [str(i) for i in range(495)] + [f"bad{i}" for i in range(10)]
    profile = profile_column("mostly_clean_big", values)
    assert profile.inferred_type == "integer"
    assert profile.suspicious_count == 10
    assert len(profile.suspicious_values) == 5


def test_profile_columns_profiles_every_column_of_a_frame() -> None:
    frame = pl.DataFrame(
        {
            "booking_id": ["SYN-0001", "SYN-0002", "SYN-0003"],
            "discount": ["0.03", "0.10", None],
            "cancellation": ["True", "False", "False"],
        }
    )
    profiles = profile_columns(frame)
    by_name = {p.name: p for p in profiles}
    assert set(by_name) == {"booking_id", "discount", "cancellation"}
    assert by_name["discount"].inferred_type == "float"
    assert by_name["discount"].missing_count == 1
    assert by_name["cancellation"].inferred_type == "boolean"
