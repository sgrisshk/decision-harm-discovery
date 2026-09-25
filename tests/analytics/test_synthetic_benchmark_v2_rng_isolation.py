"""TASK-107 Phase 2a: RNG isolation of the v2 generator (FC2/FC3 prerequisite).

The targets below are TEST-ONLY fixtures, not v2 targets (those are designed in Phase 2b).
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import csv
import random
from pathlib import Path

import pytest
from policy_analytics import synthetic_benchmark as v1
from policy_analytics import synthetic_benchmark_v2 as v2

pytestmark = pytest.mark.analytics

REPOSITORY = Path(__file__).resolve().parents[2]
SEEDS = (1001, 1002, 20260813)
ROWS = 2500  # smaller than 10,000 to keep the suite fast; full size is covered separately

_HIGH = v2.TargetDose(410.0, 1.05, 0.75)


def _t_high(cov: v2.Covariates) -> bool:
    return bool(cov["customer_segment"] == "corporate" and cov["destination"] == "Lisbon")


def _t_month(cov: v2.Covariates) -> bool:
    return bool(cov["booking_month"] in (1, 2, 12) and cov["installments"] >= 2)


def _t_broad(cov: v2.Covariates) -> bool:
    return bool(cov["acquisition_channel"] == "referral")


TARGETS_A = (v2.TargetSpec("X1", "corporate AND Lisbon", _t_high, _HIGH),)
TARGETS_B = (
    v2.TargetSpec("X1", "corporate AND Lisbon", _t_high, _HIGH),
    v2.TargetSpec("X2", "month AND installments", _t_month, v2.TargetDose(300.0, 0.75, 0.5)),
    v2.TargetSpec("X3", "referral", _t_broad, v2.TargetDose(600.0, 2.5, 1.5)),
)


def _cov_bytes(draw: v2.V2Draw) -> bytes:
    return "\n".join(
        "|".join(repr(row[c]) for c in v2.COVARIATE_COLUMNS) for row in draw.rows
    ).encode()


@pytest.mark.parametrize("seed", SEEDS)
def test_covariates_identical_across_target_sets(seed: int) -> None:
    config = v2.V2Config(seed=seed, row_count=ROWS)
    none = v2.generate_v2(config, ())
    a = v2.generate_v2(config, TARGETS_A)
    b = v2.generate_v2(config, TARGETS_B)
    assert _cov_bytes(none) == _cov_bytes(a) == _cov_bytes(b)
    assert len(b.memberships["X3"]) > 0
    assert len(b.memberships["X1"]) > 0


@pytest.mark.parametrize("seed", SEEDS)
def test_zero_target_covariates_equal_v1_generator(seed: int) -> None:
    config = v2.V2Config(seed=seed, row_count=ROWS)
    draw = v2.generate_v2(config, ())
    rng = random.Random(seed)
    v1_rows = [v1._generate_row(i, rng, config.v1_config())[0] for i in range(ROWS)]
    for mine, theirs in zip(draw.rows, v1_rows, strict=True):
        assert all(mine[c] == theirs[c] for c in v2.COVARIATE_COLUMNS)


def test_zero_target_covariates_equal_committed_v1_csv() -> None:
    path = REPOSITORY / "synthetic_data/reference/travel_bookings_clean.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        committed = list(csv.DictReader(handle))
    assert len(committed) == v1.ROW_COUNT
    draw = v2.generate_v2(v2.V2Config(seed=v1.SEED, row_count=len(committed)), ())
    for mine, theirs in zip(draw.rows, committed, strict=True):
        for c in v2.COVARIATE_COLUMNS:
            assert str(mine[c]) == theirs[c], c


def test_outcomes_change_only_on_rows_a_target_touches() -> None:
    config = v2.V2Config(seed=1001, row_count=ROWS)
    none = v2.generate_v2(config, ())
    b = v2.generate_v2(config, TARGETS_B)
    touched = {i for ids in b.memberships.values() for i in ids}
    changed = 0
    for r0, r1 in zip(none.rows, b.rows, strict=True):
        if str(r0["booking_id"]) not in touched:
            assert r0 == r1
        elif any(r0[c] != r1[c] for c in v2.OUTCOME_COLUMNS):
            changed += 1
    assert changed > 0


def test_outcomes_not_reproduced_from_v1_even_with_zero_targets() -> None:
    """Documented non-reproduction: outcome columns come from stream B and v1's nine patterns are
    absent, so zero-target outcomes differ from v1's realised values."""
    draw = v2.generate_v2(v2.V2Config(seed=v1.SEED, row_count=500), ())
    path = REPOSITORY / "synthetic_data/reference/travel_bookings_clean.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        committed = list(csv.DictReader(handle))[:500]
    differing = sum(
        str(m["additional_cost_eur"]) != t["additional_cost_eur"]
        for m, t in zip(draw.rows, committed, strict=True)
    )
    assert differing > 400


def test_outcome_stream_is_a_pure_function_of_seed_and_index() -> None:
    assert v2.outcome_rng(7, 3).random() == v2.outcome_rng(7, 3).random()
    assert v2.outcome_rng(7, 3).random() != v2.outcome_rng(7, 4).random()
    assert v2.outcome_rng(7, 3).random() != v2.outcome_rng(8, 3).random()


def test_stream_a_is_unaffected_by_targets_at_full_size() -> None:
    config = v2.V2Config(seed=1003)
    assert config.row_count == 10_000
    none = v2.generate_v2(config, ())
    b = v2.generate_v2(config, TARGETS_B)
    assert _cov_bytes(none) == _cov_bytes(b)


def test_duplicate_target_ids_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        v2.generate_v2(v2.V2Config(seed=1, row_count=10), (TARGETS_A[0], TARGETS_A[0]))
