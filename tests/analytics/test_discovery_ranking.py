import pytest
from policy_analytics.discovery.ranking import (
    CandidateSignals,
    RankingWeights,
    rank_candidates,
)

pytestmark = pytest.mark.analytics


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        RankingWeights(
            economic_impact=0.5, support=0.5, stability=0.5, actionability=0.0, novelty=0.0
        )


def test_rank_score_is_not_economic_impact_alone() -> None:
    # An "anchor" candidate sets the batch's economic/support ceiling so A is not automatically
    # normalized to 1.0 just for being the largest of two. A: large economic impact, but
    # unstable and review-required. B: smaller economic impact, but fully stable and directly
    # actionable. A naive "sort by economic impact" ranking would put A ahead of B; this one must
    # not, because stability and actionability outweigh A's remaining economic/support edge.
    anchor = CandidateSignals(
        candidate_id="CAND-ANCHOR",
        economic_impact=200_000.0,
        support=0.5,
        stability=0.0,
        actionability=0.35,
        exposed_row_ids=frozenset(range(2000, 2100)),
    )
    a = CandidateSignals(
        candidate_id="CAND-A",
        economic_impact=100_000.0,
        support=0.3,
        stability=0.0,
        actionability=0.35,
        exposed_row_ids=frozenset(range(0, 100)),
    )
    b = CandidateSignals(
        candidate_id="CAND-B",
        economic_impact=20_000.0,
        support=0.1,
        stability=1.0,
        actionability=1.0,
        exposed_row_ids=frozenset(range(1000, 1050)),
    )
    ranked = rank_candidates([anchor, a, b])
    by_id = {candidate.candidate_id: candidate for candidate in ranked}
    assert by_id["CAND-B"].rank_score > by_id["CAND-A"].rank_score
    assert by_id["CAND-B"].rank < by_id["CAND-A"].rank


def test_missing_stability_is_penalized_not_treated_as_passing() -> None:
    stable = CandidateSignals(
        candidate_id="CAND-STABLE",
        economic_impact=50_000.0,
        support=0.2,
        stability=1.0,
        actionability=1.0,
        exposed_row_ids=frozenset(range(0, 50)),
    )
    unknown = CandidateSignals(
        candidate_id="CAND-UNKNOWN",
        economic_impact=50_000.0,
        support=0.2,
        stability=None,
        actionability=1.0,
        exposed_row_ids=frozenset(range(100, 150)),
    )
    ranked = rank_candidates([stable, unknown])
    by_id = {candidate.candidate_id: candidate for candidate in ranked}
    assert by_id["CAND-UNKNOWN"].stability_missing is True
    assert by_id["CAND-UNKNOWN"].components.stability == 0.0
    assert by_id["CAND-STABLE"].rank_score > by_id["CAND-UNKNOWN"].rank_score
    assert by_id["CAND-STABLE"].rank == 1


def test_redundant_population_scores_lower_novelty_than_distinct_one() -> None:
    base = CandidateSignals(
        candidate_id="CAND-BASE",
        economic_impact=10_000.0,
        support=0.2,
        stability=0.5,
        actionability=1.0,
        exposed_row_ids=frozenset(range(0, 100)),
    )
    duplicate = CandidateSignals(
        candidate_id="CAND-DUPLICATE",
        economic_impact=10_000.0,
        support=0.2,
        stability=0.5,
        actionability=1.0,
        exposed_row_ids=frozenset(range(0, 100)),
    )
    distinct = CandidateSignals(
        candidate_id="CAND-DISTINCT",
        economic_impact=10_000.0,
        support=0.2,
        stability=0.5,
        actionability=1.0,
        exposed_row_ids=frozenset(range(500, 600)),
    )
    ranked = rank_candidates([base, duplicate, distinct])
    by_id = {candidate.candidate_id: candidate for candidate in ranked}
    assert by_id["CAND-BASE"].components.novelty == 0.0
    assert by_id["CAND-DUPLICATE"].components.novelty == 0.0
    assert by_id["CAND-DISTINCT"].components.novelty == 1.0
    assert by_id["CAND-DISTINCT"].rank_score > by_id["CAND-BASE"].rank_score


def test_ties_break_deterministically_on_candidate_id() -> None:
    identical_kwargs = {
        "economic_impact": 1_000.0,
        "support": 0.1,
        "stability": 0.5,
        "actionability": 1.0,
        "exposed_row_ids": frozenset({1, 2, 3}),
    }
    z = CandidateSignals(candidate_id="CAND-Z", **identical_kwargs)
    a = CandidateSignals(candidate_id="CAND-A", **identical_kwargs)
    ranked = rank_candidates([z, a])
    assert [candidate.candidate_id for candidate in ranked] == ["CAND-A", "CAND-Z"]


def test_extra_warnings_beyond_the_standard_one_reduce_score() -> None:
    plain = CandidateSignals(
        candidate_id="CAND-PLAIN",
        economic_impact=1_000.0,
        support=0.1,
        stability=0.5,
        actionability=1.0,
        exposed_row_ids=frozenset({1, 2, 3}),
        warning_count=1,
    )
    warned = CandidateSignals(
        candidate_id="CAND-WARNED",
        economic_impact=1_000.0,
        support=0.1,
        stability=0.5,
        actionability=1.0,
        exposed_row_ids=frozenset({4, 5, 6}),
        warning_count=3,
    )
    ranked = rank_candidates([plain, warned])
    by_id = {candidate.candidate_id: candidate for candidate in ranked}
    assert by_id["CAND-PLAIN"].components.warning_penalty == 0.0
    assert by_id["CAND-WARNED"].components.warning_penalty > 0.0
    assert by_id["CAND-PLAIN"].rank_score > by_id["CAND-WARNED"].rank_score


def test_empty_input_returns_empty_output() -> None:
    assert rank_candidates([]) == ()


def test_rank_is_one_indexed_and_contiguous() -> None:
    signals = [
        CandidateSignals(
            candidate_id=f"CAND-{i}",
            economic_impact=float(i),
            support=0.1,
            stability=0.5,
            actionability=1.0,
            exposed_row_ids=frozenset({i}),
        )
        for i in range(1, 5)
    ]
    ranked = rank_candidates(signals)
    assert [candidate.rank for candidate in ranked] == [1, 2, 3, 4]
