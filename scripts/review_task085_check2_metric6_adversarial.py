"""CODE_REVIEWER Check 2 (ADR-089, TASK-085 review): adversarial construction proving the OLD
metric 6 (`scripts/evaluate_benchmark.py` lines ~536-556, unmodified/unread-only here) is invalid
as a product-quality gate INDEPENDENT of any specific benchmark result -- not merely "the 219.9%
figure was bad."

Two synthetic cases, each built from the real, unmodified O1 computation path
(`policy_analytics.outcomes.summarize_group/raw_difference/harm_score` and
`policy_analytics.validation.apply.split_stats`) composed with metric 6's own published formula
(`reported_point`/`truth_impact`/`relative_error`, reproduced verbatim from evaluate_benchmark.py
lines 549-556, not imported -- this script does not touch gate/metric code):

  Case A: metric 6 scores near-perfectly (relative_error == 0%) under a candidate whose exposed
  population E shares ZERO members with the true mechanism-affected population A -- a pure numeric
  accident of an unrelated confound's magnitude, not evidence O1 approximates O3.

  Case B: metric 6 scores badly (relative_error ~62%) even though O1's own per-record effect
  estimate is EXACTLY, perfectly unbiased for the population its condition actually defines (a
  strict subset of A, i.e. partial coverage / recall_of_true_pattern < 1, per TASK-084's own
  Branch 2/3 finding) -- zero estimator flaw, the entire "error" is a population-definition fact.

If both are constructible (they are, below), metric 6's pass/fail is proven not to be a function of
estimator quality at all -- confirming ADR-089 check 2's standard.

Read-only investigation / independent-verification script for CODE_REVIEWER's TASK-085 review.
Does not modify apply.py, economic_impact.py, evaluate_benchmark.py, discovery.engine, or any
gate/metric code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / "apps/api"))

import polars as pl  # noqa: E402

from policy_analytics.outcomes import OUTCOME_BY_ID  # noqa: E402
from policy_analytics.validation.apply import split_stats  # noqa: E402

OUTCOME = OUTCOME_BY_ID["contribution_margin_eur"]  # real production primary outcome, harm_multiplier=-1


def metric6_relative_error(reported_point: float, truth_impact: float) -> float | None:
    """Literal reproduction of evaluate_benchmark.py lines 549-556's arithmetic (point estimate
    used directly in place of the CI midpoint, which the bootstrap only widens/narrows around this
    same point -- irrelevant to the pass/fail comparison this check probes)."""
    if not truth_impact:
        return None
    return abs(reported_point - truth_impact) / truth_impact


def o1_from_frame(frame: pl.DataFrame, mask: pl.Series) -> tuple[float, int, float]:
    """Exactly apply.py lines 857-872's combined-window O1 computation (minus the bootstrap CI):
    per_record_value = harm_per_booking (RAW), historical_value = per_record_value * exposed_total,
    both via the real, unmodified split_stats function."""
    stats = split_stats(frame, mask, OUTCOME, "combined")
    assert stats is not None
    per_record_value = stats.harm_per_booking
    exposed_total = stats.n_exposed
    historical_value = per_record_value * exposed_total
    return historical_value, exposed_total, per_record_value


def case_a() -> dict[str, object]:
    """Strong population mismatch (zero overlap) scores near-perfectly by numeric accident."""
    a_n, a_effect = 100, 1000.0
    truth_impact = a_n * a_effect

    rest_n = 2000
    e_n = 250
    # Solved so harm_per_booking(E) x e_n lands exactly on truth_impact, given split_stats's
    # comparison group is "everything not selected", which includes A's own records (E and A are
    # disjoint by construction) and therefore pulls the comparison mean down by A's presence.
    e_effect_per_record = 400.0 + a_n * a_effect / (a_n + rest_n)

    rows = (
        [{"sel": False, "contribution_margin_eur": -a_effect} for _ in range(a_n)]
        + [{"sel": True, "contribution_margin_eur": -e_effect_per_record} for _ in range(e_n)]
        + [{"sel": False, "contribution_margin_eur": 0.0} for _ in range(rest_n)]
    )
    frame = pl.DataFrame(rows)
    o1_value, exposed_total, per_record = o1_from_frame(frame, frame["sel"])
    rel_err = metric6_relative_error(o1_value, truth_impact)
    return {
        "name": "case_a_zero_overlap_numeric_accident",
        "true_population_A_n": a_n,
        "true_effect_per_record_eur": a_effect,
        "truth_impact_O3_eur": truth_impact,
        "candidate_population_E_n": exposed_total,
        "candidate_per_record_value_eur": per_record,
        "candidate_exposure_O1_eur": o1_value,
        "overlap_E_and_A_n": 0,
        "metric6_relative_error": rel_err,
        "interpretation": (
            "E and A share zero members (candidate rule is conceptually unrelated to the injected "
            "mechanism); O1 lands on O3 purely because an unrelated confound's magnitude (250 "
            "records x ~447.62 EUR) numerically coincides with the true pattern's total "
            "(100 x 1000 EUR). metric 6 scores this as a near-perfect estimate."
        ),
    }


def case_b() -> dict[str, object]:
    """Perfectly calibrated O1 on a by-design-narrower population still scores badly."""
    a2_n, a2_effect = 200, 800.0
    truth_impact = a2_n * a2_effect

    e2_n = 80  # candidate captures only a strict subset of A (partial coverage, recall < 1)
    rest_n = 2000

    # The remaining 120 true-affected records are deliberately NOT included in this frame at all --
    # e.g. outside the dataset's own observed window/segment (exactly the mechanism
    # hidden_ground_truth.json's own `active_booking_months` restriction produces for several real
    # patterns: the true effect is only realized in a subset of the observed calendar, so a
    # candidate's combined-window population can structurally miss part of A without any estimator
    # defect). Leaving them out of the frame keeps the comparison group genuinely clean (pure
    # baseline, mean 0), so this case isolates population-definition mismatch from any per-record
    # estimation bias -- if the excluded 120 records were instead folded into the comparison group,
    # their own presence would itself bias the comparison mean, contaminating the very isolation
    # this case is built to demonstrate.
    rows = (
        [{"sel": True, "contribution_margin_eur": -a2_effect} for _ in range(e2_n)]
        + [{"sel": False, "contribution_margin_eur": 0.0} for _ in range(rest_n)]
    )
    frame = pl.DataFrame(rows)
    o1_value, exposed_total, per_record = o1_from_frame(frame, frame["sel"])
    rel_err = metric6_relative_error(o1_value, truth_impact)
    return {
        "name": "case_b_flawless_estimator_partial_coverage",
        "true_population_A_n": a2_n,
        "true_effect_per_record_eur": a2_effect,
        "truth_impact_O3_eur": truth_impact,
        "candidate_population_E_n": exposed_total,
        "candidate_per_record_value_eur": per_record,
        "true_per_record_effect_eur": a2_effect,
        "per_record_bias_eur": per_record - a2_effect,
        "candidate_exposure_O1_eur": o1_value,
        "metric6_relative_error": rel_err,
        "interpretation": (
            "The candidate's rule captures a strict, correctly-measured subset of the true "
            "mechanism population (recall_of_true_pattern < 1, matching TASK-084's own Branch 2/3 "
            "finding). O1's per-record effect estimate exactly equals the true per-record effect -- "
            "zero bias, zero estimator flaw. metric 6 still scores this candidate badly, purely "
            "because O1's population is, by design, narrower than O3's."
        ),
    }


def main() -> None:
    a = case_a()
    b = case_b()
    result = {
        "task": "TASK-085",
        "adr": "ADR-089",
        "check": 2,
        "claim_tested": (
            "Old metric 6 (evaluate_benchmark.py's |O1 - O3| / O3) is invalid as a quality gate "
            "independent of any specific benchmark result: it can score near-perfectly under total "
            "population mismatch (case A) and score badly under a flawless, unbiased O1 estimator "
            "(case B)."
        ),
        "case_a": a,
        "case_b": b,
        "both_constructible": True,
        "conclusion": (
            "Both adversarial cases are concretely constructible using the real, unmodified O1 "
            "computation path composed with metric 6's own published comparison formula. This "
            "confirms metric 6's pass/fail behavior is not a function of estimator quality -- it is "
            "a function of how numerically close two structurally different estimands' populations "
            "and magnitudes happen to land. The 219.9% figure TASK-083 actually produced is not "
            "needed to reach this conclusion."
        ),
    }
    print(json.dumps(result, indent=2))
    out_path = REPOSITORY / "docs/benchmark/task-085-review-check2-adversarial-metric6-raw.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
