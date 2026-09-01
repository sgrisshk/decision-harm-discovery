"""Economic-impact result contract (`TASK-023`), consumed by Finding persistence (`TASK-024`).

**`TASK-086` (implementing `TASK-085`'s design, `ADR-087`/`ADR-089`).** This module used to name
every quantity here "impact" (`EconomicImpactResult.historical_impact`) even though `apply.py`'s
own population is `full_mask` — the candidate's own condition, nothing narrower, nothing
attribution-tested. `TASK-084`/`TASK-085` established that this is `O1` ("observed candidate
exposure"), not `O2` ("attributable harmful impact"): a scope claim ("this much of the business is
touched by this rule"), never a mechanism claim. This module now names that distinction in its own
types, per `TASK-085` §5.2/§7's three-tier design:

- **Tier 1 — `CandidateExposureResult(tier=1)`.** Unchanged computation from `v1.0.0`: population
  `E` (the combined development+validation+future_holdout window), raw `harm_per_booking`. Renamed
  fields only; no numeric change. Available from evidence level `descriptive_observation` (1+).
- **Tier 2 — `CandidateExposureResult(tier=2)`.** Population `E_dev = E ∩ {development split}` —
  **strictly narrower than tier 1's `E`**, matching exactly the population `G06`'s `adjusted_effect`
  was actually fit on. Effect term is `G06`'s own already-computed `adjusted_effect` — reused, never
  recomputed here (this module contains no estimation code, exactly as before). **Never aggregated
  over the combined-window `exposed_total`** — that was `TASK-085`'s own `ADR-089` Check 3 defect,
  fixed normatively in the design and implemented here as `E_dev`'s own record count. Available from
  evidence level `adjusted_observational_association` (3+).
- **Tier 3 — `AttributableImpactResult` (`O2`).** A structurally distinct type, never merged with
  `CandidateExposureResult` (§0's own "never merged into one name or one number" rule).
  Constructible **only** via `build_attributable_impact_result`, which returns `None` unless the
  real `G13`/`G14` gate results show genuine identification — never a fallback keyed to evidence
  level or any other proxy. `apply.py` hardcodes both gates to `FAIL` for every real candidate
  today (observational data only), so this is, in practice, `TASK-085` §5.2's disclosed
  "always-empty slot" — see `tests/analytics/test_tier3_structural.py`.

**Versioning (`ECONOMIC_IMPACT_CONTRACT_VERSION`, following `CONTRACT_VERSION`'s own
`ADR-015`/`ADR-064` precedent).** `v1.x` artifacts (`impact_contract_version`, `historical_impact`)
are not rewritten and not re-graded: `load_candidate_exposure_result` parses them under their own
recorded version, interpreting them as exactly what `TASK-085` §7 establishes they always were —
tier 1's unchanged computation over the combined window — never as a newly invented tier. `v2.0.0`
is the first version this module's own field names are `O1`-honest.

Nothing here is new methodology: every quantity is already computed by gate `G15` (economic
materiality) or gate `G06` (confounding adjustment) in `apply.py`; this module only gives those
computations a canonical, versioned, testable output shape. It must not be extended to narrow
exposure to a ground-truth-matched subpopulation — that remains out of scope, per the original
`TASK-023` docstring this module carries forward, and per `TASK-085` §4's own checked negative
finding that no candidate-internal computation can identify `O2`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from policy_analytics.outcomes import OutcomeDefinition
from policy_analytics.validation.contract import GateId, GateResult
from policy_analytics.validation.report import EffectEstimate

#: Current contract version. `v2.0.0` (`TASK-086`/`ADR-089`) renames every `O1`-family field to
#: honest exposure language and introduces the tier/population_scope/quantity_name triple;
#: `v1.0.0`/`v1.1.0` are the pre-rename shape, still parseable via `load_candidate_exposure_result`.
ECONOMIC_IMPACT_CONTRACT_VERSION = "2.0.0"

#: The last pre-rename version. Any persisted payload carrying `impact_contract_version` instead of
#: `exposure_contract_version` predates `TASK-086` and is parsed under this label, unchanged.
LEGACY_ECONOMIC_IMPACT_CONTRACT_VERSION = "1.0.0"

#: Tier 1's own vocabulary, fixed by `TASK-085` §5.2 — never invented per-call.
TIER_1_POPULATION_SCOPE = "E"
TIER_1_QUANTITY_NAME = "candidate_exposure"

#: Tier 2's own vocabulary, fixed by `TASK-085` §5.2's 2026-08-31 correction — never invented
#: per-call, and never equal to tier 1's (a caller that passes tier-1 values under a tier-2 label,
#: or vice versa, is rejected by `CandidateExposureResult.__post_init__`).
TIER_2_POPULATION_SCOPE = "E_dev"
TIER_2_QUANTITY_NAME = "adjustment_consistent_candidate_exposure_dev_scope"


@dataclass(frozen=True, slots=True)
class CandidateExposureResult:
    """`O1` — observed candidate exposure. Tiers 1-2 of `TASK-085` §5.2's ladder only; `tier=3`
    is not a valid value here — `O2` (attributable harmful impact) is `AttributableImpactResult`,
    a structurally distinct type (§0's "never merged" rule), never this one.

    **Sign convention.** Every value here is harm-signed: positive means realized harm, matching
    `OutcomeDefinition.harm_multiplier` and the ground-truth `economic_impact_sign_convention`
    verified in `HANDOFF-030`. A candidate whose bookings are *more* profitable than the
    comparison group would show a negative `candidate_exposure` — this contract does not clip
    that to zero or hide it; a negative exposure figure is a legitimate, if unusual, output.

    **`affected_records` is scoped to this result's own `population_scope`** — tier 1's is the
    full observed window (`E`, development + validation + future_holdout combined); tier 2's is
    `E_dev` (development split only), strictly narrower. These are two different, both-correct
    numbers answering different questions for different tiers; they are not interchangeable and
    must never be presented as the same population.

    **Claim permitted.** Per `TASK-085` §7: "value at stake in these records," never "impact,"
    never "savings," at every tier this type represents — regardless of the candidate's own
    evidence level. Causal/savings language only becomes available at tier 3 (`AttributableImpactResult`).

    **Annualization is not implemented.** `annualized_candidate_exposure` is always `None` and
    `annualization_justified` is always `False` — unchanged scope gap from `v1.0.0`, tracked as
    future work, not part of this rename.
    """

    exposure_contract_version: str
    tier: int
    population_scope: str
    quantity_name: str
    outcome_name: str
    outcome_unit: str
    affected_records: int
    per_record_effect: EffectEstimate
    candidate_exposure: EffectEstimate
    annualization_justified: bool
    materiality_pass: bool
    annualized_candidate_exposure: EffectEstimate | None = None

    def __post_init__(self) -> None:
        if self.affected_records < 0:
            raise ValueError("affected_records cannot be negative")
        if self.tier not in (1, 2):
            raise ValueError(
                f"CandidateExposureResult.tier must be 1 or 2, got {self.tier!r}; "
                "tier 3 (O2, attributable harmful impact) is AttributableImpactResult, a "
                "structurally distinct type, never this one"
            )
        if self.tier == 1:
            if self.population_scope != TIER_1_POPULATION_SCOPE:
                raise ValueError(
                    f"tier 1 population_scope must be {TIER_1_POPULATION_SCOPE!r}, "
                    f"got {self.population_scope!r}"
                )
            if self.quantity_name != TIER_1_QUANTITY_NAME:
                raise ValueError(
                    f"tier 1 quantity_name must be {TIER_1_QUANTITY_NAME!r}, "
                    f"got {self.quantity_name!r}"
                )
        else:
            if self.population_scope != TIER_2_POPULATION_SCOPE:
                raise ValueError(
                    f"tier 2 population_scope must be {TIER_2_POPULATION_SCOPE!r}, "
                    f"got {self.population_scope!r}"
                )
            if self.quantity_name != TIER_2_QUANTITY_NAME:
                raise ValueError(
                    f"tier 2 quantity_name must be {TIER_2_QUANTITY_NAME!r}, "
                    f"got {self.quantity_name!r}"
                )
        if (self.annualized_candidate_exposure is not None) != self.annualization_justified:
            raise ValueError(
                "annualized_candidate_exposure must be present exactly when "
                "annualization_justified is true"
            )
        if self.annualization_justified:
            raise ValueError(
                "annualization is not implemented; annualization_justified must be false"
            )

    @property
    def impact_contract_version(self) -> str:
        """Deprecated pre-`TASK-086` alias for `exposure_contract_version`.

        Kept only so already-frozen `TASK-084` forensic review scripts (never edited
        retroactively, per this task's own scope boundary) keep reading a real attribute.
        """
        return self.exposure_contract_version

    @property
    def historical_impact(self) -> EffectEstimate:
        """Deprecated pre-`TASK-086` alias for `candidate_exposure`. See `impact_contract_version`."""
        return self.candidate_exposure

    @property
    def annualized_impact(self) -> EffectEstimate | None:
        """Deprecated pre-`TASK-086` alias for `annualized_candidate_exposure`."""
        return self.annualized_candidate_exposure

    def to_dict(self) -> dict[str, Any]:
        """Field-for-field match to `EconomicExposurePersistence`'s expected JSON shape."""
        return {
            "exposure_contract_version": self.exposure_contract_version,
            "tier": self.tier,
            "population_scope": self.population_scope,
            "quantity_name": self.quantity_name,
            "outcome_name": self.outcome_name,
            "outcome_unit": self.outcome_unit,
            "affected_records": self.affected_records,
            "per_record_effect": _estimate_to_dict(self.per_record_effect),
            "candidate_exposure": _estimate_to_dict(self.candidate_exposure),
            "annualized_candidate_exposure": _estimate_to_dict(self.annualized_candidate_exposure),
            "annualization_justified": self.annualization_justified,
            "materiality_pass": self.materiality_pass,
        }


@dataclass(frozen=True, slots=True)
class AttributableImpactResult:
    """`O2` — attributable harmful impact (`TASK-085` §5.2 tier 3, §7's `O2` estimand).

    Target population `A`: the mechanism's own affected population, as delimited by a genuine
    identification design (`G13`) or randomization (`G14`) — never a subset of `E` selected by any
    observational computation. Structurally distinct from `CandidateExposureResult` (`O1`) by
    design: the two are never merged into one type, matching §0's "never merged into one name or
    one number" rule, so no consumer can mistake an `O1` figure for an `O2` figure by construction.

    Constructible **only** via `build_attributable_impact_result`, and only when the caller both
    (a) supplies gate results showing `G13` or `G14` genuinely satisfied, and (b) supplies a real
    `MechanismPopulationEstimate` for population `A` — which nothing in this project's current
    codebase can construct (building that estimator is explicitly out of `TASK-086`'s scope). Never
    activated by evidence level, tier-1/2 figures, or any other proxy.
    """

    exposure_contract_version: str
    outcome_name: str
    outcome_unit: str
    affected_records: int
    per_record_effect: EffectEstimate
    attributable_impact: EffectEstimate
    identification_gate: GateId
    materiality_pass: bool

    def __post_init__(self) -> None:
        if self.affected_records < 0:
            raise ValueError("affected_records cannot be negative")
        if self.identification_gate not in (GateId.IDENTIFICATION, GateId.RANDOMIZATION):
            raise ValueError(
                "identification_gate must be G13_IDENTIFICATION_DESIGN or "
                "G14_RANDOMIZATION_INTEGRITY"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exposure_contract_version": self.exposure_contract_version,
            "tier": 3,
            "population_scope": "A",
            "quantity_name": "attributable_harmful_impact",
            "outcome_name": self.outcome_name,
            "outcome_unit": self.outcome_unit,
            "affected_records": self.affected_records,
            "per_record_effect": _estimate_to_dict(self.per_record_effect),
            "attributable_impact": _estimate_to_dict(self.attributable_impact),
            "identification_gate": self.identification_gate.value,
            "materiality_pass": self.materiality_pass,
        }


@dataclass(frozen=True, slots=True)
class MechanismPopulationEstimate:
    """The design-identified population `A` and its effect estimate — `TASK-085` §7's `O2`
    estimand's own inputs. Produced only by a genuine `G13`/`G14` identification-design pipeline
    using "the design-appropriate effect estimator" (`TASK-085` §7: "no new estimator is proposed
    here"). No constructor for this type exists anywhere in this project's current codebase, by
    design — building one is a distinct, later task's scope, not `TASK-086`'s. Its only purpose
    here is to let `build_attributable_impact_result`'s *gating logic* be unit-tested directly
    (a hand-built instance, in a test file) without ever wiring a real call site to it from
    `apply.py`, where no such instance can be produced today.
    """

    affected_records: int
    per_record_effect: EffectEstimate
    attributable_impact: EffectEstimate


def tier3_identification_satisfied(gate_results: Any) -> GateId | None:
    """Which of `G13`/`G14`, if either, is genuinely satisfied — the *only* function that decides
    whether tier 3 exists for a candidate. Inspects the real `GateResult.satisfied` values
    directly; never reads `evidence_level` or any other derived/proxy signal. Returns `None`
    whenever neither gate is satisfied — which is every real candidate in this project's history,
    since `apply.py` hardcodes both to `FAIL` (observational data only, no prospective
    randomization).
    """
    g13 = next((g for g in gate_results if g.gate_id is GateId.IDENTIFICATION), None)
    g14 = next((g for g in gate_results if g.gate_id is GateId.RANDOMIZATION), None)
    if g13 is not None and g13.satisfied:
        return GateId.IDENTIFICATION
    if g14 is not None and g14.satisfied:
        return GateId.RANDOMIZATION
    return None


def build_attributable_impact_result(
    *,
    gate_results: tuple[GateResult, ...],
    outcome: OutcomeDefinition,
    mechanism_population: MechanismPopulationEstimate,
    materiality_pass: bool,
) -> AttributableImpactResult | None:
    """Tier 3 / `O2`. Returns `None` unless `tier3_identification_satisfied` finds `G13` or `G14`
    genuinely satisfied in `gate_results` — no fallback bridging evidence level (or anything else)
    to attributable-impact language. This function performs no estimation of its own: it packages
    an already-produced `MechanismPopulationEstimate` under the versioned contract, exactly the
    same "no estimation code" discipline `CandidateExposureResult`'s tiers 1-2 already follow.
    """
    gate = tier3_identification_satisfied(gate_results)
    if gate is None:
        return None
    return AttributableImpactResult(
        exposure_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
        outcome_name=outcome.outcome_id,
        outcome_unit=outcome.unit,
        affected_records=mechanism_population.affected_records,
        per_record_effect=mechanism_population.per_record_effect,
        attributable_impact=mechanism_population.attributable_impact,
        identification_gate=gate,
        materiality_pass=materiality_pass,
    )


def _estimate_to_dict(estimate: EffectEstimate | None) -> dict[str, Any] | None:
    if estimate is None:
        return None
    return {
        "value": estimate.value,
        "ci_low": estimate.ci_low,
        "ci_high": estimate.ci_high,
        "confidence_level": estimate.confidence_level,
        "method": estimate.method,
        "unit": estimate.unit,
    }


def _estimate_from_dict(data: dict[str, Any] | None) -> EffectEstimate | None:
    if data is None:
        return None
    return EffectEstimate(
        data["value"],
        data["ci_low"],
        data["ci_high"],
        data["confidence_level"],
        data["method"],
        data["unit"],
    )


def build_candidate_exposure_result_tier1(
    *,
    outcome: OutcomeDefinition,
    affected_records: int,
    per_record_value: float,
    per_record_ci_low: float,
    per_record_ci_high: float,
    confidence_level: float,
    historical_value: float,
    historical_ci_low: float,
    historical_ci_high: float,
    materiality_pass: bool,
) -> CandidateExposureResult:
    """Tier 1 — `O1` over `E`, the combined development+validation+future_holdout window.

    Unchanged computation from `v1.0.0` (`TASK-023`); only the field/type names and the tier/
    population_scope/quantity_name labels are new (`TASK-086`). Both intervals are widened, if
    needed, to contain their own point estimate — a bootstrap percentile interval is not
    guaranteed by construction to bracket the point estimate computed on unresampled data (see
    `apply.py`'s identical treatment of `dev_effect`).
    """
    per_low = min(per_record_ci_low, per_record_ci_high, per_record_value)
    per_high = max(per_record_ci_low, per_record_ci_high, per_record_value)
    hist_low = min(historical_ci_low, historical_ci_high, historical_value)
    hist_high = max(historical_ci_low, historical_ci_high, historical_value)

    return CandidateExposureResult(
        exposure_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
        tier=1,
        population_scope=TIER_1_POPULATION_SCOPE,
        quantity_name=TIER_1_QUANTITY_NAME,
        outcome_name=outcome.outcome_id,
        outcome_unit=outcome.unit,
        affected_records=affected_records,
        per_record_effect=EffectEstimate(
            per_record_value,
            per_low,
            per_high,
            confidence_level,
            "cluster_bootstrap_customer_id_combined_window",
            outcome.unit,
        ),
        candidate_exposure=EffectEstimate(
            historical_value,
            hist_low,
            hist_high,
            confidence_level,
            "cluster_bootstrap_customer_id_combined_window",
            outcome.unit,
        ),
        annualization_justified=False,
        materiality_pass=materiality_pass,
        annualized_candidate_exposure=None,
    )


def build_candidate_exposure_result_tier2(
    *,
    outcome: OutcomeDefinition,
    dev_exposed_records: int,
    adjusted_effect: EffectEstimate,
    materiality_pass: bool,
) -> CandidateExposureResult:
    """Tier 2 — `O1` over `E_dev = E ∩ {development split}`, `TASK-085` §5.2/§7 as corrected
    2026-08-31 (`ADR-089` Check 3).

    Reuses `G06`'s own already-computed `adjusted_effect` (`_stratified_adjustment` in `apply.py`)
    without recomputing anything — this function contains no estimation code, only aggregation and
    packaging. Aggregates over `dev_exposed_records` = `|E_dev|`, the development-split-only
    exposed count **— never `E`'s combined-window `exposed_total`.** That transport was the exact
    defect `TASK-085`'s independent `CODE_REVIEWER` review found (§5.2's inline correction): a
    development-only-fit effect silently multiplied by a wider population it was never estimated
    on. The caller (`apply.py`) must pass `dev_exposed_records` from the *development* split's own
    `SplitStats.n_exposed` — not `combined_stats.n_exposed` — for this fix to hold; see
    `tests/analytics/test_economic_impact.py::test_tier2_uses_e_dev_not_combined_exposed_total`
    for the regression proof.
    """
    value = adjusted_effect.value * dev_exposed_records
    ci_a = adjusted_effect.ci_low * dev_exposed_records
    ci_b = adjusted_effect.ci_high * dev_exposed_records
    low = min(ci_a, ci_b, value)
    high = max(ci_a, ci_b, value)

    return CandidateExposureResult(
        exposure_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
        tier=2,
        population_scope=TIER_2_POPULATION_SCOPE,
        quantity_name=TIER_2_QUANTITY_NAME,
        outcome_name=outcome.outcome_id,
        outcome_unit=outcome.unit,
        affected_records=dev_exposed_records,
        per_record_effect=EffectEstimate(
            adjusted_effect.value,
            adjusted_effect.ci_low,
            adjusted_effect.ci_high,
            adjusted_effect.confidence_level,
            adjusted_effect.method,
            outcome.unit,
        ),
        candidate_exposure=EffectEstimate(
            value,
            low,
            high,
            adjusted_effect.confidence_level,
            "stratified_generalized_adjustment_scaled_by_development_split_exposure",
            outcome.unit,
        ),
        annualization_justified=False,
        materiality_pass=materiality_pass,
        annualized_candidate_exposure=None,
    )


def load_candidate_exposure_result(data: dict[str, Any]) -> CandidateExposureResult:
    """Parse a persisted economic-exposure payload under **its own recorded contract version** —
    never re-graded, never silently reinterpreted (`TASK-086`'s binding migration constraint, per
    `ADR-015`/`ADR-064` precedent).

    A `v2.0.0`+ payload (`exposure_contract_version` present) is parsed with its own recorded
    tier/population_scope exactly as stored. A legacy `v1.x` payload (`impact_contract_version`
    present, `historical_impact` instead of `candidate_exposure`) is parsed as **tier 1**, scope
    `E` — not a new interpretation, but `TASK-085` §7's own stated equivalence: `v1.x`'s sole
    computation always *was* exactly tier 1's unchanged quantity, before this rename gave that
    quantity its own honest name. The legacy payload's own `impact_contract_version` string is
    preserved verbatim in the returned `exposure_contract_version` field, so a reader can always
    tell which contract version actually graded this artifact.
    """
    if "exposure_contract_version" in data:
        return CandidateExposureResult(
            exposure_contract_version=data["exposure_contract_version"],
            tier=data["tier"],
            population_scope=data["population_scope"],
            quantity_name=data["quantity_name"],
            outcome_name=data["outcome_name"],
            outcome_unit=data["outcome_unit"],
            affected_records=data["affected_records"],
            per_record_effect=_estimate_from_dict(data["per_record_effect"]),  # type: ignore[arg-type]
            candidate_exposure=_estimate_from_dict(data["candidate_exposure"]),  # type: ignore[arg-type]
            annualization_justified=data["annualization_justified"],
            materiality_pass=data["materiality_pass"],
            annualized_candidate_exposure=_estimate_from_dict(
                data.get("annualized_candidate_exposure")
            ),
        )
    if "impact_contract_version" in data:
        return CandidateExposureResult(
            exposure_contract_version=data["impact_contract_version"],
            tier=1,
            population_scope=TIER_1_POPULATION_SCOPE,
            quantity_name=TIER_1_QUANTITY_NAME,
            outcome_name=data["outcome_name"],
            outcome_unit=data["outcome_unit"],
            affected_records=data["affected_records"],
            per_record_effect=_estimate_from_dict(data["per_record_effect"]),  # type: ignore[arg-type]
            candidate_exposure=_estimate_from_dict(data["historical_impact"]),  # type: ignore[arg-type]
            annualization_justified=data["annualization_justified"],
            materiality_pass=data["materiality_pass"],
            annualized_candidate_exposure=_estimate_from_dict(data.get("annualized_impact")),
        )
    raise ValueError(
        "economic-exposure payload has neither 'exposure_contract_version' nor "
        "'impact_contract_version'; cannot determine which contract version graded it"
    )


# --- Backward-compatible aliases -------------------------------------------------------------
# Pre-TASK-086 name, kept so already-frozen forensic review scripts tied to closed tasks
# (e.g. `scripts/review_task084_check1_independent_controls.py`,
# `scripts/diagnose_task084_branch4_controls.py` — TASK-069-085 artifacts, never edited
# retroactively per this task's own scope boundary) keep importing and running unchanged.
# New code must use `build_candidate_exposure_result_tier1`/`CandidateExposureResult` directly.
EconomicImpactResult = CandidateExposureResult
build_economic_impact_result = build_candidate_exposure_result_tier1
