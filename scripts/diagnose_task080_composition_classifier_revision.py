"""TASK-080 revision (`ADR-075`): asymmetric interaction/confound classifier form tests, including
the mandatory proxy-confounding ladder. **DESIGN-ONLY.** No `discovery.engine`, `apply.py`, or
gate code is modified. This script calls the real, unmodified
`policy_analytics.validation.apply._stratified_adjustment`, the real
`DEFAULT_THRESHOLDS.max_adjusted_attenuation`/`min_confounder_stratum_coverage`, and the real
`policy_analytics.validation.grading.normal_approx_two_sided_p` throughout — the leave-one-out
attenuation/coverage mechanism from the reviewed design (`docs/analytics/task-080-candidate-
composition-safety-design.md` §4/§8.1) is reused verbatim, not reimplemented. What is new here is
the *classifier's* interaction-side decision rule (the subject of this revision) plus the synthetic
DGPs used to test it.

**Revised classifier under test (see the design document's revised §6/§8.1 for the full
specification and rationale):**

  - `confound_like`: unchanged from the reviewed design — coverage clears the floor, the adjusted
    effect keeps the raw sign, and attenuation exceeds `max_adjusted_attenuation`. This branch was
    never the review's finding of a defect and is not touched.
  - `interaction_like`: **no longer the residual case.** It now requires its own positive evidence,
    via two signals investigated empirically per `ADR-075`:
      1. **Stratum-contrast heterogeneity** — does `base_i`'s own effect, recomputed separately
         within `Ci`'s two levels (the same "recompute within each level of a covariate" pattern
         `G09` already uses, applied here to the leave-one-out atom instead of a `G06`-selected
         covariate), show a statistically credible gap? Tested via a closed-form Wald test
         (`normal_approx_two_sided_p`, the same function `G05` already uses in production, not a
         new resampling procedure) rather than a bootstrap, for the same resolution reason
         `grading.py` already documents for `G05`.
      2. **Consistency under threshold perturbation** — does that contrast survive a small,
         G12-style one-bin move of `Ci`'s own threshold (same sign, and at least
         `(1 - max_adjusted_attenuation)` of the production-threshold magnitude retained at both a
         lower and a higher perturbed threshold)? This is the ADR's "consistency across admissible
         partitions/threshold perturbations" candidate signal.
  - `indeterminate`: everything else, including — critically — the case that used to fall through
    to `interaction_like` by default: low attenuation with no positive heterogeneity evidence.

  A third and fourth candidate signal the ADR names (`stability under an independent
  parameterization`; a `nested base+atom vs. base+atom+interaction model comparison`) were
  evaluated analytically, not assumed sufficient or skipped: in this check's own leave-one-out
  design (a saturated 2x2 T x Ci contingency table, no additional covariates), an OLS interaction
  coefficient and the nested-model F-test both reduce *algebraically* to the identical
  difference-in-differences quantity signal 1 already computes — see `_verify_ols_redundancy`
  below, which checks this numerically to machine precision on real generated data rather than
  asserting it from first principles alone. They were not used as a second, independent signal
  because they are not independent of signal 1 in this design; genuine independence instead comes
  from re-partitioning the same data (signal 2's threshold perturbation), which a saturated-design
  regression cannot supply since it is a different partition, not a different functional form.

Usage:
  uv run python scripts/diagnose_task080_composition_classifier_revision.py
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402

from policy_analytics.outcomes.contract import (  # noqa: E402
    MissingDataPolicy,
    OutcomeDefinition,
    OutcomeRole,
)
from policy_analytics.validation.apply import _stratified_adjustment  # noqa: E402
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS  # noqa: E402
from policy_analytics.validation.grading import normal_approx_two_sided_p  # noqa: E402

ALPHA = 0.002  # deliberately stricter than a bare (1 - confidence_level); see classify_atom's docstring
STABILITY_RETENTION_FLOOR = 1.0 - DEFAULT_THRESHOLDS.max_adjusted_attenuation  # 0.50, reused, not new
THRESHOLD_STEP = 0.15  # interior perturbation step on the synthetic proxy score's own [-0.5, 1.5) scale

OUTCOME = OutcomeDefinition(
    outcome_id="synthetic_task080_metric",
    role=OutcomeRole.PRIMARY,
    column="y",
    unit="unit",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description=(
        "Neutral synthetic outcome for TASK-080's revised classifier form tests (ADR-075). "
        "Invented; unrelated to any real dataset or domain in this repository."
    ),
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Value increases",
)


# =================================================================================================
# Synthetic DGP generators — all known-by-construction, no ground-truth/trap identity referenced.
# =================================================================================================


def _proxy_column(rng: random.Random, truth: list[int]) -> list[float]:
    """A continuous proxy score whose threshold-0.5 binarization recovers `truth` exactly, with a
    G12-style perturbable margin: base in {0, 1} plus uniform(-0.5, 0.5) jitter, so a small move of
    the threshold reclassifies only the borderline share of records, mirroring this project's own
    one-bin-perturbation convention (`_robustness_battery`) applied to this check's own threshold
    instead of a candidate rule's.
    """
    return [float(u) + rng.uniform(-0.5, 0.5) for u in truth]


def gen_confound_dgp(
    n: int,
    concordance: float,
    *,
    confound_strength: float = 220.0,
    true_effect: float = 0.0,
    noise_sd: float = 60.0,
    seed: int,
) -> pl.DataFrame:
    """Scenario-C-style DGP (the review's own construction, reconstructed from `TASKS.md`'s
    description per `ADR-075`, since the review's script was never committed): `U` is a true
    common cause of both exposure composition and outcome; the base rule's true causal effect is
    exactly zero (100% confounded, by construction). `Ci` is a proxy for `U` at `concordance`.
    """
    rng = random.Random(seed)
    u = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    t = [1 if rng.random() < (0.75 if u[i] else 0.25) else 0 for i in range(n)]
    truth = [u[i] if rng.random() < concordance else 1 - u[i] for i in range(n)]
    ci_raw = _proxy_column(rng, truth)
    y = [
        1000.0 + confound_strength * u[i] + true_effect * t[i] + rng.gauss(0.0, noise_sd)
        for i in range(n)
    ]
    return pl.DataFrame(
        {"T": t, "Ci_raw": ci_raw, "y": y, "U": u}, schema={"T": pl.Int64, "Ci_raw": pl.Float64, "y": pl.Float64, "U": pl.Int64}
    )


def gen_interaction_dgp(
    n: int,
    concordance: float,
    *,
    modifier_strength: float = 260.0,
    true_effect: float = 50.0,
    noise_sd: float = 60.0,
    seed: int,
) -> pl.DataFrame:
    """Scenario-D-style DGP: `D` is a genuine effect modifier (zero main effect on `y`, zero
    confounding role — `T` is assigned independently of `D`). `Ci` is a proxy for `D` at
    `concordance`.
    """
    rng = random.Random(seed)
    d = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    t = [1 if rng.random() < 0.5 else 0 for _ in range(n)]  # independent of D: zero confounding
    truth = [d[i] if rng.random() < concordance else 1 - d[i] for i in range(n)]
    ci_raw = _proxy_column(rng, truth)
    y = [
        1000.0 + true_effect * t[i] + modifier_strength * t[i] * d[i] + rng.gauss(0.0, noise_sd)
        for i in range(n)
    ]
    return pl.DataFrame({"T": t, "Ci_raw": ci_raw, "y": y, "D": d})


def gen_combined_dgp(
    n: int,
    concordance: float,
    *,
    modifier_strength: float = 260.0,
    true_effect: float = 50.0,
    confound_strength: float = 90.0,
    noise_sd: float = 60.0,
    seed: int,
) -> pl.DataFrame:
    """Scenario-E-style DGP: `D` is *both* a genuine effect modifier *and* has an independent,
    modest confounding-via-selection role on the same atom (mirrors the review's own Scenario E
    construction at a conceptual level, per `TASKS.md`'s record — never retyped from an uncommitted
    script).
    """
    rng = random.Random(seed)
    d = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    t = [1 if rng.random() < (0.60 if d[i] else 0.40) else 0 for i in range(n)]
    truth = [d[i] if rng.random() < concordance else 1 - d[i] for i in range(n)]
    ci_raw = _proxy_column(rng, truth)
    y = [
        1000.0
        + confound_strength * d[i]
        + true_effect * t[i]
        + modifier_strength * t[i] * d[i]
        + rng.gauss(0.0, noise_sd)
        for i in range(n)
    ]
    return pl.DataFrame({"T": t, "Ci_raw": ci_raw, "y": y, "D": d})


# =================================================================================================
# The revised classifier
# =================================================================================================


def _stratum_contrast(frame: pl.DataFrame, target_mask: pl.Series) -> tuple[float | None, float]:
    """`(delta, se)` for `T`'s own effect recomputed within `target_mask` vs. its complement —
    `harm(base_i | Ci=target) - harm(base_i | Ci=complement)`, the stratum-contrast heterogeneity
    signal. `None` delta means one side had no usable comparison group."""
    working = frame.with_columns(target_mask.alias("_tgt"))
    stats = working.group_by(["T", "_tgt"]).agg(
        pl.col("y").mean().alias("mean"), pl.col("y").var(ddof=1).alias("var"), pl.len().alias("n")
    )
    cells: dict[tuple[int, bool], tuple[float, float, int]] = {}
    for row in stats.iter_rows(named=True):
        cells[(row["T"], row["_tgt"])] = (row["mean"], row["var"] or 0.0, row["n"])
    needed = [(1, True), (0, True), (1, False), (0, False)]
    if any(key not in cells for key in needed):
        return None, math.inf
    m11, v11, n11 = cells[(1, True)]
    m01, v01, n01 = cells[(0, True)]
    m10, v10, n10 = cells[(1, False)]
    m00, v00, n00 = cells[(0, False)]
    harm_target = m11 - m01
    harm_complement = m10 - m00
    delta = harm_target - harm_complement
    var_delta = (v11 / n11 if n11 else math.inf) + (v01 / n01 if n01 else math.inf)
    var_delta += (v10 / n10 if n10 else math.inf) + (v00 / n00 if n00 else math.inf)
    se = math.sqrt(var_delta) if math.isfinite(var_delta) else math.inf
    return delta, se


@dataclass
class ClassificationResult:
    label: str
    reason: str
    coverage: float
    attenuation: float
    raw_base: float
    adjusted: float
    delta_production: float | None
    delta_p_value: float | None
    delta_low_threshold: float | None
    delta_high_threshold: float | None
    stability_ok: bool
    ols_delta_match: bool


def classify_atom(frame: pl.DataFrame) -> ClassificationResult:
    """The revised leave-one-out classifier. `frame` has boolean/int `T` (base_i's own exposure
    mask) and a continuous `Ci_raw` proxy column whose `>= 0.5` binarization is the candidate atom
    under test, exactly as `_binned_group_label`/`_stratified_adjustment` would see a real
    quantile-binned numeric atom.
    """
    base_mask = frame["T"] == 1
    ci_bool = (frame["Ci_raw"] >= 0.5).cast(pl.Int64).rename("Ci")
    binned = frame.with_columns(ci_bool)

    raw_base, _ = _stratified_adjustment(binned, base_mask, OUTCOME, ())
    adjusted, coverage = _stratified_adjustment(binned, base_mask, OUTCOME, ("Ci",))
    attenuation = 1.0 - (adjusted / raw_base if raw_base else 1.0)
    coverage_ok = coverage >= DEFAULT_THRESHOLDS.min_confounder_stratum_coverage
    sign_ok = (adjusted > 0) == (raw_base > 0) if raw_base else True
    confound_positive_evidence = (
        coverage_ok and sign_ok and attenuation > DEFAULT_THRESHOLDS.max_adjusted_attenuation
    )

    delta, se = _stratum_contrast(binned, frame["Ci_raw"] >= 0.5)
    delta_p = normal_approx_two_sided_p(delta, se) if delta is not None else 1.0
    heterogeneity_significant = delta is not None and delta_p < ALPHA
    concentrates_in_target = delta is not None and (delta > 0) == (raw_base > 0 if raw_base else True)

    delta_low, se_low = _stratum_contrast(binned, frame["Ci_raw"] >= (0.5 - THRESHOLD_STEP))
    delta_high, se_high = _stratum_contrast(binned, frame["Ci_raw"] >= (0.5 + THRESHOLD_STEP))
    delta_low_p = normal_approx_two_sided_p(delta_low, se_low) if delta_low is not None else 1.0
    delta_high_p = normal_approx_two_sided_p(delta_high, se_high) if delta_high is not None else 1.0
    stability_ok = False
    if delta is not None and delta_low is not None and delta_high is not None and delta != 0:
        same_sign = (delta > 0) == (delta_low > 0) == (delta_high > 0)
        retained = min(abs(delta_low), abs(delta_high)) / abs(delta)
        # Each of the three admissible partitions (production threshold, one bin lower, one bin
        # higher) must independently clear its own significance bar, not just agree in sign and
        # retain magnitude — a single lucky draw at the production threshold is not enough to
        # grant the one branch that leaves a candidate fully uncapped. This is a deliberately
        # stricter bar than a bare 95% CI, mirroring why G06's own min_e_value (1.5, not a bare
        # "excludes 1.0") already builds in an extra safety margin beyond a simple interval.
        all_significant = delta_p < ALPHA and delta_low_p < ALPHA and delta_high_p < ALPHA
        stability_ok = same_sign and retained >= STABILITY_RETENTION_FLOOR and all_significant

    interaction_positive_evidence = (
        coverage_ok
        and attenuation <= DEFAULT_THRESHOLDS.max_adjusted_attenuation
        and heterogeneity_significant
        and concentrates_in_target
        and stability_ok
    )

    if not coverage_ok:
        label, reason = "indeterminate", "coverage_floor"
    elif confound_positive_evidence:
        label, reason = "confound_like", "attenuation_exceeds_ceiling_with_coverage"
    elif interaction_positive_evidence:
        label, reason = "interaction_like", "heterogeneity_significant_and_threshold_stable"
    else:
        label, reason = "indeterminate", "no_positive_interaction_evidence"

    ols_match = _verify_ols_redundancy(binned) if delta is not None else False

    return ClassificationResult(
        label=label,
        reason=reason,
        coverage=coverage,
        attenuation=attenuation,
        raw_base=raw_base,
        adjusted=adjusted,
        delta_production=delta,
        delta_p_value=delta_p,
        delta_low_threshold=delta_low,
        delta_high_threshold=delta_high,
        stability_ok=stability_ok,
        ols_delta_match=ols_match,
    )


def _solve_normal_equations(xtx: list[list[float]], xty: list[float]) -> list[float]:
    """Plain Gaussian elimination with partial pivoting. No numpy dependency in this environment."""
    a = [row[:] for row in xtx]
    b = xty[:]
    k = len(b)
    for col in range(k):
        pivot = max(range(col, k), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            continue
        a[col], a[pivot] = a[pivot], a[col]
        b[col], b[pivot] = b[pivot], b[col]
        for r in range(col + 1, k):
            factor = a[r][col] / a[col][col]
            for c in range(col, k):
                a[r][c] -= factor * a[col][c]
            b[r] -= factor * b[col]
    x = [0.0] * k
    for r in reversed(range(k)):
        s = b[r] - sum(a[r][c] * x[c] for c in range(r + 1, k))
        x[r] = s / a[r][r] if abs(a[r][r]) > 1e-12 else 0.0
    return x


def _verify_ols_redundancy(frame: pl.DataFrame) -> bool:
    """Confirms, numerically on this trial's own generated data (not merely asserted), that the
    saturated-design OLS interaction coefficient for `y ~ 1 + T + Ci + T*Ci` equals the
    stratum-contrast `delta` to floating-point precision — the reason signals 3/4 from the ADR's
    candidate list (independent parameterization; nested-model comparison) are not used as a
    second, independent signal in this design: they are not independent of signal 1 here.
    """
    t = frame["T"].to_list()
    ci = frame["Ci"].to_list()
    y = frame["y"].to_list()
    n = len(y)
    x_rows = [[1.0, float(t[i]), float(ci[i]), float(t[i] * ci[i])] for i in range(n)]
    xtx = [[0.0] * 4 for _ in range(4)]
    xty = [0.0] * 4
    for row, yi in zip(x_rows, y):
        for a in range(4):
            xty[a] += row[a] * yi
            for b in range(4):
                xtx[a][b] += row[a] * row[b]
    beta = _solve_normal_equations(xtx, xty)
    ols_interaction = beta[3]
    delta, _ = _stratum_contrast(frame, frame["Ci"] == 1)
    if delta is None:
        return False
    return math.isclose(ols_interaction, delta, rel_tol=1e-6, abs_tol=1e-6)


# =================================================================================================
# The proxy-confounding ladder — the mandatory core deliverable
# =================================================================================================


def run_ladder(
    dgp_fn: Any,
    concordances: list[float],
    trials_per_point: int,
    n: int,
    seed_base: int,
) -> list[dict[str, Any]]:
    results = []
    for concordance in concordances:
        labels: list[str] = []
        detail: list[dict[str, Any]] = []
        for trial in range(trials_per_point):
            seed = seed_base + int(concordance * 10_000) + trial
            frame = dgp_fn(n, concordance, seed=seed)
            result = classify_atom(frame)
            labels.append(result.label)
            detail.append({"seed": seed, **asdict(result)})
        counts = {label: labels.count(label) for label in ("confound_like", "interaction_like", "indeterminate")}
        results.append(
            {
                "concordance": concordance,
                "trials": trials_per_point,
                "counts": counts,
                "detail": detail,
            }
        )
    return results


def main() -> None:
    concordances = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.99]

    print("=" * 100)
    print("TASK-080 revision (ADR-075): proxy-confounding ladder — confound DGP (ground truth: confound_like)")
    print("=" * 100)
    confound_ladder = run_ladder(gen_confound_dgp, concordances, trials_per_point=100, n=1600, seed_base=100_000)
    for row in confound_ladder:
        c = row["counts"]
        print(
            f"concordance={row['concordance']:.2f}  n_trials={row['trials']:>3}  "
            f"confound_like={c['confound_like']:>3}  indeterminate={c['indeterminate']:>3}  "
            f"interaction_like={c['interaction_like']:>3}  <-- SAFETY FAILURE if >0"
            if c["interaction_like"] > 0
            else f"concordance={row['concordance']:.2f}  n_trials={row['trials']:>3}  "
            f"confound_like={c['confound_like']:>3}  indeterminate={c['indeterminate']:>3}  "
            f"interaction_like={c['interaction_like']:>3}"
        )

    print()
    print("=" * 100)
    print("TASK-080 revision (ADR-075): proxy-confounding ladder — interaction DGP (ground truth: interaction_like)")
    print("=" * 100)
    interaction_ladder = run_ladder(gen_interaction_dgp, concordances, trials_per_point=25, n=1600, seed_base=200_000)
    for row in interaction_ladder:
        c = row["counts"]
        print(
            f"concordance={row['concordance']:.2f}  n_trials={row['trials']:>3}  "
            f"interaction_like={c['interaction_like']:>3}  indeterminate={c['indeterminate']:>3}  "
            f"confound_like={c['confound_like']:>3}"
            + ("  <-- unexpected" if c["confound_like"] > 0 else "")
        )

    print()
    print("=" * 100)
    print("TASK-080 revision (ADR-075): combined DGP (genuine interaction + independent modest confounding, Scenario-E-style)")
    print("=" * 100)
    combined_points = [0.65, 0.80, 0.95]
    combined_ladder = run_ladder(gen_combined_dgp, combined_points, trials_per_point=20, n=1600, seed_base=300_000)
    for row in combined_ladder:
        c = row["counts"]
        print(
            f"concordance={row['concordance']:.2f}  n_trials={row['trials']:>3}  "
            f"interaction_like={c['interaction_like']:>3}  indeterminate={c['indeterminate']:>3}  "
            f"confound_like={c['confound_like']:>3}"
        )

    # -------------------------------------------------------------------------------------------
    # Aggregate the two asymmetric error rates, reported SEPARATELY per ADR-075 — never averaged.
    # -------------------------------------------------------------------------------------------
    total_confound_trials = sum(row["trials"] for row in confound_ladder)
    false_confounding_as_interaction = sum(row["counts"]["interaction_like"] for row in confound_ladder)
    false_interaction_acceptable = sum(row["counts"]["indeterminate"] for row in confound_ladder)
    correctly_confound_like = sum(row["counts"]["confound_like"] for row in confound_ladder)

    total_interaction_trials = sum(row["trials"] for row in interaction_ladder)
    correctly_interaction_like = sum(row["counts"]["interaction_like"] for row in interaction_ladder)
    interaction_to_indeterminate = sum(row["counts"]["indeterminate"] for row in interaction_ladder)
    interaction_to_confound = sum(row["counts"]["confound_like"] for row in interaction_ladder)

    # -------------------------------------------------------------------------------------------
    # Before/after: what the REVIEWED design's implicit rule (`attenuation < 0.50 ->
    # interaction_like`, now a permanently forbidden inference per ADR-075) would have produced on
    # the identical trials, computed from the same already-collected attenuation/coverage figures
    # (no extra DGP draws) — the direct quantified reproduction of the review's blocking finding.
    # -------------------------------------------------------------------------------------------
    old_rule_comparison = []
    old_rule_total_unsafe = 0
    for row in confound_ladder:
        old_unsafe = sum(
            1 for t in row["detail"] if t["coverage"] >= 0.50 and t["attenuation"] <= 0.50
        )
        old_rule_total_unsafe += old_unsafe
        old_rule_comparison.append(
            {
                "concordance": row["concordance"],
                "trials": row["trials"],
                "old_rule_interaction_like_unsafe": old_unsafe,
                "new_rule_interaction_like": row["counts"]["interaction_like"],
            }
        )

    print()
    print("=" * 100)
    print("BEFORE/AFTER: reviewed design's implicit old rule vs. this revision's new rule, same trials")
    print("=" * 100)
    for row in old_rule_comparison:
        print(
            f"concordance={row['concordance']:.2f}  n={row['trials']:>4}  "
            f"OLD RULE interaction_like(unsafe)={row['old_rule_interaction_like_unsafe']:>4}  "
            f"NEW RULE interaction_like={row['new_rule_interaction_like']:>4}"
        )
    print(
        f"TOTAL old-rule unsafe rate: {old_rule_total_unsafe}/{total_confound_trials} = "
        f"{old_rule_total_unsafe / total_confound_trials:.4f}"
    )

    summary = {
        "alpha": ALPHA,
        "stability_retention_floor": STABILITY_RETENTION_FLOOR,
        "threshold_step": THRESHOLD_STEP,
        "confound_ladder": confound_ladder,
        "interaction_ladder": interaction_ladder,
        "combined_ladder": combined_ladder,
        "old_rule_vs_new_rule_comparison": old_rule_comparison,
        "asymmetric_error_rates": {
            "confound_ground_truth_trials": total_confound_trials,
            "SAFETY_false_confounding_as_interaction_count": false_confounding_as_interaction,
            "SAFETY_false_confounding_as_interaction_rate": (
                false_confounding_as_interaction / total_confound_trials
            ),
            "acceptable_false_interaction_indeterminate_count": false_interaction_acceptable,
            "acceptable_false_interaction_indeterminate_rate": (
                false_interaction_acceptable / total_confound_trials
            ),
            "correctly_confound_like_count": correctly_confound_like,
            "correctly_confound_like_rate": correctly_confound_like / total_confound_trials,
            "interaction_ground_truth_trials": total_interaction_trials,
            "correctly_interaction_like_count": correctly_interaction_like,
            "correctly_interaction_like_rate": correctly_interaction_like / total_interaction_trials,
            "interaction_degraded_to_indeterminate_count": interaction_to_indeterminate,
            "interaction_degraded_to_indeterminate_rate": (
                interaction_to_indeterminate / total_interaction_trials
            ),
            "interaction_misclassified_confound_like_count": interaction_to_confound,
            "interaction_misclassified_confound_like_rate": (
                interaction_to_confound / total_interaction_trials
            ),
        },
    }

    print()
    print("=" * 100)
    print("ASYMMETRIC ERROR RATES (reported separately, per ADR-075 — never averaged)")
    print("=" * 100)
    rates = summary["asymmetric_error_rates"]
    print(
        f"[SAFETY-CRITICAL] confound -> interaction_like (uncapped): "
        f"{rates['SAFETY_false_confounding_as_interaction_count']}/{rates['confound_ground_truth_trials']} "
        f"= {rates['SAFETY_false_confounding_as_interaction_rate']:.4f}"
    )
    print(
        f"[acceptable]      confound -> indeterminate:               "
        f"{rates['acceptable_false_interaction_indeterminate_count']}/{rates['confound_ground_truth_trials']} "
        f"= {rates['acceptable_false_interaction_indeterminate_rate']:.4f}"
    )
    print(
        f"[correct]         confound -> confound_like:                "
        f"{rates['correctly_confound_like_count']}/{rates['confound_ground_truth_trials']} "
        f"= {rates['correctly_confound_like_rate']:.4f}"
    )
    print(
        f"[correct]         interaction -> interaction_like:          "
        f"{rates['correctly_interaction_like_count']}/{rates['interaction_ground_truth_trials']} "
        f"= {rates['correctly_interaction_like_rate']:.4f}"
    )
    print(
        f"[disclosed cost]  interaction -> indeterminate:              "
        f"{rates['interaction_degraded_to_indeterminate_count']}/{rates['interaction_ground_truth_trials']} "
        f"= {rates['interaction_degraded_to_indeterminate_rate']:.4f}"
    )
    print(
        f"[secondary]       interaction -> confound_like:              "
        f"{rates['interaction_misclassified_confound_like_count']}/{rates['interaction_ground_truth_trials']} "
        f"= {rates['interaction_misclassified_confound_like_rate']:.4f}"
    )

    out_path = REPOSITORY / "docs/benchmark/task-080-composition-classifier-revision-raw.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print()
    print(f"Raw output written to {out_path}")


if __name__ == "__main__":
    main()
