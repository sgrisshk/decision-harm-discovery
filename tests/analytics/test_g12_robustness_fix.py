"""Regression suite for the G12 robustness fix (validation contract v1.3.0, ADR-064, TASK-070).

**Neutral by construction, in the same posture `test_g05_multiplicity_fix.py` set for the ADR-015
G05 fix.** Every dataset here is invented: invented column names (`signal_metric`, `value_metric`,
`component_metric`, `cluster_key`), invented distributions, and data-generating processes whose
stability is *known a priori* because it is a property of how the rows were built, not something
measured afterwards. No test in this file reads `hidden_ground_truth.json`,
`synthetic_benchmark.py`, any analytical dataset, any frozen candidate artifact, or any real
outcome definition, and no threshold, step size, or admissibility rule under test was chosen by
looking at what it does to any real pattern. That is the point: these tests prove properties of the
*rule*, not that some particular candidate now passes.

The two regression families `TASK-070` requires:

1. **Threshold-perturbation geometry** (`test_family_1_*`): one identical effect shape, shifted
   along the percentile axis of an invented column, must receive an equivalent robustness verdict
   at every tested position — and a genuinely cutoff-dependent effect must still be rejected at
   every tested position, so the fix is not a blanket relaxation.
2. **Outcome semantics** (`test_family_2_*`): two synthetic patterns with *identical* primary-harm
   stability but different shares of that harm routed through a `decomposition_of` refit outcome
   must not receive different G12 verdicts because of that share alone.

Plus the two non-regression obligations: G12's other three check families must be untouched by the
fix, and the pre-v1.3.0 semantics must stay exactly executable so frozen runs remain reproducible.
"""

from __future__ import annotations

import random
from typing import Any, cast

import polars as pl
import pytest
from policy_analytics.outcomes import MissingDataPolicy, OutcomeDefinition, OutcomeRole
from policy_analytics.validation import apply as apply_module
from policy_analytics.validation.apply import (
    PERTURBATION_PERCENTILE_STEP,
    PERTURBATION_QUANTILES,
    Condition,
    _robustness_battery,
    _threshold_percentile,
    alternative_outcome_admissibility,
    rule_expr,
    split_stats,
)
from policy_analytics.validation.contract import (
    DEFAULT_THRESHOLDS,
    ROBUSTNESS_SEMANTICS_BY_CONTRACT_VERSION,
    ROBUSTNESS_SEMANTICS_VERSION,
    AlternativeOutcomeAdmissibility,
    RobustnessRefitState,
    RobustnessSemantics,
)
from policy_analytics.validation.input_contract import FeatureRole, ValidationInput

pytestmark = pytest.mark.analytics

ROWS = 4_000
SEED = 4242
NOISE_SD = 20.0
EFFECT = 400.0
BASELINE = 1_000.0
#: Swept, not chosen: the whole interior of the percentile range at a uniform spacing. The point of
#: a sweep is that no position in it is privileged, so no result here can have been fitted to one.
SWEPT_POSITIONS: tuple[float, ...] = tuple(round(0.10 + 0.05 * index, 2) for index in range(17))
#: A cutoff-dependent effect exists only this far past the boundary — a knife-edge artifact of
#: exactly where the cut falls, which is precisely what a robustness gate exists to catch.
SPIKE_WIDTH = 0.02


# --- invented outcomes: never the real registry ------------------------------------------------

NEUTRAL_TOTAL = OutcomeDefinition(
    outcome_id="invented_total_metric",
    role=OutcomeRole.PRIMARY,
    column="value_metric",
    unit="invented unit per row",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description="Invented total outcome for a truth-free G12 form regression. Not any real data.",
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Value Metric increases",
)
#: A structural *component* of the total: it carries the baseline and the noise but only part of
#: the harm channel. This is the shape that made the pre-v1.3.0 alternative-outcome refit report an
#: accounting identity rather than a stability measurement.
NEUTRAL_COMPONENT = OutcomeDefinition(
    outcome_id="invented_component_metric",
    role=OutcomeRole.SECONDARY,
    column="component_metric",
    unit="invented unit per row",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description="Invented decomposition component of `invented_total_metric`. Not any real data.",
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Component Metric increases",
    decomposition_of="invented_total_metric",
)
#: A second, *commensurable* measurement of the same construct — not a component of it. The one
#: shape v1.3.0 still admits as a gate-binding magnitude-parity refit.
NEUTRAL_COMMENSURABLE = OutcomeDefinition(
    outcome_id="invented_restated_total_metric",
    role=OutcomeRole.SECONDARY,
    column="restated_metric",
    unit="invented unit per row",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description="Invented alternative measurement of the same construct. Not any real data.",
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Restated Metric increases",
)


def _inputs(
    alternative_outcome_id: str | None = None, robustness_group_column: str | None = None
) -> ValidationInput:
    return ValidationInput(
        dataset_version="invented-v0",
        dataset_identity_sha256="0" * 64,
        feature_roles={"signal_metric": FeatureRole.DECISION_TIME},
        decision_time_features=frozenset({"signal_metric"}),
        adjustment_features=frozenset(),
        heterogeneity_column=None,
        seasonality_column=None,
        clustering_column="cluster_key",
        robustness_group_column=robustness_group_column,
        alternative_outcome_id=alternative_outcome_id,
    )


# --- invented data-generating processes ---------------------------------------------------------


def _feature_values(distribution: str, rng: random.Random) -> list[float]:
    if distribution == "uniform":
        return [round(rng.uniform(0.0, 100.0), 4) for _ in range(ROWS)]
    if distribution == "lognormal":
        return [round(rng.lognormvariate(3.0, 0.9), 4) for _ in range(ROWS)]
    if distribution == "coarse_integer":
        # A count-like column whose resolution is deliberately far too coarse for a fine percentile
        # step: the shape on which the pre-v1.3.0 fixed grid produced no estimate at all.
        return [float(min(9, int(rng.expovariate(1 / 2.5)))) for _ in range(ROWS)]
    raise ValueError(f"unknown invented distribution {distribution!r}")


def _effect_weight(dgp: str, position: float, threshold_position: float, operator: str) -> float:
    """Effect weight for a row, defined purely in percentile space relative to the exposed side.

    Because every process is defined relative to the rule's *own* exposed side, the same `dgp`
    means the same phenomenon at every swept threshold — which is what makes shifting the threshold
    a controlled comparison rather than a comparison of different effects.
    """
    inside = position >= threshold_position if operator == "ge" else position < threshold_position
    if not inside:
        return 0.0
    distance = position - threshold_position if operator == "ge" else threshold_position - position
    if dgp == "step_stable":
        # Maximally stable: uniform across the whole exposed side. Moving the cutoff cannot make
        # this effect appear or disappear, so every rejection of it is a false alarm.
        return 1.0
    if dgp == "spike_cutoff_dependent":
        # Genuinely an artifact of exactly where the cut falls. Every acceptance is a miss.
        return 1.0 if distance < SPIKE_WIDTH else 0.0
    raise ValueError(f"unknown invented dgp {dgp!r}")


def _frame(
    distribution: str,
    dgp: str,
    threshold_position: float,
    operator: str,
    component_share: float = 0.0,
) -> tuple[pl.DataFrame, float]:
    """One invented dataset plus the threshold value, in feature units.

    `component_share` is the share of the harm channel that reaches `component_metric` — the only
    thing that differs between regression family 2's two patterns. `restated_metric` always carries
    the whole harm channel, so it is a commensurable restatement rather than a component.
    """
    rng = random.Random(SEED)
    values = _feature_values(distribution, rng)
    order = sorted(range(len(values)), key=lambda index: values[index])
    position = [0.0] * len(values)
    for rank, index in enumerate(order):
        position[index] = rank / len(values)
    series = pl.Series("signal_metric", values)
    threshold = float(cast(float, series.quantile(threshold_position, interpolation="nearest")))
    total: list[float] = []
    component: list[float] = []
    restated: list[float] = []
    for own_position in position:
        harm = _effect_weight(dgp, own_position, threshold_position, operator) * EFFECT
        noise = rng.gauss(0.0, NOISE_SD)
        total.append(round(BASELINE + noise + harm, 6))
        component.append(round(BASELINE + noise + component_share * harm, 6))
        restated.append(round(BASELINE + noise + harm, 6))
    frame = pl.DataFrame(
        {
            "signal_metric": values,
            "value_metric": total,
            "component_metric": component,
            "restated_metric": restated,
            "cluster_key": [f"c{index % 40}" for index in range(ROWS)],
        }
    )
    return frame, threshold


def _battery(
    frame: pl.DataFrame,
    threshold: float,
    operator: str,
    semantics: RobustnessSemantics,
    inputs: ValidationInput | None = None,
    outcome: OutcomeDefinition = NEUTRAL_TOTAL,
) -> Any:
    conditions = (Condition("signal_metric", cast(Any, operator), round(threshold, 8)),)
    mask = frame.select(rule_expr(conditions).alias("m"))["m"]
    dev = split_stats(frame, mask, outcome, "development")
    assert dev is not None, "invented fixture must produce both an exposed and a comparison group"
    return _robustness_battery(
        frame, conditions, mask, outcome, dev, inputs or _inputs(), semantics
    )


def _g12_satisfied(battery: Any) -> bool:
    """G12's own conjunction, applied exactly as `_validate_one` applies it."""
    return bool(
        battery.evaluated
        and battery.sign_agreement >= DEFAULT_THRESHOLDS.min_robustness_sign_agreement
        and battery.max_magnitude_deviation <= DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation
    )


# --- the step size is inherited, not invented ---------------------------------------------------


def test_the_one_bin_step_is_the_legacy_grids_own_half_width() -> None:
    """v1.3.0 changed the perturbation's *reference point*, never its size.

    The pre-v1.3.0 pair (0.15, 0.25) is symmetric about a q0.20 anchor with a half-width of 0.05
    percentile points. v1.3.0 applies that same 0.05 step about each candidate's own threshold
    instead, so no new tunable constant was introduced by this fix and nothing about the step's
    magnitude could have been fitted to any observed result.
    """
    low, high = min(PERTURBATION_QUANTILES), max(PERTURBATION_QUANTILES)
    assert pytest.approx((high - low) / 2.0) == PERTURBATION_PERCENTILE_STEP
    assert pytest.approx(0.05) == PERTURBATION_PERCENTILE_STEP


def test_the_legacy_grid_is_the_new_grid_at_exactly_one_threshold_position() -> None:
    """The two semantics coincide for a threshold at the legacy pair's own anchor, and only there.

    This is the mechanical statement of the defect: the shipped implementation *was* a one-bin
    relative step, for a candidate whose threshold happened to sit at q0.20, and was a
    progressively larger absolute displacement everywhere else.
    """
    anchor = sum(PERTURBATION_QUANTILES) / len(PERTURBATION_QUANTILES)
    assert anchor == pytest.approx(0.20)
    at_anchor = (
        round(anchor - PERTURBATION_PERCENTILE_STEP, 10),
        round(anchor + PERTURBATION_PERCENTILE_STEP, 10),
    )
    assert at_anchor == pytest.approx(PERTURBATION_QUANTILES)
    elsewhere = (
        round(0.75 - PERTURBATION_PERCENTILE_STEP, 10),
        round(0.75 + PERTURBATION_PERCENTILE_STEP, 10),
    )
    assert elsewhere != pytest.approx(PERTURBATION_QUANTILES)


# --- regression family 1: threshold-perturbation geometry ---------------------------------------


@pytest.mark.parametrize("distribution", ["uniform", "lognormal"])
@pytest.mark.parametrize("operator", ["ge", "lt"])
def test_family_1_a_stable_effect_passes_at_every_position_on_the_percentile_axis(
    distribution: str, operator: str
) -> None:
    """The required regression: one effect shape, shifted along an invented column's percentile
    axis, must get an equivalent verdict everywhere — proving the *fix*, not a pattern, changed.
    """
    verdicts = {
        position: _g12_satisfied(
            _battery(
                *_frame(distribution, "step_stable", position, operator),
                operator,
                ROBUSTNESS_SEMANTICS_VERSION,
            )
        )
        for position in SWEPT_POSITIONS
    }
    assert all(verdicts.values()), (
        "a maximally stable effect must clear G12's threshold check wherever its cutoff sits; "
        f"failed at {sorted(p for p, ok in verdicts.items() if not ok)}"
    )


@pytest.mark.parametrize("distribution", ["uniform", "lognormal"])
@pytest.mark.parametrize("operator", ["ge", "lt"])
def test_family_1_a_cutoff_dependent_effect_is_rejected_at_every_position(
    distribution: str, operator: str
) -> None:
    """The other half of family 1, and the one that makes it a fix rather than a relaxation.

    An effect that exists only within `SPIKE_WIDTH` of its own boundary *is* an artifact of where
    the cut falls. If widening the passing window for stable effects also admitted these, the gate
    would have lost the discriminating power it exists for.
    """
    verdicts = {
        position: _g12_satisfied(
            _battery(
                *_frame(distribution, "spike_cutoff_dependent", position, operator),
                operator,
                ROBUSTNESS_SEMANTICS_VERSION,
            )
        )
        for position in SWEPT_POSITIONS
    }
    assert not any(verdicts.values()), (
        "a knife-edge, genuinely cutoff-dependent effect must still be rejected wherever its "
        f"cutoff sits; passed at {sorted(p for p, ok in verdicts.items() if ok)}"
    )


def test_family_1_the_pre_fix_semantics_fail_this_same_regression() -> None:
    """The regression is only meaningful if the old semantics actually fail it. They do, both ways.

    Under `FIXED_QUANTILE_V1` the same maximally stable effect is rejected outside a narrow band of
    threshold positions *and* the same knife-edge effect is accepted inside part of that band — the
    bidirectional, position-driven misclassification `TASK-069` item 2 measured.
    """
    stable = {
        position: _g12_satisfied(
            _battery(
                *_frame("uniform", "step_stable", position, "ge"),
                "ge",
                RobustnessSemantics.FIXED_QUANTILE_V1,
            )
        )
        for position in SWEPT_POSITIONS
    }
    spike = {
        position: _g12_satisfied(
            _battery(
                *_frame("uniform", "spike_cutoff_dependent", position, "ge"),
                "ge",
                RobustnessSemantics.FIXED_QUANTILE_V1,
            )
        )
        for position in SWEPT_POSITIONS
    }
    assert not all(stable.values()), "old semantics were supposed to reject some stable effects"
    assert any(stable.values()), "old semantics were supposed to accept stable effects somewhere"
    assert any(spike.values()), "old semantics were supposed to miss some knife-edge effects"
    # And the misses sit inside the same band where stable effects pass — the signature of a gate
    # whose verdict tracks threshold position rather than stability.
    missed = {position for position, ok in spike.items() if ok}
    passed_stable = {position for position, ok in stable.items() if ok}
    assert missed <= passed_stable


def test_family_1_deviation_no_longer_tracks_threshold_position() -> None:
    """The measured quantity itself, not just the verdict, must stop tracking threshold position.

    Under the old grid the deviation reported for a maximally stable effect climbs monotonically
    with the threshold's percentile and crosses the ceiling — it is a function of position, not of
    the effect. Under the fix the residual variation is (a) bounded well under the ceiling
    everywhere and (b) *symmetric* about the middle of the column, which is the signature of a
    quantity that depends only on how big a relative change a fixed percentile step makes to the
    exposed group at that position, with no directional bias left. A `+/-`0.05-point step is
    inherently a larger relative move at the tails than in the middle; that residual geometry is
    real, disclosed, and — unlike the old grid's — never enough to reject a stable effect.
    """
    old = [
        _battery(
            *_frame("uniform", "step_stable", position, "ge"),
            "ge",
            RobustnessSemantics.FIXED_QUANTILE_V1,
        ).max_magnitude_deviation
        for position in SWEPT_POSITIONS
    ]
    new = [
        _battery(
            *_frame("uniform", "step_stable", position, "ge"),
            "ge",
            ROBUSTNESS_SEMANTICS_VERSION,
        ).max_magnitude_deviation
        for position in SWEPT_POSITIONS
    ]
    ceiling = DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation
    assert max(old) - min(old) > 0.7
    assert max(old) > ceiling  # the old grid rejects this stable effect at some positions
    assert max(new) - min(new) < 0.3
    assert max(new) < ceiling  # the fix never rejects it at any position
    # Symmetric about the column's midpoint: no percentile band is privileged any more.
    for low, high in zip(new, reversed(new), strict=True):
        assert low == pytest.approx(high, abs=0.02)
    # The old grid is emphatically not symmetric — it is monotone in the threshold's percentile.
    assert old == sorted(old[:4], reverse=True) + sorted(old[4:])


# --- regression family 1, coarse columns: named states, never silent failure ---------------------


def test_coarse_integer_column_produces_estimates_instead_of_silent_no_estimate_failure() -> None:
    """The pre-fix grid produced *no estimate at all* on a coarse integer column, for every
    process: both fixed quantiles collapsed onto the column's minimum, so one perturbed rule
    selected every row and the other selected none, and the gate failed regardless of content.
    v1.3.0 snaps to the column's own adjacent level, which is that column's true one-bin move.
    """
    frame, threshold = _frame("coarse_integer", "step_stable", 0.70, "ge")
    old = _battery(frame, threshold, "ge", RobustnessSemantics.FIXED_QUANTILE_V1)
    new = _battery(frame, threshold, "ge", ROBUSTNESS_SEMANTICS_VERSION)

    assert not _g12_satisfied(old)
    assert new.evaluated
    assert _g12_satisfied(new)
    states = new.diagnostics["robustness_threshold_refit_states"]
    assert states[RobustnessRefitState.ESTIMATED.value] == 2
    assert states[RobustnessRefitState.DEGENERATE_NO_CONTRAST.value] == 0
    assert states[RobustnessRefitState.VACUOUS_IDENTICAL_RULE.value] == 0
    # The two refits move to the column's genuinely adjacent levels — one down, one up. At this
    # column's resolution the requested percentile step happens to reach the level below on its
    # own; the step above has to snap, and says so.
    refits = new.diagnostics["robustness_threshold_refits"]
    perturbed = sorted(cast(float, refit["perturbed_value"]) for refit in refits)
    levels = sorted({float(value) for value in frame["signal_metric"].unique().to_list()})
    index = levels.index(threshold)
    assert perturbed == [levels[index - 1], levels[index + 1]]
    assert any(refit["snapped_to_adjacent_level"] for refit in refits)


def test_a_threshold_at_the_columns_extreme_yields_a_disclosed_one_sided_check() -> None:
    """At a column's extreme only one direction exists, and that is stated rather than hidden.

    The pre-fix grid had the same problem invisibly — its "two independent perturbations" were
    sometimes the same rule evaluated twice — and reported a two-sided check either way. Here the
    unavailable direction gets its own named state and is counted, so the gate's own detail says
    the check was one-sided. A one-sided perturbation is still a real robustness test (does the
    effect survive including the next level?), so the gate is evaluated, not refused.
    """
    frame, _ = _frame("coarse_integer", "step_stable", 0.50, "ge")
    top = max(float(value) for value in frame["signal_metric"].to_list())
    battery = _battery(frame, top, "ge", ROBUSTNESS_SEMANTICS_VERSION)

    assert battery.evaluated is True
    states = battery.diagnostics["robustness_threshold_refit_states"]
    assert states[RobustnessRefitState.UNREPRESENTABLE_STEP.value] == 1
    assert states[RobustnessRefitState.ESTIMATED.value] == 1
    # The refit that could not be taken is recorded, not dropped.
    assert any(
        refit["state"] == RobustnessRefitState.UNREPRESENTABLE_STEP.value
        for refit in battery.diagnostics["robustness_threshold_refits"]
    )


def test_a_threshold_with_no_usable_perturbation_at_all_is_not_evaluated() -> None:
    """When *neither* direction can produce an estimate, G12 cannot answer its own question.

    A two-level column with the threshold on its upper level: stepping up has no level to move to,
    and stepping down broadens the rule to every row, leaving no comparison group. The disclosed
    outcome is NOT_EVALUATED with both named states and a stated reason — which the contract treats
    exactly like a failure for grading (§3), but which a reader can tell apart from "this effect
    moved when we perturbed the cutoff". Never a silent pass, never a silent fail.
    """
    rng = random.Random(SEED)
    levels = [0.0 if index % 2 else 1.0 for index in range(ROWS)]
    frame = pl.DataFrame(
        {
            "signal_metric": levels,
            "value_metric": [
                round(BASELINE + rng.gauss(0.0, NOISE_SD) + (EFFECT if level else 0.0), 6)
                for level in levels
            ],
            "cluster_key": [f"c{index % 40}" for index in range(ROWS)],
        }
    )
    battery = _battery(frame, 1.0, "ge", ROBUSTNESS_SEMANTICS_VERSION)

    assert battery.evaluated is False
    assert battery.not_evaluated_reason is not None
    assert "signal_metric ge" in battery.not_evaluated_reason
    states = battery.diagnostics["robustness_threshold_refit_states"]
    assert states[RobustnessRefitState.ESTIMATED.value] == 0
    assert states[RobustnessRefitState.UNREPRESENTABLE_STEP.value] == 1
    assert states[RobustnessRefitState.DEGENERATE_NO_CONTRAST.value] == 1


def test_the_one_bin_step_is_measured_from_the_candidates_own_threshold() -> None:
    """The mechanical property the whole fix rests on, checked directly on an invented column."""
    frame, threshold = _frame("uniform", "step_stable", 0.80, "ge")
    own = _threshold_percentile(frame["signal_metric"], threshold)
    battery = _battery(frame, threshold, "ge", ROBUSTNESS_SEMANTICS_VERSION)
    refits = battery.diagnostics["robustness_threshold_refits"]
    realised = sorted(
        _threshold_percentile(frame["signal_metric"], cast(float, refit["perturbed_value"]))
        for refit in refits
    )
    assert realised[0] == pytest.approx(own - PERTURBATION_PERCENTILE_STEP, abs=0.01)
    assert realised[1] == pytest.approx(own + PERTURBATION_PERCENTILE_STEP, abs=0.01)
    # Exactly one refit narrows the exposed group and exactly one broadens it, whatever the
    # operator — the "direction" half of the contract's one-bin semantics.
    exposed = [cast(int, refit["n_exposed"]) for refit in refits]
    base = frame.select(rule_expr((Condition("signal_metric", "ge", threshold),)).alias("m"))[
        "m"
    ].sum()
    assert min(exposed) < base < max(exposed)


# --- regression family 2: outcome semantics -----------------------------------------------------


@pytest.fixture
def invented_outcome_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register the *invented* outcomes for the duration of one test.

    `_robustness_battery` resolves a manifest-declared alternative outcome through the reviewed
    registry. Patching it with invented definitions keeps regression family 2 truth-free: the test
    never touches, and cannot be influenced by, any real outcome definition.
    """
    monkeypatch.setattr(
        apply_module,
        "OUTCOME_BY_ID",
        {
            NEUTRAL_TOTAL.outcome_id: NEUTRAL_TOTAL,
            NEUTRAL_COMPONENT.outcome_id: NEUTRAL_COMPONENT,
            NEUTRAL_COMMENSURABLE.outcome_id: NEUTRAL_COMMENSURABLE,
        },
    )


@pytest.mark.usefixtures("invented_outcome_registry")
def test_family_2_the_decomposition_share_alone_no_longer_changes_the_verdict() -> None:
    """The required regression: identical primary-harm stability, different component shares.

    Both patterns have a byte-identical `value_metric` and therefore identical primary effects and
    identical stability. They differ only in how much of that harm reaches a `decomposition_of`
    outcome — 0% for one, 90% for the other. Under v1.3.0 they must receive the same G12 verdict,
    because the share is a property of the outcome algebra, not of the pattern.
    """
    inputs = _inputs(alternative_outcome_id=NEUTRAL_COMPONENT.outcome_id)
    invisible_frame, threshold = _frame("uniform", "step_stable", 0.50, "ge", component_share=0.0)
    visible_frame, _ = _frame("uniform", "step_stable", 0.50, "ge", component_share=0.9)
    assert invisible_frame["value_metric"].to_list() == visible_frame["value_metric"].to_list()

    invisible = _battery(
        invisible_frame, threshold, "ge", ROBUSTNESS_SEMANTICS_VERSION, inputs=inputs
    )
    visible = _battery(visible_frame, threshold, "ge", ROBUSTNESS_SEMANTICS_VERSION, inputs=inputs)

    assert _g12_satisfied(invisible) == _g12_satisfied(visible) is True
    assert invisible.checks_run == visible.checks_run
    assert invisible.max_magnitude_deviation == pytest.approx(visible.max_magnitude_deviation)
    for battery in (invisible, visible):
        assert (
            battery.diagnostics["robustness_alternative_outcome_admissibility"]
            == AlternativeOutcomeAdmissibility.INADMISSIBLE_DECOMPOSITION.value
        )


@pytest.mark.usefixtures("invented_outcome_registry")
def test_family_2_the_pre_fix_semantics_fail_this_same_regression() -> None:
    """Under v1.2.0 the very same two patterns get *different* verdicts, from the share alone."""
    inputs = _inputs(alternative_outcome_id=NEUTRAL_COMPONENT.outcome_id)
    invisible_frame, threshold = _frame("uniform", "step_stable", 0.50, "ge", component_share=0.0)
    visible_frame, _ = _frame("uniform", "step_stable", 0.50, "ge", component_share=0.9)

    invisible = _battery(
        invisible_frame,
        threshold,
        "ge",
        RobustnessSemantics.FIXED_QUANTILE_V1,
        inputs=inputs,
    )
    visible = _battery(
        visible_frame, threshold, "ge", RobustnessSemantics.FIXED_QUANTILE_V1, inputs=inputs
    )
    assert invisible.max_magnitude_deviation > visible.max_magnitude_deviation
    # The larger deviation is ~100%: the component sees none of the harm, so the refit reports
    # "the effect vanished" for an effect that is stable by construction.
    assert invisible.max_magnitude_deviation == pytest.approx(1.0, abs=0.02)


@pytest.mark.usefixtures("invented_outcome_registry")
def test_an_inadmissible_alternative_outcome_is_disclosed_never_silently_dropped() -> None:
    """The named state must be visible, with the estimate itself still reported."""
    inputs = _inputs(alternative_outcome_id=NEUTRAL_COMPONENT.outcome_id)
    frame, threshold = _frame("uniform", "step_stable", 0.50, "ge", component_share=0.0)
    battery = _battery(frame, threshold, "ge", ROBUSTNESS_SEMANTICS_VERSION, inputs=inputs)

    diagnostic = battery.diagnostics["robustness_alternative_outcome_diagnostic"]
    assert diagnostic is not None
    assert diagnostic["outcome_id"] == NEUTRAL_COMPONENT.outcome_id
    assert (
        diagnostic["admissibility"]
        == AlternativeOutcomeAdmissibility.INADMISSIBLE_DECOMPOSITION.value
    )
    # The number is still there — a reader sees both the measurement and why it is not evidence.
    assert diagnostic["magnitude_deviation"] == pytest.approx(1.0, abs=0.02)
    names = apply_module._robustness_test_names(inputs, battery.diagnostics)  # pyright: ignore[reportPrivateUsage]
    assert any("not_gate_binding" in name for name in names)


@pytest.mark.usefixtures("invented_outcome_registry")
def test_a_commensurable_alternative_outcome_still_binds_the_gate() -> None:
    """The fix removes a category error, not the alternative-outcome check itself.

    An outcome that restates the same construct on the same scale is still admitted, still run, and
    still counted — so G12 keeps a genuine outcome-definition robustness test wherever a dataset
    actually offers one.
    """
    inputs = _inputs(alternative_outcome_id=NEUTRAL_COMMENSURABLE.outcome_id)
    frame, threshold = _frame("uniform", "step_stable", 0.50, "ge")
    battery = _battery(frame, threshold, "ge", ROBUSTNESS_SEMANTICS_VERSION, inputs=inputs)
    baseline = _battery(frame, threshold, "ge", ROBUSTNESS_SEMANTICS_VERSION, inputs=_inputs())

    assert (
        battery.diagnostics["robustness_alternative_outcome_admissibility"]
        == AlternativeOutcomeAdmissibility.ADMISSIBLE.value
    )
    assert battery.diagnostics["robustness_alternative_outcome_diagnostic"] is None
    assert battery.checks_run == baseline.checks_run + 1
    assert _g12_satisfied(battery)


def test_admissibility_is_a_property_of_the_outcome_contract_alone() -> None:
    """Unit coverage of the rule, on invented definitions, with one deterministic reason each."""
    assert (
        alternative_outcome_admissibility(NEUTRAL_TOTAL, None)
        is AlternativeOutcomeAdmissibility.NOT_DECLARED
    )
    assert (
        alternative_outcome_admissibility(NEUTRAL_TOTAL, NEUTRAL_COMMENSURABLE)
        is AlternativeOutcomeAdmissibility.ADMISSIBLE
    )
    assert (
        alternative_outcome_admissibility(NEUTRAL_TOTAL, NEUTRAL_COMPONENT)
        is AlternativeOutcomeAdmissibility.INADMISSIBLE_DECOMPOSITION
    )
    # Symmetric: a component may not use its own total as an equal-footing refit either.
    assert (
        alternative_outcome_admissibility(NEUTRAL_COMPONENT, NEUTRAL_TOTAL)
        is AlternativeOutcomeAdmissibility.INADMISSIBLE_DECOMPOSITION
    )
    # Two components of one parent are not commensurable with each other either.
    sibling = OutcomeDefinition(
        outcome_id="invented_second_component",
        role=OutcomeRole.SECONDARY,
        column="second_component",
        unit="invented unit per row",
        higher_is_worse=True,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description="Invented sibling component. Not any real data.",
        valid_range=(-1.0e9, 1.0e9),
        aggregation_rule="mean of the outcome column over the group",
        harm_direction_phrase="Second Component increases",
        decomposition_of="invented_total_metric",
    )
    assert (
        alternative_outcome_admissibility(NEUTRAL_COMPONENT, sibling)
        is AlternativeOutcomeAdmissibility.INADMISSIBLE_DECOMPOSITION
    )
    rate = OutcomeDefinition(
        outcome_id="invented_rate_metric",
        role=OutcomeRole.SECONDARY,
        column="rate_metric",
        unit="rate, proportion in [0, 1]",
        higher_is_worse=True,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description="Invented rate outcome on a different scale. Not any real data.",
        valid_range=(0.0, 1.0),
        aggregation_rule="mean of the outcome column over the group",
        harm_direction_phrase="Rate Metric increases",
    )
    assert (
        alternative_outcome_admissibility(NEUTRAL_TOTAL, rate)
        is AlternativeOutcomeAdmissibility.INADMISSIBLE_UNIT_MISMATCH
    )
    mnar = OutcomeDefinition(
        outcome_id="invented_mnar_metric",
        role=OutcomeRole.SECONDARY,
        column="mnar_metric",
        unit="invented unit per row",
        higher_is_worse=True,
        missing_data_policy=MissingDataPolicy.MNAR_BOUNDED,
        description="Invented outcome whose missingness depends on itself. Not any real data.",
        valid_range=(-1.0e9, 1.0e9),
        aggregation_rule="mean of the outcome column over the group",
        harm_direction_phrase="Mnar Metric increases",
    )
    assert (
        alternative_outcome_admissibility(NEUTRAL_TOTAL, mnar)
        is AlternativeOutcomeAdmissibility.INADMISSIBLE_MISSINGNESS_POLICY
    )


# --- non-regression: G12's other three check families are untouched -----------------------------


@pytest.mark.usefixtures("invented_outcome_registry")
@pytest.mark.parametrize("dgp", ["step_stable", "spike_cutoff_dependent"])
@pytest.mark.parametrize("position", [0.20, 0.50, 0.80])
def test_the_other_check_families_are_byte_identical_across_the_two_semantics(
    dgp: str, position: float
) -> None:
    """`TASK-070` scope item 6: leave-one-cluster-out and winsorisation must be unchanged.

    Both semantics are run on the same inputs and the refits of the two families the fix does *not*
    touch are compared directly — including their treatment of a refit that produces no estimate,
    which for these families is a genuine fragility signal rather than an artifact of a
    perturbation grid, and is therefore deliberately left exactly as it was.
    """
    inputs = _inputs(
        alternative_outcome_id=NEUTRAL_COMMENSURABLE.outcome_id,
        robustness_group_column="cluster_key",
    )
    frame, threshold = _frame("uniform", dgp, position, "ge")
    conditions = (Condition("signal_metric", "ge", round(threshold, 8)),)
    mask = frame.select(rule_expr(conditions).alias("m"))["m"]
    dev = split_stats(frame, mask, NEUTRAL_TOTAL, "development")
    assert dev is not None

    def _other_families() -> list[tuple[str, float | None]]:
        """Re-run the two untouched families exactly as `_robustness_battery` runs them."""
        recorded: list[tuple[str, float | None]] = []
        for group_value in frame["cluster_key"].unique().to_list():
            subset = frame.filter(pl.col("cluster_key") != group_value)  # pyright: ignore[reportUnknownMemberType]
            submask = subset.select(rule_expr(conditions).alias("m"))["m"]
            stats = split_stats(subset, submask, NEUTRAL_TOTAL, "development")
            recorded.append(
                (f"loo:{group_value}", None if stats is None else stats.harm_per_booking)
            )
        low = frame[NEUTRAL_TOTAL.column].quantile(0.01)
        high = frame[NEUTRAL_TOTAL.column].quantile(0.99)
        winsor = frame.with_columns(
            pl.col(NEUTRAL_TOTAL.column).clip(cast(float, low), cast(float, high))
        )
        stats = split_stats(winsor, mask, NEUTRAL_TOTAL, "development")
        recorded.append(("winsor", None if stats is None else stats.harm_per_booking))
        return sorted(recorded)

    expected = _other_families()
    old = _robustness_battery(
        frame,
        conditions,
        mask,
        NEUTRAL_TOTAL,
        dev,
        inputs,
        RobustnessSemantics.FIXED_QUANTILE_V1,
    )
    new = _robustness_battery(
        frame, conditions, mask, NEUTRAL_TOTAL, dev, inputs, ROBUSTNESS_SEMANTICS_VERSION
    )
    # The untouched families contribute the same refits under both semantics: same count, same
    # estimates. The only difference in `checks_run` is the threshold family's own refit count.
    n_untouched = len(expected)
    assert n_untouched == frame["cluster_key"].n_unique() + 1
    assert old.checks_run - n_untouched - 1 == len(PERTURBATION_QUANTILES)
    assert (
        new.checks_run - n_untouched - 1
        == new.diagnostics["robustness_threshold_refit_states"][
            RobustnessRefitState.ESTIMATED.value
        ]
    )
    assert _other_families() == expected  # deterministic, and unaffected by either battery run


def test_the_fix_touches_no_gate_other_than_g12() -> None:
    """Scope item 6's other half: G06's adjustment machinery is byte-identical to v1.2.0.

    The G06 selection rule is a pure function of cardinality and coverage. This pins that the
    TASK-070 change did not perturb it, on an invented confound whose structure is known by
    construction, using the same public helpers `test_validation_apply.py` exercises.
    """
    from policy_analytics.validation.apply import (
        _select_adjustment_columns,
        _stratified_adjustment,
    )

    rng = random.Random(SEED)
    rows = 1_200
    confound = [rng.choice(["a", "b"]) for _ in range(rows)]
    irrelevant = [rng.choice(["x", "y", "z"]) for _ in range(rows)]
    exposed = [value == "a" and rng.random() < 0.7 for value in confound]
    outcome_values = [
        BASELINE + (300.0 if value == "a" else 0.0) + rng.gauss(0.0, 25.0) for value in confound
    ]
    frame = pl.DataFrame(
        {
            "real_confound": confound,
            "irrelevant_a": irrelevant,
            "value_metric": outcome_values,
        }
    )
    mask = pl.Series("m", exposed)
    selected = _select_adjustment_columns(  # pyright: ignore[reportPrivateUsage]
        frame,
        mask,
        NEUTRAL_TOTAL,
        ("real_confound", "irrelevant_a"),
        DEFAULT_THRESHOLDS.min_confounder_stratum_coverage,
    )
    assert "real_confound" in selected
    raw = split_stats(frame, mask, NEUTRAL_TOTAL, "development")
    assert raw is not None
    adjusted, coverage = _stratified_adjustment(frame, mask, NEUTRAL_TOTAL, selected)  # pyright: ignore[reportPrivateUsage]
    assert coverage >= DEFAULT_THRESHOLDS.min_confounder_stratum_coverage
    # Adjusting on the real confound removes almost all of the raw gap it manufactured.
    assert abs(adjusted) < abs(raw.raw_difference) * 0.25


# --- versioning -------------------------------------------------------------------------------


def test_every_contract_version_maps_to_the_semantics_that_shipped_with_it() -> None:
    """The mapping that makes an older frozen run reproducible rather than merely un-re-graded."""
    for version in ("1.0.0", "1.1.0", "1.2.0"):
        assert (
            ROBUSTNESS_SEMANTICS_BY_CONTRACT_VERSION[version]
            is RobustnessSemantics.FIXED_QUANTILE_V1
        )
    assert (
        ROBUSTNESS_SEMANTICS_BY_CONTRACT_VERSION["1.3.0"] is RobustnessSemantics.ONE_BIN_RELATIVE_V2
    )
    assert ROBUSTNESS_SEMANTICS_VERSION is RobustnessSemantics.ONE_BIN_RELATIVE_V2


def test_the_battery_return_stays_positionally_compatible_with_the_pre_fix_tuple() -> None:
    """Existing diagnostic callers unpack three positional values; that must keep working."""
    frame, threshold = _frame("uniform", "step_stable", 0.50, "ge")
    battery = _battery(frame, threshold, "ge", ROBUSTNESS_SEMANTICS_VERSION)
    sign_agreement, max_deviation, checks_run = battery[0], battery[1], battery[2]
    assert (sign_agreement, max_deviation, checks_run) == (
        battery.sign_agreement,
        battery.max_magnitude_deviation,
        battery.checks_run,
    )
