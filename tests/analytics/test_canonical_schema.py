from __future__ import annotations

import pytest
from policy_analytics.cleaning.canonical_schema import (
    CANONICAL_FIELDS_BY_NAME,
    CANONICAL_SCHEMA,
    CANONICAL_SCHEMA_VERSION,
    required_fields,
)
from policy_analytics.outcomes.contract import OUTCOME_DEFINITIONS, MissingDataPolicy
from policy_schemas.domain import FeatureTiming

pytestmark = pytest.mark.analytics


def test_schema_has_no_duplicate_names() -> None:
    names = [field.name for field in CANONICAL_SCHEMA]
    assert len(names) == len(set(names))


def test_schema_version_matches_analytical_dataset() -> None:
    """The one existing consumer of this version string must stay in sync — it now imports the
    same constant rather than defining its own copy (see analytical_dataset.py)."""
    from policy_analytics.analytical_dataset import CANONICAL_SCHEMA_VERSION as consumer_version

    assert consumer_version == CANONICAL_SCHEMA_VERSION


def test_fields_by_name_is_consistent_with_the_tuple() -> None:
    assert set(CANONICAL_FIELDS_BY_NAME) == {field.name for field in CANONICAL_SCHEMA}
    for name, field in CANONICAL_FIELDS_BY_NAME.items():
        assert field.name == name


def test_every_field_has_a_valid_dtype() -> None:
    valid = {"string", "integer", "float", "boolean", "date"}
    for field in CANONICAL_SCHEMA:
        assert field.dtype in valid, field.name


def test_every_field_has_a_feature_timing_role() -> None:
    for field in CANONICAL_SCHEMA:
        assert isinstance(field.role, FeatureTiming)
        assert field.role is not FeatureTiming.UNKNOWN, field.name


def test_required_fields_match_the_outcome_contracts_complete_policy_columns() -> None:
    """The `required` flag is not editorial — it must equal exactly the union of structurally
    load-bearing identity/split columns and every outcome-contract column whose
    `MissingDataPolicy` is `COMPLETE`. Regenerating this set from the outcome contract directly
    (rather than hand-copying it) is what keeps this test a real cross-check, not a tautology."""
    # customer_price_eur is never a standalone OutcomeDefinition.column (it only appears embedded
    # in contribution_margin_rate's formula, "contribution_margin_eur / customer_price_eur"), but
    # that definition's own description documents it as expected-complete ("decision-time and
    # always positive... so the ratio is always defined") — real justification, not a guess.
    structural = {"booking_id", "customer_id", "booking_date", "currency", "customer_price_eur"}
    complete_outcome_columns = {
        definition.column
        for definition in OUTCOME_DEFINITIONS
        if definition.missing_data_policy is MissingDataPolicy.COMPLETE
        and definition.column in CANONICAL_FIELDS_BY_NAME
    }
    assert set(required_fields()) == structural | complete_outcome_columns


def test_repeat_purchase_is_deliberately_not_required() -> None:
    """MNAR-bounded outcome — its missingness is structurally meaningful, not a data-quality gap."""
    assert CANONICAL_FIELDS_BY_NAME["repeat_purchase_180d"].required is False


def test_primary_outcome_is_required() -> None:
    assert CANONICAL_FIELDS_BY_NAME["contribution_margin_eur"].required is True
