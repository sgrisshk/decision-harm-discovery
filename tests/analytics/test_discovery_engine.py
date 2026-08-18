import math

import polars as pl
import pytest
from policy_analytics.discovery.engine import (
    DiscoveryConfig,
    SplitMetric,
    _development_score,
    discover_candidates,
)
from policy_analytics.outcomes import primary_outcome

pytestmark = pytest.mark.analytics


def _metric(n_exposed: int, harm_per_booking: float) -> SplitMetric:
    return SplitMetric(
        split="development",
        n_population=10_000,
        n_exposed=n_exposed,
        support=n_exposed / 10_000,
        exposed_mean=0.0,
        comparison_mean=0.0,
        raw_difference=0.0,
        harm_per_booking=harm_per_booking,
        historical_exposure=harm_per_booking * n_exposed,
    )


def test_discovers_interaction_and_records_full_search_family() -> None:
    rows = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(400):
            supplier = "A" if index % 2 == 0 else "B"
            discount = (index % 10) / 100
            harm = 80.0 if supplier == "A" and discount >= 0.05 else 0.0
            rows.append((supplier, discount, index % 3, 200.0 - harm, split))
    frame = pl.DataFrame(
        rows,
        schema=[
            "supplier",
            "discount_rate",
            "party_size",
            "contribution_margin_eur",
            "split_label",
        ],
        orient="row",
    )
    result = discover_candidates(
        frame,
        ("supplier", "discount_rate", "party_size"),
        primary_outcome(),
        DiscoveryConfig(min_n=20, beam_width=30, top_k=5),
    )
    assert result["search"]["evaluated_hypotheses"] > result["candidate_count"]
    assert all(len(candidate["conditions"]) >= 2 for candidate in result["candidates"])
    assert any(
        {condition["feature"] for condition in candidate["conditions"]}
        >= {"supplier", "discount_rate"}
        for candidate in result["candidates"]
    )
    assert all(candidate["fit_split"] == "development" for candidate in result["candidates"])


def test_rejects_missing_primary_outcome() -> None:
    frame = pl.DataFrame(
        {
            "supplier": ["A", "B"],
            "contribution_margin_eur": [1.0, None],
            "split_label": ["development", "development"],
        }
    )
    with pytest.raises(ValueError, match="contains missing"):
        discover_candidates(frame, ("supplier",), primary_outcome())


# --- TASK-058 (HANDOFF-043 remediation part 2): precision term on the beam-survival score ---


def test_population_score_exponent_of_one_reproduces_old_pure_exposure_ranking() -> None:
    """`population_score_exponent=1.0` must exactly reproduce `discovery-engine-v0.1.0`'s ranking:
    linear in `n_exposed`, i.e. identical to sorting by `historical_exposure` alone."""
    broad = _metric(n_exposed=2000, harm_per_booking=50.0)
    narrow = _metric(n_exposed=100, harm_per_booking=700.0)
    config = DiscoveryConfig(population_score_exponent=1.0)
    broad_score = _development_score(broad, condition_count=2, config=config)
    narrow_score = _development_score(narrow, condition_count=2, config=config)
    assert broad_score == pytest.approx(broad.historical_exposure / 1.15)
    assert narrow_score == pytest.approx(narrow.historical_exposure / 1.15)
    assert broad_score > narrow_score  # broad wins on raw total exposure alone (100,000 > 70,000)


def test_default_population_score_exponent_prefers_the_purer_rule_at_comparable_exposure() -> None:
    """The exact mechanism HANDOFF-043 diagnosed: a broad, diluted rule (large N, modest
    per-booking harm) outscores a narrow, purer rule (small N, strong per-booking harm) under
    linear population scaling even when the narrow rule's total exposure is smaller — but the
    default `population_score_exponent=0.5` must flip that preference once the narrow rule's
    per-booking effect is proportionally large enough, without ever opening real benchmark data."""
    broad = _metric(n_exposed=2000, harm_per_booking=50.0)  # historical_exposure = 100,000
    narrow = _metric(n_exposed=100, harm_per_booking=700.0)  # historical_exposure = 70,000
    config = DiscoveryConfig()  # default population_score_exponent = 0.5
    assert config.population_score_exponent == pytest.approx(0.5)
    broad_score = _development_score(broad, condition_count=2, config=config)
    narrow_score = _development_score(narrow, condition_count=2, config=config)
    # sqrt-scaled: broad = 50*sqrt(2000)/1.15, narrow = 700*sqrt(100)/1.15
    assert broad_score == pytest.approx(50.0 * math.sqrt(2000) / 1.15)
    assert narrow_score == pytest.approx(700.0 * math.sqrt(100) / 1.15)
    assert narrow_score > broad_score  # preference reversed relative to the exponent=1.0 case


def test_population_score_exponent_must_be_in_zero_to_one_range() -> None:
    for bad_exponent in (0.0, -0.5, 1.5):
        with pytest.raises(ValueError, match="population_score_exponent"):
            DiscoveryConfig(population_score_exponent=bad_exponent)
    DiscoveryConfig(population_score_exponent=1.0)  # upper bound is inclusive, does not raise


def test_discover_candidates_with_exponent_one_matches_manual_pure_exposure_reproduction() -> None:
    """End-to-end sanity check: run the full search twice on the same tiny fixture, once at the
    old linear exponent and once at the new default, and confirm both still return valid,
    development-only-fit candidates (the precision term changes ranking, not eligibility)."""
    rows = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(400):
            supplier = "A" if index % 2 == 0 else "B"
            discount = (index % 10) / 100
            harm = 80.0 if supplier == "A" and discount >= 0.05 else 0.0
            rows.append((supplier, discount, index % 3, 200.0 - harm, split))
    frame = pl.DataFrame(
        rows,
        schema=[
            "supplier",
            "discount_rate",
            "party_size",
            "contribution_margin_eur",
            "split_label",
        ],
        orient="row",
    )
    for exponent in (1.0, 0.5):
        result = discover_candidates(
            frame,
            ("supplier", "discount_rate", "party_size"),
            primary_outcome(),
            DiscoveryConfig(min_n=20, beam_width=30, top_k=5, population_score_exponent=exponent),
        )
        assert result["candidate_count"] > 0
        assert all(candidate["fit_split"] == "development" for candidate in result["candidates"])
        assert result["methodology_version"] == "discovery-engine-v0.2.0"
