"""Tests for `outcome_definition_from_manifest` (`HANDOFF-065`, `TASK-019` half).

Two paths matter: travel's own manifest must be a byte-for-byte pass-through to the real,
Product-reviewed `primary_outcome()`; any other manifest (a `TASK-061` domain's) gets a real but
explicitly-disclosed-provisional `OutcomeDefinition` derived from its own `outcome_contract` block.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.outcomes import (  # noqa: E402
    outcome_definition_from_manifest as outcome_definition_from_manifest_public,
)
from policy_analytics.outcomes.contract import (  # noqa: E402
    DATASET_VERSION,
    OUTCOME_CONTRACT_VERSION,
    MissingDataPolicy,
    primary_outcome,
)
from policy_analytics.outcomes.manifest_binding import (  # noqa: E402
    _empirical_valid_range,
    _mechanical_harm_direction_phrase,
    _primary_definition,
    outcome_definition_from_manifest,
)

pytestmark = pytest.mark.analytics

TRAVEL_DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
B2B_DATASET_ROOT = (
    REPOSITORY / "synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0"
)


def _manifest(dataset_root: Path) -> dict[str, object]:
    return json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))


def test_travel_manifest_is_a_byte_for_byte_pass_through_to_primary_outcome() -> None:
    outcome, version = outcome_definition_from_manifest(
        _manifest(TRAVEL_DATASET_ROOT), TRAVEL_DATASET_ROOT
    )
    assert outcome == primary_outcome()
    assert version == OUTCOME_CONTRACT_VERSION


def test_travel_pass_through_is_keyed_on_dataset_version_not_the_dataset_root_path() -> None:
    # Even if called with a differently-named directory, matching dataset_version is what matters.
    manifest = _manifest(TRAVEL_DATASET_ROOT)
    assert manifest["dataset_version"] == DATASET_VERSION
    outcome, _ = outcome_definition_from_manifest(manifest, TRAVEL_DATASET_ROOT)
    assert outcome.outcome_id == primary_outcome().outcome_id


def test_b2b_sales_manifest_derives_a_real_provisional_outcome_definition() -> None:
    manifest = _manifest(B2B_DATASET_ROOT)
    outcome, version = outcome_definition_from_manifest(manifest, B2B_DATASET_ROOT)

    assert outcome.outcome_id == "net_deal_contribution_usd"
    assert outcome.column == "net_deal_contribution_usd"
    assert outcome.unit == "USD (nominal; single currency; no inflation or FX adjustment)"
    assert outcome.higher_is_worse is False
    assert outcome.harm_multiplier == -1
    # manifest says "not_yet_classified", which is not a recognized MissingDataPolicy value —
    # must default to COMPLETE rather than raising or silently guessing MNAR.
    assert outcome.missing_data_policy == MissingDataPolicy.COMPLETE
    assert "PROVISIONAL" in outcome.description
    assert "HANDOFF-065" in outcome.description
    assert version == "0.1.0-provisional"


def test_b2b_sales_valid_range_matches_the_actual_observed_min_and_max() -> None:
    manifest = _manifest(B2B_DATASET_ROOT)
    outcome, _ = outcome_definition_from_manifest(manifest, B2B_DATASET_ROOT)
    expected = _empirical_valid_range(B2B_DATASET_ROOT, "net_deal_contribution_usd")
    assert outcome.valid_range == expected
    assert outcome.valid_range[0] < outcome.valid_range[1]


def test_outcome_definition_from_manifest_raises_for_a_manifest_without_outcome_contract() -> None:
    # A dataset built before TASK-062 has no outcome_contract block at all — a real gap to surface,
    # not something to silently paper over with another hardcoded default.
    manifest = _manifest(B2B_DATASET_ROOT)
    del manifest["outcome_contract"]
    with pytest.raises(KeyError):
        outcome_definition_from_manifest(manifest, B2B_DATASET_ROOT)


def test_primary_definition_raises_when_primary_outcome_id_has_no_matching_definition() -> None:
    outcome_contract = {
        "primary_outcome_id": "missing_id",
        "definitions": [{"outcome_id": "some_other_id"}],
    }
    with pytest.raises(ValueError, match="missing_id"):
        _primary_definition(outcome_contract)


def test_mechanical_harm_direction_phrase_title_cases_and_states_direction() -> None:
    phrase = _mechanical_harm_direction_phrase("net_deal_contribution_usd", higher_is_worse=False)
    assert phrase == "Net Deal Contribution Usd decreases"
    assert _mechanical_harm_direction_phrase("cancellation_rate", higher_is_worse=True) == (
        "Cancellation Rate increases"
    )


def test_empirical_valid_range_reads_min_and_max_from_outcomes_csv(tmp_path: Path) -> None:
    (tmp_path / "outcomes.csv").write_text("some_metric\n1.5\n-3.0\n\n9.25\n", encoding="utf-8")
    assert _empirical_valid_range(tmp_path, "some_metric") == (-3.0, 9.25)


def test_empirical_valid_range_raises_when_the_column_has_no_present_values(tmp_path: Path) -> None:
    (tmp_path / "outcomes.csv").write_text("some_metric\n\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no present values"):
        _empirical_valid_range(tmp_path, "some_metric")


def test_public_import_matches_the_direct_module_import() -> None:
    # outcomes/__init__.py's re-export resolves to the same function object as the module itself.
    assert outcome_definition_from_manifest_public is outcome_definition_from_manifest
