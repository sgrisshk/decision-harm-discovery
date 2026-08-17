"""Regression tests for the cluster-bootstrap ordering fix (`HANDOFF-047`).

Synthetic, hand-constructed `ClusterCell` populations only — never real candidate data or
`hidden_ground_truth.json`. The defect and fix are both properties of `cluster_bootstrap_replicates`
alone: whether resampling by index is reproducible under a fixed seed when the *same* cluster
population arrives in a *different* dict-insertion order (exactly what an un-ordered Polars
`group_by` could do run-to-run without `maintain_order=True`).
"""

from __future__ import annotations

import random

import pytest
from policy_analytics.validation.apply import ClusterCell, cluster_bootstrap_replicates

pytestmark = pytest.mark.analytics

SEED = 20260813  # apply.py's own BOOTSTRAP_SEED, reused so this test means what it claims to


def _population() -> dict[str, ClusterCell]:
    """Cluster cells with distinguishable exposed-minus-comparison contributions, so resampling
    a different index would almost certainly change the replicate — a fix that merely happened
    not to disturb identical cells would pass by accident.
    """
    return {
        "cust_alpha": ClusterCell(
            exposed_sum=500.0, exposed_n=5, comparison_sum=100.0, comparison_n=5
        ),
        "cust_bravo": ClusterCell(
            exposed_sum=50.0, exposed_n=5, comparison_sum=400.0, comparison_n=5
        ),
        "cust_charlie": ClusterCell(
            exposed_sum=900.0, exposed_n=5, comparison_sum=10.0, comparison_n=5
        ),
        "cust_delta": ClusterCell(
            exposed_sum=20.0, exposed_n=5, comparison_sum=600.0, comparison_n=5
        ),
        "cust_echo": ClusterCell(
            exposed_sum=300.0, exposed_n=5, comparison_sum=250.0, comparison_n=5
        ),
    }


def _reordered(cells: dict[str, ClusterCell], order: list[str]) -> dict[str, ClusterCell]:
    """Same key/value pairs, rebuilt in a different insertion order — simulating what an
    un-ordered `group_by(...).agg(...)` could hand back across two otherwise-identical runs.
    """
    assert set(order) == set(cells)
    return {key: cells[key] for key in order}


def test_replicates_are_identical_across_differently_ordered_but_equal_populations() -> None:
    """The actual regression: same clusters, same seed, different dict-insertion order in →
    identical replicates out. Before the fix (`population = list(cells.values())`, unsorted),
    this would fail — see the paired demonstration below.
    """
    base = _population()
    shuffled = _reordered(
        base, ["cust_echo", "cust_alpha", "cust_delta", "cust_bravo", "cust_charlie"]
    )
    reversed_order = _reordered(base, list(reversed(list(base))))

    reps_base = cluster_bootstrap_replicates(base, reps=500, rng=random.Random(SEED))
    reps_shuffled = cluster_bootstrap_replicates(shuffled, reps=500, rng=random.Random(SEED))
    reps_reversed = cluster_bootstrap_replicates(reversed_order, reps=500, rng=random.Random(SEED))

    assert reps_base == reps_shuffled == reps_reversed


def test_old_unsorted_population_order_was_not_reproducible() -> None:
    """Formal demonstration of the defect HANDOFF-047 found: resampling by index
    (`rng.choices(population, k=len(population))`) over `list(a_dict.values())` is only
    reproducible under a fixed seed if the dict's own iteration order is fixed. Reproduce the old
    (pre-fix) call shape directly here — not by re-adding the bug to `apply.py` — to keep this a
    permanent proof of *why* the fix was necessary, independent of the current source.
    """
    base = _population()
    shuffled = _reordered(
        base, ["cust_delta", "cust_bravo", "cust_echo", "cust_charlie", "cust_alpha"]
    )

    def old_unsorted_replicates(
        cells: dict[str, ClusterCell], reps: int, rng: random.Random
    ) -> list[float]:
        population = list(cells.values())  # the pre-fix line, order = dict insertion order
        replicates: list[float] = []
        for _ in range(reps):
            sample = rng.choices(population, k=len(population))
            exposed_sum = sum(cell.exposed_sum for cell in sample)
            exposed_n = sum(cell.exposed_n for cell in sample)
            comparison_sum = sum(cell.comparison_sum for cell in sample)
            comparison_n = sum(cell.comparison_n for cell in sample)
            replicates.append(exposed_sum / exposed_n - comparison_sum / comparison_n)
        return replicates

    reps_base = old_unsorted_replicates(base, reps=500, rng=random.Random(SEED))
    reps_shuffled = old_unsorted_replicates(shuffled, reps=500, rng=random.Random(SEED))

    # Same clusters, same seed, only insertion order differs — the old approach diverges.
    assert reps_base != reps_shuffled


def test_point_estimate_is_order_independent_regardless_of_bootstrap_fix() -> None:
    """Sanity check on HANDOFF-047's own observation: point estimates (a straight sum over the
    *entire* population) never depended on order, before or after the fix — only resampling did.
    This is not a bootstrap call at all; it mirrors what `split_stats`'s combined-sample mean does.
    """
    base = _population()
    shuffled = _reordered(
        base, ["cust_charlie", "cust_echo", "cust_alpha", "cust_bravo", "cust_delta"]
    )

    def full_population_estimate(cells: dict[str, ClusterCell]) -> float:
        exposed_sum = sum(c.exposed_sum for c in cells.values())
        exposed_n = sum(c.exposed_n for c in cells.values())
        comparison_sum = sum(c.comparison_sum for c in cells.values())
        comparison_n = sum(c.comparison_n for c in cells.values())
        return exposed_sum / exposed_n - comparison_sum / comparison_n

    assert full_population_estimate(base) == full_population_estimate(shuffled)


def test_replicates_are_reproducible_across_repeated_calls_with_a_fresh_rng() -> None:
    """End-to-end reproducibility check matching HANDOFF-047's actual observed symptom: rerunning
    validation twice with the same `bootstrap_seed` must now produce byte-identical confidence
    intervals, not just byte-identical point estimates.
    """
    cells = _population()
    first = cluster_bootstrap_replicates(cells, reps=2000, rng=random.Random(SEED))
    second = cluster_bootstrap_replicates(
        dict(reversed(list(cells.items()))), reps=2000, rng=random.Random(SEED)
    )
    assert first == second
