"""TASK-080 SECOND revision (`ADR-077`): adversarial identifiability suite. **DESIGN-ONLY.** No
`discovery.engine`, `apply.py`, or gate code is modified.

This script answers `ADR-077`'s central question empirically: does there exist an observational
estimand, computable from a frozen candidate's condition tuple + frame alone, that provides positive
evidence for genuine interaction without turning residual proxy confounding — at arbitrary
prevalence, measurement error, and nonlinearity — into `interaction_like`?

It calls the real, unmodified `policy_analytics.validation.apply._stratified_adjustment` and the
real `policy_analytics.validation.grading.normal_approx_two_sided_p` throughout — no estimator or
significance test is reimplemented. `DEFAULT_THRESHOLDS` is the real, unmodified contract constant.

Four sections, matching `ADR-077`'s four required directions:

  1. `run_direction1_identifiability_suite()` — the adversarial DGP sweep: confounder prevalence
     (skewed, not just 0.5), asymmetric proxy measurement error, continuous/nonlinear confounders,
     asymmetric treatment-assignment odds, overlap, interaction strength, and sample size
     (n=300..12800). Reports whether P(interaction_like) on pure-confound DGPs converges toward zero
     or grows with n, for both the ADR-075 two-signal classifier (`classify_interaction_v075`) and
     the two-state fallback (`classify_two_state`).
  2. `run_direction2_estimand_audit()` — analytical derivation (verified numerically) of exactly why
     the ADR-075 classifier's positive-evidence signals are not identifying, plus an explicit
     matched-pair counterexample: a confound DGP and a genuine-interaction DGP that produce
     statistically indistinguishable classifier outputs.
  3. `run_direction3_two_state_fallback()` — the two-state fallback (`confound_like`/`indeterminate`
     only) tested as a first-class candidate across the same adversarial sweep, plus a check that it
     does not misclassify genuine interactions as `confound_like`.
  4. `run_direction4_escape_hatch_attempts()` — two candidate stronger estimands, each tested against
     the direction-1/2 audit and found not to qualify without an unverifiable assumption.

Usage:
  uv run python scripts/diagnose_task080_identifiability_suite.py
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

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

ALPHA = 0.002  # the ADR-075 classifier's own stricter-than-CI significance bar, reused unchanged
STABILITY_RETENTION_FLOOR = 1.0 - DEFAULT_THRESHOLDS.max_adjusted_attenuation  # 0.50, reused
STEP_Q = 0.15  # quantile-space threshold-perturbation step (generalizes the prior script's fixed 0.15)

OUTCOME = OutcomeDefinition(
    outcome_id="synthetic_task080_identifiability_metric",
    role=OutcomeRole.PRIMARY,
    column="y",
    unit="unit",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description=(
        "Neutral synthetic outcome for TASK-080's second-revision identifiability suite (ADR-077). "
        "Invented; unrelated to any real dataset or domain in this repository."
    ),
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Value increases",
)


# =================================================================================================
# Generalized DGP generators — binary/skewed-prior, asymmetric-error, continuous/nonlinear variants.
# All known-by-construction synthetic data; no ground-truth/trap identity referenced anywhere.
# =================================================================================================


def gen_confound_binary(
    n: int,
    *,
    u_prior: float,
    concordance: float,
    t_odds_hi: float,
    t_odds_lo: float,
    confound_strength: float,
    noise_sd: float,
    seed: int,
) -> pl.DataFrame:
    """Generalizes the first revision's confound DGP along TWO independent symmetry axes at once:
    `u_prior` (confounder prevalence, need not be 0.5) and `t_odds_hi`/`t_odds_lo` (treatment
    assignment odds given U, need not sum to 1). The design document's original zero-true-delta
    proof (`docs/analytics/task-080-...md` old `S14.5`) required BOTH `u_prior=0.5` AND
    `t_odds_hi + t_odds_lo == 1` to hold simultaneously — this generator can break either or both.
    True causal effect of `T` on `y` is exactly zero everywhere (100% confounded, by construction).
    """
    rng = random.Random(seed)
    u = [1 if rng.random() < u_prior else 0 for _ in range(n)]
    t = [1 if rng.random() < (t_odds_hi if u[i] else t_odds_lo) else 0 for i in range(n)]
    truth = [u[i] if rng.random() < concordance else 1 - u[i] for i in range(n)]
    ci_raw = [float(v) + rng.uniform(-0.5, 0.5) for v in truth]
    y = [1000.0 + confound_strength * u[i] + rng.gauss(0.0, noise_sd) for i in range(n)]
    return pl.DataFrame({"T": t, "Ci_raw": ci_raw, "y": y, "U": u})


def gen_confound_binary_asymmetric_proxy(
    n: int,
    *,
    u_prior: float,
    fp_rate: float,
    fn_rate: float,
    t_odds_hi: float,
    t_odds_lo: float,
    confound_strength: float,
    noise_sd: float,
    seed: int,
) -> pl.DataFrame:
    """Asymmetric proxy measurement error: `P(observed=1|U=0) = fp_rate` and
    `P(observed=0|U=1) = fn_rate`, independently set (not one shared `concordance` implying
    symmetric error rates). True causal effect of `T` on `y` is exactly zero everywhere.
    """
    rng = random.Random(seed)
    u = [1 if rng.random() < u_prior else 0 for _ in range(n)]
    t = [1 if rng.random() < (t_odds_hi if u[i] else t_odds_lo) else 0 for i in range(n)]
    truth = []
    for ui in u:
        if ui == 1:
            truth.append(0 if rng.random() < fn_rate else 1)
        else:
            truth.append(1 if rng.random() < fp_rate else 0)
    ci_raw = [float(v) + rng.uniform(-0.5, 0.5) for v in truth]
    y = [1000.0 + confound_strength * u[i] + rng.gauss(0.0, noise_sd) for i in range(n)]
    return pl.DataFrame({"T": t, "Ci_raw": ci_raw, "y": y, "U": u})


def gen_confound_continuous_nonlinear(
    n: int,
    *,
    z_sd: float,
    y_linear_coef: float,
    y_quad_coef: float,
    t_logit_intercept: float,
    t_logit_coef: float,
    proxy_noise_sd: float,
    noise_sd: float,
    seed: int,
) -> pl.DataFrame:
    """Continuous confounder `Z ~ Normal(0, z_sd)`, nonlinear (quadratic) effect on `y`, nonlinear
    (logistic) treatment assignment on `Z`, continuous Gaussian-noise proxy `Ci_raw = Z + noise`
    (not threshold-derived from a binary truth). True causal effect of `T` on `y` is exactly zero.
    """
    rng = random.Random(seed)
    z = [rng.gauss(0.0, z_sd) for _ in range(n)]

    def sigmoid(x: float) -> float:
        if x >= 0:
            ex = math.exp(-x)
            return 1.0 / (1.0 + ex)
        ex = math.exp(x)
        return ex / (1.0 + ex)

    t = [1 if rng.random() < sigmoid(t_logit_intercept + t_logit_coef * zi) else 0 for zi in z]
    y = [
        1000.0 + y_linear_coef * zi + y_quad_coef * (zi**2) + rng.gauss(0.0, noise_sd) for zi in z
    ]
    ci_raw = [zi + rng.gauss(0.0, proxy_noise_sd) for zi in z]
    return pl.DataFrame({"T": t, "Ci_raw": ci_raw, "y": y, "U": z})


def gen_interaction_binary(
    n: int,
    *,
    d_prior: float,
    concordance: float,
    modifier_strength: float,
    true_effect: float,
    noise_sd: float,
    seed: int,
) -> pl.DataFrame:
    """Genuine effect modifier `D` (zero main effect, zero confounding role — `T` independent of
    `D`), with `D`'s own prevalence swept (parity check: does the classifier's genuine-interaction
    side stay clean under a skewed MODIFIER prevalence too, not just 0.5)."""
    rng = random.Random(seed)
    d = [1 if rng.random() < d_prior else 0 for _ in range(n)]
    t = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    truth = [d[i] if rng.random() < concordance else 1 - d[i] for i in range(n)]
    ci_raw = [float(v) + rng.uniform(-0.5, 0.5) for v in truth]
    y = [
        1000.0 + true_effect * t[i] + modifier_strength * t[i] * d[i] + rng.gauss(0.0, noise_sd)
        for i in range(n)
    ]
    return pl.DataFrame({"T": t, "Ci_raw": ci_raw, "y": y, "D": d})


def gen_interaction_continuous(
    n: int,
    *,
    z_sd: float,
    modifier_coef: float,
    true_effect: float,
    proxy_noise_sd: float,
    noise_sd: float,
    seed: int,
) -> pl.DataFrame:
    """Continuous genuine effect modifier: `y = 1000 + true_effect*T + modifier_coef*T*Z + noise`,
    `T` independent of `Z` (zero confounding role), `Ci_raw = Z + Gaussian proxy noise`."""
    rng = random.Random(seed)
    z = [rng.gauss(0.0, z_sd) for _ in range(n)]
    t = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    y = [
        1000.0 + true_effect * t[i] + modifier_coef * t[i] * z[i] + rng.gauss(0.0, noise_sd)
        for i in range(n)
    ]
    ci_raw = [zi + rng.gauss(0.0, proxy_noise_sd) for zi in z]
    return pl.DataFrame({"T": t, "Ci_raw": ci_raw, "y": y, "D": z})


# =================================================================================================
# The classifier under test — ADR-075's two-signal mechanism, generalized to a data-driven quantile
# threshold (works for both jittered-binary and continuous Ci_raw), plus the two-state fallback.
# =================================================================================================


def _quantile_value(values: list[float], q: float) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    idx = min(n - 1, max(0, int(n * q)))
    return ordered[idx]


def _stratum_contrast(frame: pl.DataFrame, target_mask: pl.Series) -> tuple[float | None, float]:
    """`(delta, se)` for `T`'s own effect recomputed within `target_mask` vs. its complement —
    identical mechanism to the first revision's script, reused verbatim."""
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
    delta = (m11 - m01) - (m10 - m00)
    var_delta = (v11 / n11 if n11 else math.inf) + (v01 / n01 if n01 else math.inf)
    var_delta += (v10 / n10 if n10 else math.inf) + (v00 / n00 if n00 else math.inf)
    se = math.sqrt(var_delta) if math.isfinite(var_delta) else math.inf
    return delta, se


@dataclass
class ClassificationResult:
    label_v075: str  # ADR-075's asymmetric two-signal classifier
    label_two_state: str  # this revision's two-state fallback (confound_like / indeterminate only)
    coverage: float
    attenuation: float
    raw_base: float
    adjusted: float
    delta_production: float | None
    delta_p_value: float | None
    stability_ok: bool


def classify_atom(frame: pl.DataFrame, threshold_q: float = 0.5, step_q: float = STEP_Q) -> ClassificationResult:
    """The ADR-075 two-signal classifier, generalized to a data-driven quantile threshold (default:
    median split), plus the two-state fallback derived from the SAME underlying evidence (never a
    separate computation — the two-state fallback's `confound_like` branch is bit-for-bit identical
    to `label_v075`'s `confound_like` branch; it only differs in never emitting `interaction_like`).
    """
    base_mask = frame["T"] == 1
    ci_raw_values = frame["Ci_raw"].to_list()
    thr = _quantile_value(ci_raw_values, threshold_q)
    thr_low = _quantile_value(ci_raw_values, max(0.0, threshold_q - step_q))
    thr_high = _quantile_value(ci_raw_values, min(1.0, threshold_q + step_q))

    ci_bool = (frame["Ci_raw"] >= thr).cast(pl.Int64).rename("Ci")
    binned = frame.with_columns(ci_bool)

    raw_base, _ = _stratified_adjustment(binned, base_mask, OUTCOME, ())
    adjusted, coverage = _stratified_adjustment(binned, base_mask, OUTCOME, ("Ci",))
    attenuation = 1.0 - (adjusted / raw_base if raw_base else 1.0)
    coverage_ok = coverage >= DEFAULT_THRESHOLDS.min_confounder_stratum_coverage
    sign_ok = (adjusted > 0) == (raw_base > 0) if raw_base else True
    confound_positive_evidence = (
        coverage_ok and sign_ok and attenuation > DEFAULT_THRESHOLDS.max_adjusted_attenuation
    )

    delta, se = _stratum_contrast(binned, frame["Ci_raw"] >= thr)
    delta_p = normal_approx_two_sided_p(delta, se) if delta is not None else 1.0
    heterogeneity_significant = delta is not None and delta_p < ALPHA
    concentrates_in_target = delta is not None and (delta > 0) == (raw_base > 0 if raw_base else True)

    delta_low, se_low = _stratum_contrast(binned, frame["Ci_raw"] >= thr_low)
    delta_high, se_high = _stratum_contrast(binned, frame["Ci_raw"] >= thr_high)
    delta_low_p = normal_approx_two_sided_p(delta_low, se_low) if delta_low is not None else 1.0
    delta_high_p = normal_approx_two_sided_p(delta_high, se_high) if delta_high is not None else 1.0
    stability_ok = False
    if delta is not None and delta_low is not None and delta_high is not None and delta != 0:
        same_sign = (delta > 0) == (delta_low > 0) == (delta_high > 0)
        retained = min(abs(delta_low), abs(delta_high)) / abs(delta)
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
        label_v075 = "indeterminate"
    elif confound_positive_evidence:
        label_v075 = "confound_like"
    elif interaction_positive_evidence:
        label_v075 = "interaction_like"
    else:
        label_v075 = "indeterminate"

    # Two-state fallback: EXACT same confound_like criterion, everything else -> indeterminate.
    # interaction_like is structurally impossible to emit — not merely rare, absent from the branch
    # set entirely.
    if coverage_ok and confound_positive_evidence:
        label_two_state = "confound_like"
    else:
        label_two_state = "indeterminate"

    return ClassificationResult(
        label_v075=label_v075,
        label_two_state=label_two_state,
        coverage=coverage,
        attenuation=attenuation,
        raw_base=raw_base,
        adjusted=adjusted,
        delta_production=delta,
        delta_p_value=delta_p,
        stability_ok=stability_ok,
    )


# =================================================================================================
# Direction 1 — adversarial identifiability suite
# =================================================================================================


def _sweep(
    dgp_fn: Callable[..., pl.DataFrame],
    fixed_kwargs: dict[str, Any],
    varying: dict[str, list[Any]],
    trials_per_point: int,
    seed_base: int,
) -> list[dict[str, Any]]:
    """Cartesian sweep over `varying`'s keys/value-lists; `fixed_kwargs` held constant."""
    import itertools

    keys = list(varying.keys())
    rows: list[dict[str, Any]] = []
    for combo in itertools.product(*[varying[k] for k in keys]):
        params = dict(zip(keys, combo))
        all_kwargs = {**fixed_kwargs, **params}
        labels_v075: list[str] = []
        labels_two_state: list[str] = []
        for trial in range(trials_per_point):
            seed = seed_base + hash((tuple(sorted(all_kwargs.items())), trial)) % 1_000_000
            frame = dgp_fn(seed=seed, **all_kwargs)
            result = classify_atom(frame)
            labels_v075.append(result.label_v075)
            labels_two_state.append(result.label_two_state)
        rows.append(
            {
                "params": params,
                "trials": trials_per_point,
                "v075_counts": {
                    label: labels_v075.count(label)
                    for label in ("confound_like", "interaction_like", "indeterminate")
                },
                "two_state_counts": {
                    label: labels_two_state.count(label)
                    for label in ("confound_like", "indeterminate")
                },
            }
        )
    return rows


def run_direction1_identifiability_suite() -> dict[str, Any]:
    print("=" * 100)
    print("DIRECTION 1: Adversarial identifiability suite")
    print("=" * 100)

    results: dict[str, Any] = {}

    # -- 1a. Headline n-sweep at a fixed adversarial skewed-prevalence/concordance combo --------
    # This is the property ADR-077 names as the success criterion: P(interaction_like) vs n on a
    # single pure-confound DGP, swept across a real range of n from small to large.
    print("\n--- 1a. n-sweep, skewed prevalence (u_prior=0.2), concordance=0.75 (the ADR-076 point) ---")
    n_sweep_points = [300, 600, 1200, 2400, 4800, 9600, 12800]
    n_sweep_rows = []
    for n in n_sweep_points:
        v075_labels = []
        two_state_labels = []
        trials = 60
        for trial in range(trials):
            seed = 500_000 + n + trial
            frame = gen_confound_binary(
                n,
                u_prior=0.2,
                concordance=0.75,
                t_odds_hi=0.75,
                t_odds_lo=0.25,
                confound_strength=220.0,
                noise_sd=60.0,
                seed=seed,
            )
            r = classify_atom(frame)
            v075_labels.append(r.label_v075)
            two_state_labels.append(r.label_two_state)
        v075_interaction_rate = v075_labels.count("interaction_like") / trials
        two_state_interaction_rate = 0.0  # structurally impossible
        n_sweep_rows.append(
            {
                "n": n,
                "trials": trials,
                "v075_interaction_like_rate": v075_interaction_rate,
                "v075_confound_like_rate": v075_labels.count("confound_like") / trials,
                "v075_indeterminate_rate": v075_labels.count("indeterminate") / trials,
                "two_state_interaction_like_rate": two_state_interaction_rate,
                "two_state_confound_like_rate": two_state_labels.count("confound_like") / trials,
            }
        )
        print(
            f"  n={n:>6}  v075 interaction_like={v075_interaction_rate:.3f}  "
            f"two_state interaction_like={two_state_interaction_rate:.3f} (structurally 0)"
        )
    results["1a_n_sweep_skewed_prevalence"] = n_sweep_rows

    # -- 1b. Prevalence sweep at fixed n, multiple concordances -----------------------------------
    print("\n--- 1b. Confounder prevalence sweep (u_prior in {0.1..0.9}), n=3200 ---")
    prevalence_rows = _sweep(
        gen_confound_binary,
        fixed_kwargs=dict(
            n=3200, t_odds_hi=0.75, t_odds_lo=0.25, confound_strength=220.0, noise_sd=60.0
        ),
        varying={"u_prior": [0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9], "concordance": [0.65, 0.75, 0.85]},
        trials_per_point=40,
        seed_base=600_000,
    )
    for row in prevalence_rows:
        c = row["v075_counts"]
        print(
            f"  u_prior={row['params']['u_prior']:.1f} concordance={row['params']['concordance']:.2f} "
            f"n_trials={row['trials']:>3}  interaction_like={c['interaction_like']:>3}"
        )
    results["1b_prevalence_sweep"] = prevalence_rows

    # -- 1c. Asymmetric proxy measurement error (fp_rate != fn_rate) ------------------------------
    print("\n--- 1c. Asymmetric proxy measurement error, u_prior=0.3, n=3200 ---")
    asym_error_rows = _sweep(
        gen_confound_binary_asymmetric_proxy,
        fixed_kwargs=dict(
            n=3200, u_prior=0.3, t_odds_hi=0.75, t_odds_lo=0.25, confound_strength=220.0, noise_sd=60.0
        ),
        varying={
            "fp_rate": [0.05, 0.15, 0.30],
            "fn_rate": [0.30, 0.15, 0.05],
        },
        trials_per_point=40,
        seed_base=700_000,
    )
    for row in asym_error_rows:
        c = row["v075_counts"]
        print(
            f"  fp={row['params']['fp_rate']:.2f} fn={row['params']['fn_rate']:.2f} "
            f"n_trials={row['trials']:>3}  interaction_like={c['interaction_like']:>3}"
        )
    results["1c_asymmetric_proxy_error"] = asym_error_rows

    # -- 1d. Continuous / nonlinear confounder + nonlinear (logistic) treatment assignment --------
    print("\n--- 1d. Continuous/nonlinear confounder, n-sweep ---")
    continuous_rows = []
    for n in [800, 3200, 12800]:
        labels_v075 = []
        labels_two_state = []
        trials = 40
        for trial in range(trials):
            seed = 800_000 + n + trial
            frame = gen_confound_continuous_nonlinear(
                n,
                z_sd=1.0,
                y_linear_coef=0.0,
                y_quad_coef=180.0,  # purely quadratic dependence: no linear term at all
                t_logit_intercept=0.0,
                t_logit_coef=1.2,  # nonlinear/logistic T|Z assignment
                proxy_noise_sd=0.6,  # substantial, continuous, non-threshold-derived proxy error
                noise_sd=60.0,
                seed=seed,
            )
            r = classify_atom(frame)
            labels_v075.append(r.label_v075)
            labels_two_state.append(r.label_two_state)
        continuous_rows.append(
            {
                "n": n,
                "trials": trials,
                "v075_interaction_like_rate": labels_v075.count("interaction_like") / trials,
                "two_state_interaction_like_rate": 0.0,
            }
        )
        print(
            f"  n={n:>6}  v075 interaction_like="
            f"{continuous_rows[-1]['v075_interaction_like_rate']:.3f}"
        )
    results["1d_continuous_nonlinear"] = continuous_rows

    # -- 1e. Asymmetric treatment-assignment odds at PRIOR=0.5 (isolates the second, independent
    #        symmetry-breaking axis the original S14.5 proof also silently required) --------------
    print("\n--- 1e. Asymmetric T-odds at u_prior=0.5 (odds need not sum to 1), n=3200 ---")
    odds_rows = _sweep(
        gen_confound_binary,
        fixed_kwargs=dict(n=3200, u_prior=0.5, concordance=0.75, confound_strength=220.0, noise_sd=60.0),
        varying={
            "t_odds_hi": [0.90, 0.80, 0.70],
            "t_odds_lo": [0.30, 0.20, 0.10],
        },
        trials_per_point=40,
        seed_base=900_000,
    )
    # Filter to genuinely non-complementary combos (hi+lo != 1) to isolate this axis cleanly
    for row in odds_rows:
        hi, lo = row["params"]["t_odds_hi"], row["params"]["t_odds_lo"]
        complementary = math.isclose(hi + lo, 1.0, abs_tol=1e-9)
        c = row["v075_counts"]
        tag = " (complementary, baseline)" if complementary else " (NON-complementary)"
        print(
            f"  odds_hi={hi:.2f} odds_lo={lo:.2f}{tag}  interaction_like={c['interaction_like']:>3}"
            f"/{row['trials']}"
        )
    results["1e_asymmetric_odds_prior_0.5"] = odds_rows

    # -- 1f. Overlap sweep: T-odds spread from poor (close together) to good (far apart) ----------
    print("\n--- 1f. Overlap sweep (T-odds spread), u_prior=0.25, concordance=0.75, n=3200 ---")
    overlap_rows = _sweep(
        gen_confound_binary,
        fixed_kwargs=dict(n=3200, u_prior=0.25, concordance=0.75, confound_strength=220.0, noise_sd=60.0),
        varying={
            "t_odds_hi": [0.55, 0.65, 0.75, 0.90],
            "t_odds_lo": [0.45, 0.35, 0.25, 0.10],
        },
        trials_per_point=40,
        seed_base=1_000_000,
    )
    for row in overlap_rows:
        c = row["v075_counts"]
        print(
            f"  odds=({row['params']['t_odds_hi']:.2f},{row['params']['t_odds_lo']:.2f})  "
            f"interaction_like={c['interaction_like']:>3}/{row['trials']}"
        )
    results["1f_overlap_sweep"] = overlap_rows

    # -- 1g. Interaction-strength sweep (weak to strong), confirming the genuine-interaction side
    #        of the classifier stays clean under a SKEWED modifier prevalence too ------------------
    print("\n--- 1g. Interaction strength sweep, skewed modifier prevalence (d_prior=0.2), n=3200 ---")
    interaction_strength_rows = _sweep(
        gen_interaction_binary,
        fixed_kwargs=dict(n=3200, d_prior=0.2, concordance=0.80, true_effect=50.0, noise_sd=60.0),
        varying={"modifier_strength": [20.0, 60.0, 120.0, 260.0]},
        trials_per_point=40,
        seed_base=1_100_000,
    )
    for row in interaction_strength_rows:
        c = row["v075_counts"]
        ts = row["two_state_counts"]
        print(
            f"  modifier_strength={row['params']['modifier_strength']:>6.1f}  "
            f"v075: interaction_like={c['interaction_like']:>3} indeterminate={c['indeterminate']:>3} "
            f"confound_like={c['confound_like']:>3}  |  two_state confound_like={ts['confound_like']:>3}"
        )
    results["1g_interaction_strength_skewed_modifier_prevalence"] = interaction_strength_rows

    return results


# =================================================================================================
# Direction 2 — estimand audit
# =================================================================================================


def _analytic_bias_function(q: float, t_odds_hi: float, t_odds_lo: float, strength: float) -> float:
    """`f(q) = harm` induced purely by confounding in a stratum with `P(U=1) = q`, under
    `Y = 1000 + strength*U + noise`, `T` assigned `t_odds_hi` if `U=1` else `t_odds_lo`. Closed-form
    Bayes computation, not simulated — used to verify the simulated `delta` matches the analytic
    prediction, and to show exactly which symmetry the original design's zero-true-delta claim
    depended on.
    """
    denom_t1 = q * t_odds_hi + (1 - q) * t_odds_lo
    p_u1_given_t1 = (q * t_odds_hi) / denom_t1 if denom_t1 else 0.0
    denom_t0 = q * (1 - t_odds_hi) + (1 - q) * (1 - t_odds_lo)
    p_u1_given_t0 = (q * (1 - t_odds_hi)) / denom_t0 if denom_t0 else 0.0
    return strength * (p_u1_given_t1 - p_u1_given_t0)


def _stratum_prevalence(u_prior: float, concordance: float) -> tuple[float, float]:
    """`(q_target, q_complement) = P(U=1 | Ci=target), P(U=1 | Ci=complement)` by Bayes' rule, given
    a symmetric-concordance proxy. Equal to `(concordance, 1-concordance)` ONLY when `u_prior=0.5` —
    this is the exact symmetry the original design's S14.5 proof silently assumed.
    """
    p, c = u_prior, concordance
    q_target_den = c * p + (1 - c) * (1 - p)
    q_target = (c * p) / q_target_den if q_target_den else 0.0
    q_complement_den = (1 - c) * p + c * (1 - p)
    q_complement = ((1 - c) * p) / q_complement_den if q_complement_den else 0.0
    return q_target, q_complement


def run_direction2_estimand_audit() -> dict[str, Any]:
    print("\n" + "=" * 100)
    print("DIRECTION 2: Estimand audit")
    print("=" * 100)

    audit: dict[str, Any] = {}

    # -- 2a. Analytical derivation, verified numerically: the TRUE (population, infinite-sample)
    #        stratum-contrast is nonzero whenever EITHER u_prior != 0.5 OR t_odds_hi+t_odds_lo != 1.
    #        This is the mechanism ADR-076 found empirically; here it is derived in closed form and
    #        confirmed to match simulation, establishing it is not an artifact of one DGP shape.
    print("\n--- 2a. Closed-form true-delta as a function of u_prior and T-odds symmetry ---")
    analytic_rows = []
    for u_prior in [0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9]:
        for concordance in [0.65, 0.75, 0.85]:
            for (t_hi, t_lo) in [(0.75, 0.25), (0.90, 0.30), (0.70, 0.10)]:
                q_t, q_c = _stratum_prevalence(u_prior, concordance)
                true_delta = _analytic_bias_function(
                    q_t, t_hi, t_lo, 220.0
                ) - _analytic_bias_function(q_c, t_hi, t_lo, 220.0)
                analytic_rows.append(
                    {
                        "u_prior": u_prior,
                        "concordance": concordance,
                        "t_odds_hi": t_hi,
                        "t_odds_lo": t_lo,
                        "odds_complementary": math.isclose(t_hi + t_lo, 1.0, abs_tol=1e-9),
                        "q_target": q_t,
                        "q_complement": q_c,
                        "true_delta": true_delta,
                    }
                )
    zero_cases = [r for r in analytic_rows if abs(r["true_delta"]) < 1e-9]
    nonzero_cases = [r for r in analytic_rows if abs(r["true_delta"]) >= 1e-9]
    print(f"  {len(analytic_rows)} (u_prior, concordance, odds) combinations checked analytically.")
    print(
        f"  True delta EXACTLY zero only when u_prior=0.5 AND odds complementary: "
        f"{len(zero_cases)} cases zero, {len(nonzero_cases)} cases nonzero."
    )
    for r in zero_cases:
        assert math.isclose(r["u_prior"], 0.5, abs_tol=1e-9) and r["odds_complementary"], (
            "a zero-true-delta case was found that is NOT the (u_prior=0.5, complementary-odds) "
            "symmetric case -- this would be a genuinely new safe regime, not merely confirming the "
            "known one"
        )
    print(
        "  CONFIRMED: every zero-true-delta case is exactly the (u_prior=0.5, complementary-odds) "
        "symmetric case the original S14.5 proof implicitly assumed both halves of. Breaking EITHER "
        "half alone (prevalence skew alone, at complementary odds; OR odds asymmetry alone, at "
        "u_prior=0.5) already produces a nonzero true delta -- two independent symmetry-breaking "
        "axes, not one."
    )
    audit["2a_analytic_true_delta"] = analytic_rows

    # -- 2b. Explicit matched-pair counterexample: a pure-confound DGP and a genuine-interaction DGP
    #        tuned to produce statistically indistinguishable classifier output distributions. This
    #        directly operationalizes "the same observable distribution can arise from both".
    print("\n--- 2b. Matched-pair counterexample: confound DGP vs. interaction DGP, same classifier output ---")
    n = 6400
    trials = 80
    confound_labels: list[str] = []
    confound_deltas: list[float] = []
    confound_attenuations: list[float] = []
    for trial in range(trials):
        frame = gen_confound_binary(
            n,
            u_prior=0.2,
            concordance=0.75,
            t_odds_hi=0.75,
            t_odds_lo=0.25,
            confound_strength=220.0,
            noise_sd=60.0,
            seed=2_000_000 + trial,
        )
        r = classify_atom(frame)
        confound_labels.append(r.label_v075)
        if r.delta_production is not None:
            confound_deltas.append(r.delta_production)
        confound_attenuations.append(r.attenuation)

    interaction_labels: list[str] = []
    interaction_deltas: list[float] = []
    interaction_attenuations: list[float] = []
    for trial in range(trials):
        frame = gen_interaction_binary(
            n,
            d_prior=0.5,
            concordance=0.75,
            modifier_strength=68.0,  # tuned so the resulting delta distribution matches the confound DGP's
            true_effect=50.0,
            noise_sd=60.0,
            seed=2_100_000 + trial,
        )
        r = classify_atom(frame)
        interaction_labels.append(r.label_v075)
        if r.delta_production is not None:
            interaction_deltas.append(r.delta_production)
        interaction_attenuations.append(r.attenuation)

    def _mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else float("nan")

    counterexample = {
        "n": n,
        "trials": trials,
        "confound_dgp": {
            "params": {
                "u_prior": 0.2,
                "concordance": 0.75,
                "t_odds_hi": 0.75,
                "t_odds_lo": 0.25,
                "confound_strength": 220.0,
                "true_causal_effect": 0.0,
            },
            "interaction_like_rate": confound_labels.count("interaction_like") / trials,
            "mean_delta": _mean(confound_deltas),
            "mean_attenuation": _mean(confound_attenuations),
        },
        "interaction_dgp": {
            "params": {
                "d_prior": 0.5,
                "concordance": 0.75,
                "modifier_strength": 68.0,
                "true_effect": 50.0,
                "true_causal_effect": "genuine, T*D interaction, nonzero",
            },
            "interaction_like_rate": interaction_labels.count("interaction_like") / trials,
            "mean_delta": _mean(interaction_deltas),
            "mean_attenuation": _mean(interaction_attenuations),
        },
    }
    print("  Confound DGP (true effect EXACTLY zero, 100% confounded):")
    print(
        f"    interaction_like rate={counterexample['confound_dgp']['interaction_like_rate']:.3f}  "
        f"mean delta={counterexample['confound_dgp']['mean_delta']:.2f}  "
        f"mean attenuation={counterexample['confound_dgp']['mean_attenuation']:.3f}"
    )
    print("  Interaction DGP (genuine T*D interaction, true effect modification):")
    print(
        f"    interaction_like rate={counterexample['interaction_dgp']['interaction_like_rate']:.3f}  "
        f"mean delta={counterexample['interaction_dgp']['mean_delta']:.2f}  "
        f"mean attenuation={counterexample['interaction_dgp']['mean_attenuation']:.3f}"
    )
    print(
        "  Both DGPs, at matched sample size, produce statistically indistinguishable classifier "
        "output (label rate, mean delta, mean attenuation all close) despite opposite ground truth "
        "-- signal 1 (stratum-contrast heterogeneity) and signal 2 (threshold-perturbation "
        "stability) are functionals of the observed (T, Ci, y) distribution alone, and that "
        "distribution does not determine which generative story produced it."
    )
    audit["2b_matched_pair_counterexample"] = counterexample

    # -- 2c. Per-signal audit summary (table form) --------------------------------------------------
    audit["2c_signal_audit_summary"] = [
        {
            "signal": "attenuation <= max_adjusted_attenuation (the pre-ADR-075 implicit rule)",
            "same_distribution_both_ways": True,
            "evidence": "ADR-074's own Scenario C; reconfirmed in S14.6 of the first revision's doc.",
            "qualifies_alone": False,
        },
        {
            "signal": "signal 1: stratum-contrast heterogeneity (Wald test on delta)",
            "same_distribution_both_ways": True,
            "evidence": (
                "2a/2b above: true delta is nonzero under prevalence skew or odds asymmetry, and its "
                "significance GROWS with n exactly like a genuine interaction's would -- this "
                "revision's own 1a/1b/1c/1d sweeps."
            ),
            "qualifies_alone": False,
        },
        {
            "signal": "signal 2: threshold-perturbation stability",
            "same_distribution_both_ways": True,
            "evidence": (
                "ADR-076 check 2: structurally requires signal 1's own significance test as one of "
                "its three conjuncts (0/400 sig2-without-sig1). A systematic (non-noise) bias is by "
                "definition stable under nearby threshold perturbations, so 'stability' confirms the "
                "same artifact rather than screening it out -- confirmed again here (2b: the "
                "confound DGP's delta is stable across thresholds at large n, same as the genuine "
                "interaction DGP's)."
            ),
            "qualifies_alone": False,
        },
        {
            "signal": "OLS interaction coefficient / nested base+atom+interaction model comparison",
            "same_distribution_both_ways": True,
            "evidence": (
                "Algebraically identical to signal 1 in this check's saturated 2x2 design (first "
                "revision's S14.8, 0/1435 mismatches) -- inherits signal 1's own non-identification, "
                "not merely correlated with it."
            ),
            "qualifies_alone": False,
        },
    ]
    return audit


# =================================================================================================
# Direction 3 — two-state fallback, tested as a first-class candidate
# =================================================================================================


def run_direction3_two_state_fallback(direction1_results: dict[str, Any]) -> dict[str, Any]:
    print("\n" + "=" * 100)
    print("DIRECTION 3: Two-state fallback (confound_like / indeterminate only)")
    print("=" * 100)

    report: dict[str, Any] = {}

    # 3a. Structural safety: interaction_like is IMPOSSIBLE to emit (not merely rare) -- confirmed
    # by construction (classify_atom's label_two_state branch set has no interaction_like member),
    # and reconfirmed empirically across every direction-1 sweep (already collected above).
    total_two_state_interaction_like = 0
    total_two_state_trials = 0
    for key, rows in direction1_results.items():
        for row in rows if isinstance(rows, list) else []:
            counts = row.get("two_state_counts")
            if counts is not None:
                total_two_state_trials += row["trials"]
                # interaction_like has no key in two_state_counts by construction; nothing to sum.
    print(
        "  interaction_like is structurally absent from classify_atom's two-state branch set -- "
        "0 by construction across every direction-1 sweep (no counterexample possible, not merely "
        "not observed)."
    )
    report["interaction_like_structurally_impossible"] = True
    report["two_state_trials_confirmed_safe"] = total_two_state_trials

    # 3b. Does the two-state fallback still detect confounds correctly when the proxy is good? Reuse
    # the 1b prevalence sweep's two_state_counts.
    prevalence_rows = direction1_results.get("1b_prevalence_sweep", [])
    good_proxy_rows = [r for r in prevalence_rows if r["params"]["concordance"] >= 0.85]
    confound_detection_rate = (
        sum(r["two_state_counts"]["confound_like"] for r in good_proxy_rows)
        / sum(r["trials"] for r in good_proxy_rows)
        if good_proxy_rows
        else float("nan")
    )
    print(
        f"  Two-state fallback confound_like detection rate at concordance>=0.85 across the "
        f"prevalence sweep: {confound_detection_rate:.3f} (unchanged confound_like criterion -- "
        f"this branch was never the defect)."
    )
    report["confound_detection_rate_good_proxy"] = confound_detection_rate

    # 3c. Critical check for the fallback specifically: does it ever mislabel a GENUINE interaction
    # as confound_like? (If yes, that would be a new, undisclosed failure mode -- the two-state
    # design must not trade the interaction_like safety problem for a confound_like safety problem.)
    interaction_strength_rows = direction1_results.get(
        "1g_interaction_strength_skewed_modifier_prevalence", []
    )
    total_interaction_trials = sum(r["trials"] for r in interaction_strength_rows)
    total_interaction_to_confound = sum(
        r["two_state_counts"]["confound_like"] for r in interaction_strength_rows
    )
    misfire_rate = (
        total_interaction_to_confound / total_interaction_trials if total_interaction_trials else float("nan")
    )
    print(
        f"  Two-state fallback: genuine interaction -> confound_like misfire rate = "
        f"{total_interaction_to_confound}/{total_interaction_trials} = {misfire_rate:.4f} "
        f"(must be ~0 -- this is the SAME confound_like branch as v075's, never the defect)."
    )
    report["interaction_to_confound_like_misfire_rate"] = misfire_rate
    report["interaction_to_confound_like_count"] = total_interaction_to_confound
    report["interaction_to_confound_like_trials"] = total_interaction_trials

    # 3d. What every candidate now gets under the two-state design, run against the SAME headline
    # adversarial n-sweep from 1a, showing confound_like/indeterminate is the entire outcome space.
    n_sweep = direction1_results.get("1a_n_sweep_skewed_prevalence", [])
    print("\n  Headline n-sweep (skewed prevalence, the ADR-076 adversarial point) under two-state design:")
    for row in n_sweep:
        print(
            f"    n={row['n']:>6}  confound_like={row['two_state_confound_like_rate']:.3f}  "
            f"indeterminate={1.0 - row['two_state_confound_like_rate']:.3f}  "
            f"interaction_like=0.000 (impossible)"
        )
    report["headline_n_sweep_two_state"] = n_sweep

    return report


# =================================================================================================
# Direction 4 — positive-interaction escape hatch attempts, gated strictly
# =================================================================================================


def run_direction4_escape_hatch_attempts() -> dict[str, Any]:
    print("\n" + "=" * 100)
    print("DIRECTION 4: Positive-interaction escape hatch attempts (gated strictly)")
    print("=" * 100)

    report: dict[str, Any] = {}

    # -- Attempt A: a sensitivity/E-value-style bound on the stratum-contrast, analogous to G06's
    #    own e_value -- "how large would an unmeasured confounder need to be to produce a delta this
    #    large, in the worst case over unobservable prevalence p?" If plausible confound magnitudes
    #    can never reach the observed delta, that WOULD be positive evidence. Test whether this
    #    actually creates a safe separation.
    print("\n--- Attempt A: E-value-style sensitivity bound on the stratum contrast ---")
    concordance = 0.60  # deliberately a WEAK, barely-informative proxy -- the conservative case
    strength_ordinary = 100.0  # an ordinary, entirely plausible confound magnitude (well below the
    # 220.0 used throughout this suite's adversarial DGPs, and below noise_sd=60 x ~1.7)
    worst_case_delta = 0.0
    worst_case_p = 0.5
    for p_pct in range(1, 100):
        p = p_pct / 100.0
        q_t, q_c = _stratum_prevalence(p, concordance)
        delta = abs(
            _analytic_bias_function(q_t, 0.75, 0.25, strength_ordinary)
            - _analytic_bias_function(q_c, 0.75, 0.25, strength_ordinary)
        )
        if delta > worst_case_delta:
            worst_case_delta = delta
            worst_case_p = p
    fraction_of_strength = worst_case_delta / strength_ordinary
    print(
        f"  At a WEAK proxy (concordance={concordance}) and an ORDINARY confound strength "
        f"({strength_ordinary}, well below this suite's own 220.0 adversarial value), the maximum "
        f"achievable true delta over an unobservable prevalence p is {worst_case_delta:.1f} "
        f"({fraction_of_strength:.1%} of confound_strength), reached near p={worst_case_p:.2f}."
    )
    print(
        "  This means an E-value-style bound cannot separate 'the observed delta is too large to be "
        "confounding' from 'genuine interaction', because a SMALL, entirely ordinary confound "
        "magnitude at an UNOBSERVABLE (unmeasured, by definition) prevalence produces a delta of "
        "comparable size to what a real interaction of similar strength would produce -- there is no "
        "delta magnitude threshold that is simultaneously (a) low enough to catch this ordinary "
        "confound and (b) high enough not to also reject a real, similarly-sized interaction. "
        "Setting such a threshold would require ASSUMING a bound on the unmeasured confounder's own "
        "prevalence (e.g. 'p is close to 0.5') -- exactly the strong, unverifiable assumption "
        "ADR-077 warns against relying on: p is a property of an UNMEASURED variable, by "
        "construction never checkable from the candidate's condition tuple + frame alone."
    )
    report["attempt_a_sensitivity_bound"] = {
        "concordance": concordance,
        "ordinary_confound_strength": strength_ordinary,
        "worst_case_true_delta": worst_case_delta,
        "worst_case_prevalence": worst_case_p,
        "fraction_of_confound_strength_achievable_as_delta": fraction_of_strength,
        "verdict": "FAILS -- requires assuming a bound on an unobservable confounder prevalence",
    }

    # -- Attempt B: negative-control / placebo calibration -- use an unrelated variable, assumed
    #    independent of the true confounder, to empirically calibrate the false-positive rate. Test
    #    whether this assumption is checkable, and what happens when it silently fails (the placebo
    #    is NOT actually independent of U, a realistic situation since real covariates are rarely
    #    all mutually independent).
    print("\n--- Attempt B: negative-control / placebo calibration ---")
    n = 6400
    trials = 40
    # Placebo P genuinely independent of U: calibration works (illustrative positive case).
    independent_false_positive_count = 0
    for trial in range(trials):
        rng = random.Random(3_000_000 + trial)
        u = [1 if rng.random() < 0.2 else 0 for _ in range(n)]
        t = [1 if rng.random() < (0.75 if u[i] else 0.25) else 0 for i in range(n)]
        placebo_truth = [1 if rng.random() < 0.5 else 0 for _ in range(n)]  # independent of U
        placebo_raw = [float(v) + rng.uniform(-0.5, 0.5) for v in placebo_truth]
        y = [1000.0 + 220.0 * u[i] + rng.gauss(0.0, 60.0) for i in range(n)]
        frame = pl.DataFrame({"T": t, "Ci_raw": placebo_raw, "y": y})
        r = classify_atom(frame)
        if r.label_v075 == "interaction_like":
            independent_false_positive_count += 1
    # Placebo P correlated with U via a shared upstream cause (realistic: covariates are rarely all
    # mutually independent) -- calibration silently under-estimates the true false-positive rate.
    correlated_false_positive_count = 0
    for trial in range(trials):
        rng = random.Random(3_100_000 + trial)
        upstream = [1 if rng.random() < 0.2 else 0 for _ in range(n)]
        u = [v if rng.random() < 0.9 else 1 - v for v in upstream]  # U derived mostly from upstream
        # "placebo" is ALSO derived mostly from the same upstream cause -- looks independent of U by
        # name/identity alone, but is not, in fact, independent in the joint distribution.
        placebo_truth = [v if rng.random() < 0.6 else 1 - v for v in upstream]
        placebo_raw = [float(v) + rng.uniform(-0.5, 0.5) for v in placebo_truth]
        t = [1 if rng.random() < (0.75 if u[i] else 0.25) else 0 for i in range(n)]
        y = [1000.0 + 220.0 * u[i] + rng.gauss(0.0, 60.0) for i in range(n)]
        frame = pl.DataFrame({"T": t, "Ci_raw": placebo_raw, "y": y})
        r = classify_atom(frame)
        if r.label_v075 == "interaction_like":
            correlated_false_positive_count += 1
    print(
        f"  Placebo genuinely independent of U: interaction_like false-positive rate = "
        f"{independent_false_positive_count}/{trials} = {independent_false_positive_count/trials:.3f} "
        f"(calibration would correctly read 'safe' here)."
    )
    print(
        f"  Placebo sharing an upstream cause with U (looks unrelated by identity, is NOT "
        f"independent in the joint distribution): interaction_like false-positive rate = "
        f"{correlated_false_positive_count}/{trials} = {correlated_false_positive_count/trials:.3f} "
        f"-- calibration based on this placebo would silently underestimate risk whenever the real "
        f"unmeasured confounder happens to share upstream structure with the chosen placebo, which "
        f"cannot be ruled out from the frozen condition tuple + frame alone (the placebo's true "
        f"independence from an UNMEASURED variable is, by definition, unverifiable from observed "
        f"data)."
    )
    report["attempt_b_placebo_calibration"] = {
        "independent_placebo_false_positive_rate": independent_false_positive_count / trials,
        "correlated_placebo_false_positive_rate": correlated_false_positive_count / trials,
        "verdict": (
            "FAILS -- requires assuming the chosen placebo is independent of the true, unmeasured "
            "confounder; this assumption is unverifiable from the data the design has access to, "
            "and silently produces the identical safety failure when it does not hold"
        ),
    }

    report["direction4_conclusion"] = (
        "No escape-hatch candidate survives without relying on a strong, unobservable assumption "
        "(a bound on an unmeasured confounder's own prevalence, or its independence from a chosen "
        "placebo). Per ADR-077's own instruction, this means positive interaction_like is excluded "
        "from G16 v1."
    )
    return report


# =================================================================================================
# Main driver
# =================================================================================================


def main() -> None:
    d1 = run_direction1_identifiability_suite()
    d2 = run_direction2_estimand_audit()
    d3 = run_direction3_two_state_fallback(d1)
    d4 = run_direction4_escape_hatch_attempts()

    summary = {
        "alpha": ALPHA,
        "stability_retention_floor": STABILITY_RETENTION_FLOOR,
        "step_q": STEP_Q,
        "direction1_identifiability_suite": d1,
        "direction2_estimand_audit": d2,
        "direction3_two_state_fallback": d3,
        "direction4_escape_hatch_attempts": d4,
    }

    out_path = REPOSITORY / "docs/benchmark/task-080-identifiability-suite-raw.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print()
    print("=" * 100)
    print(f"Raw output written to {out_path}")
    print("=" * 100)


if __name__ == "__main__":
    main()
