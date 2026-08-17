import csv
import json
from pathlib import Path

import pytest
from policy_analytics.outcomes import (
    DATASET_IDENTITY_SHA256,
    DATASET_VERSION,
    DISCOVERY_CONTRACT,
    EXCLUDED_EXPLANATORY_CLASSIFICATIONS,
    OUTCOME_BY_ID,
    OUTCOME_DEFINITIONS,
    PRIMARY_OUTCOME_ID,
    DiscoveryStatisticalContract,
    GroupSummary,
    MissingDataPolicy,
    OutcomeRole,
    harm_score,
    historical_exposure,
    missingness_gap,
    mnar_bounds,
    primary_outcome,
    raw_difference,
    secondary_outcomes,
    summarize_group,
)
from policy_schemas.domain import FeatureTiming

pytestmark = pytest.mark.analytics

BENCHMARK_CSV = (
    Path(__file__).parents[2] / "synthetic_data" / "reference" / "travel_bookings_clean.csv"
)
ANALYTICAL_DATASET = Path(__file__).parents[2] / "synthetic_data" / "analytical" / DATASET_VERSION


def test_exactly_one_primary_outcome() -> None:
    primaries = [d for d in OUTCOME_DEFINITIONS if d.role is OutcomeRole.PRIMARY]
    assert len(primaries) == 1
    assert primaries[0].outcome_id == PRIMARY_OUTCOME_ID
    assert primary_outcome().outcome_id == PRIMARY_OUTCOME_ID
    assert all(d.role is OutcomeRole.SECONDARY for d in secondary_outcomes())


def test_primary_outcome_has_no_expected_missingness() -> None:
    assert primary_outcome().missing_data_policy is MissingDataPolicy.COMPLETE


def test_only_repeat_purchase_is_mnar_bounded() -> None:
    mnar = [
        d.outcome_id
        for d in OUTCOME_DEFINITIONS
        if d.missing_data_policy is MissingDataPolicy.MNAR_BOUNDED
    ]
    assert mnar == ["repeat_purchase_180d"]
    assert OUTCOME_BY_ID["repeat_purchase_180d"].role is OutcomeRole.SECONDARY


def test_harm_multiplier_matches_direction() -> None:
    # Good outcomes (higher is better): a decrease is harmful -> multiplier negates.
    assert OUTCOME_BY_ID["contribution_margin_eur"].harm_multiplier == -1
    assert OUTCOME_BY_ID["gross_profit_eur"].harm_multiplier == -1
    assert OUTCOME_BY_ID["repeat_purchase_180d"].harm_multiplier == -1
    # Bad outcomes (higher is worse): an increase is harmful -> multiplier keeps sign.
    assert OUTCOME_BY_ID["cancellation"].harm_multiplier == 1
    assert OUTCOME_BY_ID["refund_amount_eur"].harm_multiplier == 1
    assert OUTCOME_BY_ID["support_cost_eur"].harm_multiplier == 1


def test_decomposition_outcomes_reference_the_primary_outcome() -> None:
    for definition in OUTCOME_DEFINITIONS:
        if definition.decomposition_of is not None:
            assert definition.decomposition_of in OUTCOME_BY_ID


def test_definition_requires_core_fields() -> None:
    with pytest.raises(ValueError, match="id, column, unit"):
        OUTCOME_BY_ID["contribution_margin_eur"].__class__(
            outcome_id="",
            role=OutcomeRole.SECONDARY,
            column="x",
            unit="EUR",
            higher_is_worse=True,
            missing_data_policy=MissingDataPolicy.COMPLETE,
            description="x",
            valid_range=(0.0, 1.0),
            aggregation_rule="arithmetic_mean_of_present_values",
            harm_direction_phrase="x",
        )
    with pytest.raises(ValueError, match="aggregation_rule"):
        OUTCOME_BY_ID["contribution_margin_eur"].__class__(
            outcome_id="x",
            role=OutcomeRole.SECONDARY,
            column="x",
            unit="EUR",
            higher_is_worse=True,
            missing_data_policy=MissingDataPolicy.COMPLETE,
            description="x",
            valid_range=(0.0, 1.0),
            aggregation_rule="",
            harm_direction_phrase="x",
        )
    with pytest.raises(ValueError, match="valid_range"):
        OUTCOME_BY_ID["contribution_margin_eur"].__class__(
            outcome_id="x",
            role=OutcomeRole.SECONDARY,
            column="x",
            unit="EUR",
            higher_is_worse=True,
            missing_data_policy=MissingDataPolicy.COMPLETE,
            description="x",
            valid_range=(1.0, 0.0),
            aggregation_rule="arithmetic_mean_of_present_values",
            harm_direction_phrase="x",
        )


def test_group_summary_is_internally_consistent() -> None:
    outcome = primary_outcome()
    summary = summarize_group([10.0, None, 20.0, 30.0], outcome)
    assert summary.n_total == 4
    assert summary.n_present == 3
    assert summary.missing_count == 1
    assert summary.missing_rate == pytest.approx(0.25)
    assert summary.mean == pytest.approx(20.0)

    with pytest.raises(ValueError, match="cannot exceed"):
        GroupSummary(
            "x", n_total=1, n_present=1, missing_count=2, missing_rate=0.0, mean=None, variance=None
        )
    with pytest.raises(ValueError, match="empty group"):
        GroupSummary(
            "x", n_total=0, n_present=0, missing_count=0, missing_rate=0.0, mean=1.0, variance=None
        )


def test_raw_difference_and_harm_score_sign_convention() -> None:
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    exposed = summarize_group([100.0, 200.0], outcome)  # mean 150, worse
    comparison = summarize_group([300.0, 300.0], outcome)  # mean 300, better
    diff = raw_difference(exposed, comparison)
    assert diff == pytest.approx(-150.0)
    # Margin dropped -> harmful -> harm_score positive despite a negative raw difference.
    assert harm_score(diff, outcome) == pytest.approx(150.0)

    cancellation = OUTCOME_BY_ID["cancellation"]
    exposed_c = summarize_group([1.0, 1.0, 0.0], cancellation)  # higher cancellation rate
    comparison_c = summarize_group([0.0, 0.0, 0.0], cancellation)
    diff_c = raw_difference(exposed_c, comparison_c)
    assert diff_c > 0
    assert harm_score(diff_c, cancellation) == pytest.approx(diff_c)


def test_historical_exposure_matches_hand_computation() -> None:
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    exposed = summarize_group([100.0, 200.0, 300.0], outcome)  # mean 200, n=3
    comparison = summarize_group([300.0] * 10, outcome)
    # harm per record = 100, n_present = 3 -> exposure = 300
    assert historical_exposure(exposed, comparison, outcome) == pytest.approx(300.0)


def test_mismatched_outcome_ids_are_rejected() -> None:
    a = summarize_group([1.0], OUTCOME_BY_ID["contribution_margin_eur"])
    b = summarize_group([1.0], OUTCOME_BY_ID["gross_profit_eur"])
    with pytest.raises(ValueError, match="same outcome"):
        raw_difference(a, b)
    with pytest.raises(ValueError, match="same outcome"):
        missingness_gap(a, b)


def test_mnar_bounds_requires_the_declared_policy_and_unit_range() -> None:
    repeat = OUTCOME_BY_ID["repeat_purchase_180d"]
    with pytest.raises(ValueError, match="not an MNAR-bounded outcome"):
        mnar_bounds([1.0], OUTCOME_BY_ID["contribution_margin_eur"])
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        mnar_bounds([2.0], repeat)

    values = [1.0, 1.0, 0.0, None, None]  # 2 present-true, 1 present-false, 2 missing
    bounds = mnar_bounds(values, repeat)
    assert bounds.observed_only_mean == pytest.approx(2 / 3)
    assert bounds.pessimistic_mean == pytest.approx(2 / 5)
    assert bounds.optimistic_mean == pytest.approx(4 / 5)


def test_missingness_gap_is_symmetric() -> None:
    outcome = OUTCOME_BY_ID["repeat_purchase_180d"]
    exposed = summarize_group([1.0, None, None], outcome)
    comparison = summarize_group([1.0, 1.0, None, None], outcome)
    assert missingness_gap(exposed, comparison) == pytest.approx(
        missingness_gap(comparison, exposed)
    )


@pytest.mark.skipif(not BENCHMARK_CSV.exists(), reason="synthetic benchmark artifact not present")
def test_contract_matches_the_generated_benchmark() -> None:
    """The missing-data policy is an empirical claim about this dataset; keep it honest."""
    with BENCHMARK_CSV.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    for definition in OUTCOME_DEFINITIONS:
        if definition.decomposition_of == "contribution_margin_eur" and "/" in definition.column:
            continue  # derived ratio, not a stored column
        if definition.missing_data_policy is MissingDataPolicy.COMPLETE:
            missing = sum(1 for row in rows if row[definition.column] == "")
            assert missing == 0, f"{definition.outcome_id} was expected to have no missingness"

    repeat_missing = sum(1 for row in rows if row["repeat_purchase_180d"] == "")
    assert repeat_missing > 0, "repeat_purchase_180d was expected to have MNAR missingness"

    cancelled = [row for row in rows if row["cancellation"] == "True"]
    not_cancelled = [row for row in rows if row["cancellation"] == "False"]
    cancelled_missing_rate = sum(1 for row in cancelled if row["repeat_purchase_180d"] == "") / len(
        cancelled
    )
    not_cancelled_missing_rate = sum(
        1 for row in not_cancelled if row["repeat_purchase_180d"] == ""
    ) / len(not_cancelled)
    assert cancelled_missing_rate > not_cancelled_missing_rate, (
        "repeat_purchase_180d missingness was expected to depend on cancellation"
    )


@pytest.mark.skipif(
    not ANALYTICAL_DATASET.exists(), reason="delivered analytical dataset not present"
)
def test_contract_is_pinned_to_the_delivered_analytical_dataset() -> None:
    """This contract targets a specific dataset artifact, not just a column-name convention."""
    manifest = json.loads((ANALYTICAL_DATASET / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_version"] == DATASET_VERSION
    assert manifest["dataset_identity_sha256"] == DATASET_IDENTITY_SHA256
    assert manifest["clustering"]["column"] == "customer_id"

    outcome_columns = set(manifest["outcome_contract"]["available_columns"])
    assert outcome_columns == {d.column for d in OUTCOME_DEFINITIONS if d.column in outcome_columns}
    # Every outcome this contract defines from a stored column must actually be in outcomes.csv.
    for definition in OUTCOME_DEFINITIONS:
        if "/" not in definition.column:  # skip the derived ratio, not a stored column
            assert definition.column in outcome_columns

    missingness = json.loads((ANALYTICAL_DATASET / "missingness.json").read_text(encoding="utf-8"))
    assert missingness["overall"]["contribution_margin_eur"] == 0.0
    assert missingness["overall"]["repeat_purchase_180d"] > 0.0


def test_every_definition_has_a_valid_range_and_aggregation_rule() -> None:
    for definition in OUTCOME_DEFINITIONS:
        low, high = definition.valid_range
        assert low <= high
        assert definition.aggregation_rule
        assert definition.harm_direction_phrase


def test_primary_outcome_harm_direction_phrase_is_product_reviewed() -> None:
    assert primary_outcome().harm_direction_phrase == "Contribution margin drops"


def test_every_definition_does_not_allow_winsorization_at_discovery() -> None:
    for definition in OUTCOME_DEFINITIONS:
        assert definition.winsorization_allowed_at_discovery is False


def test_valid_range_rejects_low_greater_than_high() -> None:
    with pytest.raises(ValueError, match="valid_range"):
        OUTCOME_BY_ID["contribution_margin_eur"].__class__(
            outcome_id="x",
            role=OutcomeRole.SECONDARY,
            column="x",
            unit="EUR",
            higher_is_worse=True,
            missing_data_policy=MissingDataPolicy.COMPLETE,
            description="x",
            valid_range=(5.0, -5.0),
            aggregation_rule="arithmetic_mean_of_present_values",
            harm_direction_phrase="x",
        )


@pytest.mark.skipif(
    not ANALYTICAL_DATASET.exists(), reason="delivered analytical dataset not present"
)
def test_valid_ranges_bound_the_delivered_dataset() -> None:
    """valid_range is an empirical claim about the pinned dataset; keep it honest and non-loose."""
    outcomes_path = ANALYTICAL_DATASET / "outcomes.csv"
    with outcomes_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    boolean_columns = {"cancellation", "repeat_purchase_180d"}
    for definition in OUTCOME_DEFINITIONS:
        if "/" in definition.column or definition.column in boolean_columns:
            continue  # derived ratio (no stored column) or boolean (range is definitional [0, 1])
        values = [float(row[definition.column]) for row in rows if row[definition.column] != ""]
        low, high = definition.valid_range
        assert min(values) >= low, f"{definition.outcome_id} observed below its valid_range floor"
        assert max(values) <= high, (
            f"{definition.outcome_id} observed above its valid_range ceiling"
        )
        # The declared range should reflect the data, not be arbitrarily wider than observed.
        assert min(values) == pytest.approx(low, abs=0.01)
        assert max(values) == pytest.approx(high, abs=0.01)


def test_discovery_contract_shares_the_validation_contracts_support_floor() -> None:
    from policy_analytics.validation.contract import DEFAULT_THRESHOLDS

    assert DISCOVERY_CONTRACT.min_support_records == DEFAULT_THRESHOLDS.min_exposed_records


def test_discovery_contract_fit_split_is_not_a_diagnostic_split() -> None:
    assert DISCOVERY_CONTRACT.search_fit_split == "development"
    assert DISCOVERY_CONTRACT.search_fit_split not in DISCOVERY_CONTRACT.diagnostic_only_splits
    assert set(DISCOVERY_CONTRACT.diagnostic_only_splits) == {"validation", "future_holdout"}

    with pytest.raises(ValueError, match="fit split"):
        DiscoveryStatisticalContract(
            contract_version="x",
            search_fit_split="development",
            diagnostic_only_splits=("development",),
            min_support_records=50,
            excluded_explanatory_classifications=frozenset(),
            primary_outcome_missing_handling="x",
            mnar_outcome_missing_handling="x",
            causal_language_note="x",
        )
    with pytest.raises(ValueError, match="positive"):
        DiscoveryStatisticalContract(
            contract_version="x",
            search_fit_split="development",
            diagnostic_only_splits=("validation",),
            min_support_records=0,
            excluded_explanatory_classifications=frozenset(),
            primary_outcome_missing_handling="x",
            mnar_outcome_missing_handling="x",
            causal_language_note="x",
        )


def test_excluded_explanatory_classifications_covers_every_non_decision_time_timing() -> None:
    assert FeatureTiming.DECISION_TIME.value not in EXCLUDED_EXPLANATORY_CLASSIFICATIONS
    for timing in FeatureTiming:
        if timing is not FeatureTiming.DECISION_TIME:
            assert timing.value in EXCLUDED_EXPLANATORY_CLASSIFICATIONS


@pytest.mark.skipif(
    not ANALYTICAL_DATASET.exists(), reason="delivered analytical dataset not present"
)
def test_excluded_classifications_match_the_delivered_feature_manifest() -> None:
    """features.csv must contain only DECISION_TIME columns, matching this contract's exclusion."""
    excluded_manifest = json.loads(
        (ANALYTICAL_DATASET / "excluded_columns_manifest.json").read_text(encoding="utf-8")
    )
    for column in excluded_manifest["excluded_from_feature_matrix"]:
        assert column["classification"].lower() in EXCLUDED_EXPLANATORY_CLASSIFICATIONS
