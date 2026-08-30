"""`G16_CANDIDATE_COMPOSITION_SAFETY` (`TASK-081`, implementing `TASK-080`'s design as closed by
`ADR-078`).

This module computes the result-computation half of `G16` only. Wiring into the gate ladder
(`GateId`/`GateSpec`, `evidence_ceiling`) lives in `contract.py`; producing the actual
`GateResult` for a candidate from this module's output lives in `apply.py`. See
`docs/analytics/task-080-candidate-composition-safety-design.md` §8.1/§8.1a (mechanism) and
§15.3 (the current, authoritative two-state specification this module implements — not the
original three-outcome §8/§9/§10 content those sections' own markers say is superseded).

**The two-state design, restated precisely (`ADR-077`/`ADR-078`):** for a promoted candidate
`R = (C1, ..., Ck)`:

- `k == 1`: no check applies (nothing to leave one atom out of). The candidate is unaffected.
- `k >= 2`: for **every** atom `i` in `1..k` — never "each atom beyond the first"; see `ADR-075`
  correction 2 for why that phrasing is an unsafe, order-dependent paraphrase this module must
  never reproduce — run the leave-one-out check: `base_i` = the candidate's other `k - 1` atoms,
  stratified by atom `i` alone, reusing the caller-supplied `stratified_adjustment` callable
  (the real, unmodified `policy_analytics.validation.apply._stratified_adjustment` in
  production) and the existing, unmodified `max_adjusted_attenuation`/
  `min_confounder_stratum_coverage` thresholds. An atom is `confound_like` when the
  stratification clears the coverage floor, the adjusted effect keeps `base_i`'s own raw sign,
  and attenuation exceeds the ceiling — unchanged from every prior design revision, the one
  branch no review round ever found a defect in. Every other atom is `indeterminate`.
  `interaction_like` was **removed**, not merely deprioritized: `CompositionAtomClassification`
  has exactly two members, so no atom classification this module can produce, represent, or
  return is anything but one of those two — this is the structural (type-level) half of the
  "no reachable third state" property `TASK-081` requires; see
  `tests/analytics/test_g16_structural.py` for the exhaustive test.
- **Rule-level outcome:** if any atom is `confound_like`, the candidate's reason is
  `confound_like` (naming the atom(s)). Otherwise — every atom `indeterminate` — the candidate's
  reason is `composition_risk_indeterminate`. **Both reasons carry an identical cap.** The
  `satisfied` field on `CompositionSafetyResult` is `False` in both cases and is never set to
  `True` by any code path in this module when `k >= 2` — there is no branch here that computes
  "every atom cleared some positive-evidence bar, so leave this candidate uncapped": per
  `ADR-077`/`ADR-078`'s non-identifiability finding, no such branch exists in this design at all.
  The reason code is diagnostic only; it never determines cap severity (`TASK-081`'s own stated
  "one executable invariant").

No randomness or resampling appears anywhere in this module — every quantity is a closed-form
function of the frame and the already-frozen candidate conditions, computed once via the
injected `stratified_adjustment` callable (dependency-injected specifically so this module does
not import `policy_analytics.validation.apply` and cannot create an import cycle with it).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import reduce
from operator import and_
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import polars as pl

    from policy_analytics.outcomes import OutcomeDefinition
    from policy_analytics.validation.contract import ValidationThresholds

#: `(frame, mask, outcome, columns) -> (adjusted_diff, coverage)`, the exact signature of
#: `policy_analytics.validation.apply._stratified_adjustment`. Passed in by the caller rather
#: than imported directly so this module reuses that function's real object (never a
#: reimplementation) without importing `apply.py`, which itself imports this module.
StratifiedAdjustmentFn = Callable[
    ["pl.DataFrame", "pl.Series", "OutcomeDefinition", "tuple[str, ...]"], "tuple[float, float]"
]


class CompositionAtomClassification(StrEnum):
    """The only two reachable classifications for one leave-one-out atom check.

    `interaction_like` was removed from this design (`ADR-077`, confirmed `ADR-078`), not merely
    made harder to reach. This enum has exactly two members; no third member exists to add, and
    no function in this module constructs a value of this type other than by referencing one of
    these two members — see `classify_atom`, whose only two return statements name
    `CONFOUND_LIKE` and `INDETERMINATE` and nothing else.
    """

    CONFOUND_LIKE = "confound_like"
    INDETERMINATE = "indeterminate"


class CompositionSafetyReason(StrEnum):
    """Candidate-level `G16` reason code.

    `NOT_APPLICABLE_SINGLE_ATOM` is the only reason under which the gate is satisfied
    (`k == 1`, vacuous). `CONFOUND_LIKE` and `COMPOSITION_RISK_INDETERMINATE` are the two `k >= 2`
    reasons and carry an **identical** evidence cap — this string distinguishes them for
    diagnostics only. Distinct, by construction, from any reason `T05`/`G06`'s own
    coverage-ceiling failure ever produces: `G06`'s gate detail text is generated independently
    in `apply.py` and never constructed from, or compared against, this enum.
    """

    NOT_APPLICABLE_SINGLE_ATOM = "not_applicable_single_atom"
    CONFOUND_LIKE = "confound_like"
    COMPOSITION_RISK_INDETERMINATE = "composition_risk_indeterminate"


@dataclass(frozen=True, slots=True)
class AtomCompositionResult:
    """One atom `Ci`'s leave-one-out classification within a compound candidate.

    `atom_index` is 1-based, matching §8.1's own `i in 1..k` convention.
    """

    atom_index: int
    feature: str
    classification: CompositionAtomClassification
    coverage: float
    raw_base_effect: float
    adjusted_effect: float
    attenuation: float
    detail: str


@dataclass(frozen=True, slots=True)
class CompositionSafetyResult:
    """Candidate-level `G16` outcome.

    `satisfied` is this module's own pass/fail signal for the gate: `True` only when
    `applicable` is `False` (`k == 1`); `False` for every `k >= 2` candidate this module
    examines, regardless of `reason` — the one executable invariant `TASK-081` names.
    """

    applicable: bool
    atom_results: tuple[AtomCompositionResult, ...]
    satisfied: bool
    reason: CompositionSafetyReason
    detail: str


def classify_atom(
    frame: "pl.DataFrame",
    atom_masks: "tuple[tuple[str, pl.Series], ...]",
    atom_position: int,
    outcome: "OutcomeDefinition",
    stratified_adjustment: StratifiedAdjustmentFn,
    thresholds: "ValidationThresholds",
) -> AtomCompositionResult:
    """Classify one atom (`atom_masks[atom_position]`) via the leave-one-out check.

    `base_i` is the AND of every *other* atom's own mask (full enumeration — every atom is
    reachable as `atom_position`, and every other atom contributes to `base_i`; there is no
    "beyond the first" exclusion anywhere in this function).
    """
    feature_i, mask_i = atom_masks[atom_position]
    other_masks = [mask for position, (_, mask) in enumerate(atom_masks) if position != atom_position]
    base_i_mask = reduce(and_, other_masks)

    raw_base_diff, _ = stratified_adjustment(frame, base_i_mask, outcome, ())
    temp_column = f"__g16_atom_{atom_position}__"
    working = frame.with_columns(mask_i.alias(temp_column))
    adjusted_diff, coverage = stratified_adjustment(working, base_i_mask, outcome, (temp_column,))

    raw_base = raw_base_diff * outcome.harm_multiplier
    adjusted = adjusted_diff * outcome.harm_multiplier
    attenuation = 1.0 - (adjusted / raw_base if raw_base else 1.0)
    coverage_ok = coverage >= thresholds.min_confounder_stratum_coverage
    sign_ok = (adjusted > 0) == (raw_base > 0) if raw_base else True
    confound_positive_evidence = (
        coverage_ok and sign_ok and attenuation > thresholds.max_adjusted_attenuation
    )

    k = len(atom_masks)
    if confound_positive_evidence:
        classification = CompositionAtomClassification.CONFOUND_LIKE
        verdict_text = (
            f"positive evidence of confounding (attenuation {attenuation:.2f} > ceiling "
            f"{thresholds.max_adjusted_attenuation:.2f}, coverage {coverage:.2f} >= floor "
            f"{thresholds.min_confounder_stratum_coverage:.2f}, sign preserved)"
        )
    else:
        classification = CompositionAtomClassification.INDETERMINATE
        verdict_text = (
            f"no positive evidence of confounding cleared (attenuation {attenuation:.2f}, "
            f"coverage {coverage:.2f} vs floor {thresholds.min_confounder_stratum_coverage:.2f}"
            f"{', sign flipped' if not sign_ok else ''}); G16 v1 makes no positive interaction "
            "claim (ADR-077/ADR-078: not identifiable from the information this check has "
            "access to)"
        )

    detail = (
        f"G16 leave-one-out atom {atom_position + 1}/{k} ({feature_i!r}): base rule's raw "
        f"effect {raw_base:.2f} -> {adjusted:.2f} once stratified by this atom alone -- "
        f"{verdict_text}."
    )
    return AtomCompositionResult(
        atom_index=atom_position + 1,
        feature=feature_i,
        classification=classification,
        coverage=coverage,
        raw_base_effect=raw_base,
        adjusted_effect=adjusted,
        attenuation=attenuation,
        detail=detail,
    )


def classify_composition_safety(
    frame: "pl.DataFrame",
    atom_masks: "tuple[tuple[str, pl.Series], ...]",
    outcome: "OutcomeDefinition",
    stratified_adjustment: StratifiedAdjustmentFn,
    thresholds: "ValidationThresholds",
) -> CompositionSafetyResult:
    """`G16`'s candidate-level result.

    `atom_masks` is `((feature_1, mask_1), ..., (feature_k, mask_k))` — one boolean mask per
    condition atom of the candidate, in the candidate's own condition order (order carries no
    semantic weight here: every atom's own `base_i` is the AND of every *other* atom, so
    permuting `atom_masks` permutes only which `AtomCompositionResult` gets which `atom_index`,
    never the rule-level `reason`/`satisfied` outcome — see
    `tests/analytics/test_g16_structural.py::test_permutation_invariance`).
    """
    k = len(atom_masks)
    if k <= 1:
        return CompositionSafetyResult(
            applicable=False,
            atom_results=(),
            satisfied=True,
            reason=CompositionSafetyReason.NOT_APPLICABLE_SINGLE_ATOM,
            detail=f"k={k}: G16 does not apply (nothing to leave one atom out of).",
        )

    atom_results = tuple(
        classify_atom(frame, atom_masks, position, outcome, stratified_adjustment, thresholds)
        for position in range(k)
    )

    confound_like_atoms = tuple(
        atom
        for atom in atom_results
        if atom.classification is CompositionAtomClassification.CONFOUND_LIKE
    )
    joined_atom_detail = " | ".join(atom.detail for atom in atom_results)
    if confound_like_atoms:
        names = ", ".join(f"{atom.feature!r} (atom {atom.atom_index})" for atom in confound_like_atoms)
        reason = CompositionSafetyReason.CONFOUND_LIKE
        detail = (
            f"G16: {len(confound_like_atoms)}/{k} atom(s) classify confound_like ({names}); "
            f"evidence capped. {joined_atom_detail}"
        )
    else:
        reason = CompositionSafetyReason.COMPOSITION_RISK_INDETERMINATE
        detail = (
            f"G16: no atom of {k} classifies confound_like; composition_risk_indeterminate -- "
            "no positive evidence of confounding found, and this two-state design (ADR-077/"
            "ADR-078) never grants an uncapped interaction_like verdict. Evidence capped. "
            f"{joined_atom_detail}"
        )

    # `satisfied` is unconditionally False here -- the one executable invariant this gate exists
    # to provide (TASK-081): every k >= 2 candidate is capped identically regardless of `reason`.
    return CompositionSafetyResult(
        applicable=True,
        atom_results=atom_results,
        satisfied=False,
        reason=reason,
        detail=detail,
    )
