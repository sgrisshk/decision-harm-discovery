"""`G16_CANDIDATE_COMPOSITION_SAFETY` (`TASK-081`): DIAGNOSTIC-correctness tests only.

Per `TASK-081`'s control level 3, this file checks whether `confound_like` vs. `indeterminate`
was the "right" call for a constructed case (a genuine confound labeled `confound_like`; a
genuine effect modifier never labeled `confound_like`). **A diagnostic misclassification here
must never be read as a safety failure** -- both states cap identically (see
`test_g16_safety.py`), which is exactly why label-correctness lives in its own file, with its
own, explicitly non-safety-critical framing, per `ADR-075`'s asymmetric-loss discipline
(a false confound landing `indeterminate` is acceptable; the only truly unsafe direction, a real
confound landing an uncapped release, is structurally impossible per `test_g16_structural.py` --
there is no uncapped release to land in at all).

DGPs here mirror `scripts/diagnose_task080_composition_classifier_revision.py`'s own already-
reviewed (`ADR-075`/`ADR-076`/`ADR-077`/`ADR-078`) synthetic constructions, calling the real,
unmodified `policy_analytics.validation.apply._stratified_adjustment` throughout -- never a
reimplementation of the estimator.
"""

from __future__ import annotations

import random

import polars as pl
import pytest
from policy_analytics.outcomes.contract import MissingDataPolicy, OutcomeDefinition, OutcomeRole
from policy_analytics.validation.apply import _stratified_adjustment
from policy_analytics.validation.composition_safety import (
    CompositionAtomClassification,
    classify_composition_safety,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS

pytestmark = pytest.mark.analytics

OUTCOME = OutcomeDefinition(
    outcome_id="g16_diagnostic_test_metric",
    role=OutcomeRole.PRIMARY,
    column="y",
    unit="unit",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description=(
        "Neutral synthetic outcome for G16's diagnostic tests. Unrelated to any real domain."
    ),
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Value increases",
)


def _atom_masks(
    frame: pl.DataFrame, features: tuple[str, ...]
) -> tuple[tuple[str, pl.Series], ...]:
    return tuple((feature, frame[feature] == 1) for feature in features)


def _proxy(rng: random.Random, truth: list[int]) -> list[int]:
    """A near-exact binary proxy for `truth` (a small, fixed flip probability), giving the
    leave-one-out atom high concordance -- the regime the design document's own §14.2 ladder
    shows `confound_like` actually fires in (see that section for the full, honestly-disclosed
    prevalence-dependence of when this branch does and does not fire).
    """
    return [t if rng.random() < 0.97 else 1 - t for t in truth]


def gen_confound_dgp(n: int, seed: int) -> pl.DataFrame:
    """`U` drives both exposure (`A`) and outcome; the base rule's true causal effect is exactly
    zero (100% confounded, by construction). `B` is a near-exact proxy for `U`.
    """
    rng = random.Random(seed)
    u = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    a = [1 if rng.random() < (0.75 if u[i] else 0.25) else 0 for i in range(n)]
    b = _proxy(rng, u)
    y = [1000.0 + 220.0 * u[i] + rng.gauss(0.0, 60.0) for i in range(n)]
    return pl.DataFrame({"A": a, "B": b, "y": y})


def gen_interaction_dgp(n: int, seed: int, modifier_strength: float = 260.0) -> pl.DataFrame:
    """`D` is a genuine effect modifier: `A`'s own effect on `y` differs by `D`'s level, but `D`
    has zero confounding role (assignment of `A` is independent of `D`) and zero main effect.
    """
    rng = random.Random(seed)
    d = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    a = [1 if rng.random() < 0.5 else 0 for _ in range(n)]  # independent of D
    y = [
        1000.0 + 50.0 * a[i] + modifier_strength * a[i] * d[i] + rng.gauss(0.0, 60.0)
        for i in range(n)
    ]
    return pl.DataFrame({"A": a, "D": d, "y": y})


# =====================================================================================
# 1. A genuine confound is correctly capped, and typically labeled confound_like when
#    concordance/prevalence sit in the regime the design document's own §14.2 identifies.
# =====================================================================================


@pytest.mark.parametrize("seed", list(range(10)))
def test_confound_dgp_capped_and_usually_confound_like(seed: int) -> None:
    frame = gen_confound_dgp(1600, seed=100_000 + seed)
    atom_masks = _atom_masks(frame, ("A", "B"))
    result = classify_composition_safety(
        frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
    )
    # SAFETY property (also re-confirmed here, harmlessly): always capped. This assertion is not
    # what makes this test "diagnostic" -- test_g16_safety.py owns the safety-critical framing;
    # this repeats it only as a sanity precondition for the diagnostic assertion that follows.
    assert result.satisfied is False
    # DIAGNOSTIC-only assertion: atom B (the near-exact confounder proxy) is the one under test.
    b_atom = next(a for a in result.atom_results if a.feature == "B")
    assert b_atom.classification in (
        CompositionAtomClassification.CONFOUND_LIKE,
        CompositionAtomClassification.INDETERMINATE,
    )


def test_confound_dgp_mostly_confound_like_at_high_concordance_unskewed_prevalence() -> None:
    """Reproduces, at reduced scale, the regime §14.2/§15.3 of the design document identifies as
    where `confound_like` actually fires (u_prior=0.5, concordance >= 0.90): not a universal
    detection claim (§15.3 explicitly disclaims that), only that this specific, already-audited
    regime behaves as documented. A failure here is a diagnostic regression worth investigating,
    never a safety failure -- see this file's own module docstring.
    """
    confound_like_count = 0
    trials = 30
    for trial in range(trials):
        frame = gen_confound_dgp(1600, seed=200_000 + trial)
        atom_masks = _atom_masks(frame, ("A", "B"))
        result = classify_composition_safety(
            frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
        )
        b_atom = next(a for a in result.atom_results if a.feature == "B")
        if b_atom.classification is CompositionAtomClassification.CONFOUND_LIKE:
            confound_like_count += 1
    # Diagnostic expectation only, generously bounded: the design document's own ladder shows
    # 93-100/100 at concordance 0.90-0.99, u_prior=0.5. A materially lower rate here would be
    # worth investigating as a diagnostic regression, but would never fail a safety test.
    assert confound_like_count >= trials * 0.5


# =====================================================================================
# 2. A genuine effect modifier is capped, but NEVER labeled confound_like -- the one true
#    "new failure mode" a two-state design could in principle introduce (§15.3), checked here.
# =====================================================================================


@pytest.mark.parametrize("modifier_strength", [80.0, 150.0, 260.0, 400.0])
def test_genuine_effect_modifier_never_labeled_confound_like(modifier_strength: float) -> None:
    misclassified = 0
    trials = 15
    for trial in range(trials):
        frame = gen_interaction_dgp(1600, seed=300_000 + trial, modifier_strength=modifier_strength)
        atom_masks = _atom_masks(frame, ("A", "D"))
        result = classify_composition_safety(
            frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
        )
        d_atom = next(a for a in result.atom_results if a.feature == "D")
        if d_atom.classification is CompositionAtomClassification.CONFOUND_LIKE:
            misclassified += 1
        # Landing indeterminate is the correct, EXPECTED v1 outcome (ADR-077/078 check 5), not a
        # classifier false negative -- asserted here as documentation of intent, not a failure
        # condition either way (this loop only tracks the misclassification count above).
    assert misclassified == 0, (
        f"{misclassified}/{trials} genuine effect-modifier trials misclassified confound_like "
        f"at modifier_strength={modifier_strength} -- a new, undisclosed failure mode ADR-076 "
        "check 3 specifically required ruling out."
    )


# =====================================================================================
# 3. Proxy-confounding ladder (reduced scale, matching ADR-075's mandatory deliverable in
#    spirit): as concordance degrades, confound_like -> indeterminate, never anything unsafe.
# =====================================================================================


def gen_confound_dgp_at_concordance(n: int, concordance: float, seed: int) -> pl.DataFrame:
    rng = random.Random(seed)
    u = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    a = [1 if rng.random() < (0.75 if u[i] else 0.25) else 0 for i in range(n)]
    b = [u[i] if rng.random() < concordance else 1 - u[i] for i in range(n)]
    y = [1000.0 + 220.0 * u[i] + rng.gauss(0.0, 60.0) for i in range(n)]
    return pl.DataFrame({"A": a, "B": b, "y": y})


@pytest.mark.parametrize("concordance", [0.50, 0.65, 0.80, 0.90, 0.99])
def test_proxy_confounding_ladder_degrades_only_toward_indeterminate(concordance: float) -> None:
    """The mandatory `ADR-075` safety property, reduced to a fast regression-suite scale: as
    concordance degrades, the only reachable classifications are confound_like and
    indeterminate -- structurally guaranteed by `test_g16_structural.py`, reconfirmed here on a
    real sweep. This test cannot fail on classification *choice* between the two -- only on a
    classification outside the two-member set, which would already be a structural-test failure.
    """
    trials = 8
    classifications: set[CompositionAtomClassification] = set()
    for trial in range(trials):
        seed = 400_000 + int(concordance * 100) + trial
        frame = gen_confound_dgp_at_concordance(1600, concordance, seed=seed)
        atom_masks = _atom_masks(frame, ("A", "B"))
        result = classify_composition_safety(
            frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
        )
        b_atom = next(a for a in result.atom_results if a.feature == "B")
        classifications.add(b_atom.classification)
        assert result.satisfied is False  # always capped, at every concordance point
    assert classifications <= {
        CompositionAtomClassification.CONFOUND_LIKE,
        CompositionAtomClassification.INDETERMINATE,
    }
