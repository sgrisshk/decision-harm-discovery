"""Economic-impact result contract (TASK-023), consumed by Finding persistence (TASK-024).

Resolves `HANDOFF-025`: Architect's `EconomicImpactPersistence`
(`apps/api/app/findings/contracts.py`) is a storage envelope only — this module is the
Statistics-owned computation and versioned semantics behind every field in it. Field names below
are kept in exact 1:1 correspondence with `EconomicImpactPersistence` so TASK-024 can persist this
object without interpreting or recomputing any statistical meaning.

Nothing here is new methodology: every quantity is already computed by gate G15 in `apply.py`
(economic materiality); this module only gives that computation a canonical, versioned, testable
output shape, and fills in the one piece G15 discarded (a per-record CI distinct from the
total-exposure CI). It must not be extended to narrow exposure to a ground-truth-matched
subpopulation — that would be `TASK-029`/`HANDOFF-043` remediation, a design decision pending
ML_DISCOVERY's concurrence, not a persistence-contract change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from policy_analytics.outcomes import OutcomeDefinition
from policy_analytics.validation.report import EffectEstimate

ECONOMIC_IMPACT_CONTRACT_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class EconomicImpactResult:
    """Field-for-field match to `EconomicImpactPersistence` (`apps/api/app/findings/contracts.py`).

    **Sign convention.** Every value here is harm-signed: positive means realized harm, matching
    `OutcomeDefinition.harm_multiplier` and the ground-truth `economic_impact_sign_convention`
    verified in `HANDOFF-030`. A candidate whose bookings are *more* profitable than the
    comparison group would show a negative `historical_impact` — this contract does not clip that
    to zero or hide it; a negative "impact" is a legitimate, if unusual, output.

    **`affected_records` is the full observed window (development + validation + future_holdout
    splits combined), not `ValidationMetadataPersistence.exposed_records` (development only).**
    These are two different, both-correct numbers answering different questions:
    `exposed_records` is "how many rows were available to grade the finding on"; `affected_records`
    here is "how many historical bookings does this pattern actually touch." They will not
    generally be equal, and displaying only one without the other's context is a foreseeable
    source of confusion — see the correction this sends back to Product's
    `docs/product/finding-product-contract.md`, which assumed they were the same population.

    **Interval propagation.** Both `per_record_effect` and `historical_impact` intervals come from
    the same cluster bootstrap (customer_id, `DIAGNOSTIC_BOOTSTRAP_REPS` replicates) over the full
    observed window — a *different* bootstrap run than the one behind
    `ValidationMetadataPersistence.raw_effect`, which is development-split-only at
    `DEV_BOOTSTRAP_REPS` replicates and exists to grade evidence, not to size impact. `
    historical_impact`'s interval is `per_record_effect`'s interval scaled by `affected_records`,
    from the same replicate set, so the two are internally consistent with each other.

    **Materiality.** `materiality_pass` is gate G15's own pass/fail: the impact CI's lower bound is
    positive and clears either `min_material_annual_impact` or `min_material_outcome_share`
    (`ValidationThresholds`, both placeholders pending real customer economics — `OQ-004`). This
    contract does not expose the threshold values themselves, matching Product's own display rule
    (show pass/fail, never the number).

    **Annualization is not implemented in v1.0.0.** `annualized_impact` is always `None` and
    `annualization_justified` is always `False` — TASK-023 v0's economic-impact reporting is
    observed-window-only. Implementing annualization requires the exposure-rate-stability check
    `docs/analytics/validation-contract.md` §8 already specifies but this version does not compute;
    that is a scoped, disclosed gap, not an oversight, tracked as future TASK-023 work, not part of
    this resolution.
    """

    impact_contract_version: str
    outcome_name: str
    outcome_unit: str
    affected_records: int
    per_record_effect: EffectEstimate
    historical_impact: EffectEstimate
    annualization_justified: bool
    materiality_pass: bool
    annualized_impact: EffectEstimate | None = None

    def __post_init__(self) -> None:
        if self.affected_records < 0:
            raise ValueError("affected_records cannot be negative")
        if (self.annualized_impact is not None) != self.annualization_justified:
            raise ValueError(
                "annualized_impact must be present exactly when annualization_justified is true"
            )
        if self.annualization_justified:
            raise ValueError(
                "annualization is not implemented in contract v1.0.0; "
                "annualization_justified must be false"
            )

    def to_dict(self) -> dict[str, Any]:
        """Field-for-field match to `EconomicImpactPersistence`'s expected JSON shape."""
        return {
            "impact_contract_version": self.impact_contract_version,
            "outcome_name": self.outcome_name,
            "outcome_unit": self.outcome_unit,
            "affected_records": self.affected_records,
            "per_record_effect": _estimate_to_dict(self.per_record_effect),
            "historical_impact": _estimate_to_dict(self.historical_impact),
            "annualized_impact": _estimate_to_dict(self.annualized_impact),
            "annualization_justified": self.annualization_justified,
            "materiality_pass": self.materiality_pass,
        }


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


def build_economic_impact_result(
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
) -> EconomicImpactResult:
    """Assemble the versioned result from already-computed gate-G15 quantities.

    Both intervals are widened, if needed, to contain their own point estimate — a bootstrap
    percentile interval is not guaranteed by construction to bracket the point estimate computed
    on unresampled data (see `apply.py`'s identical treatment of `dev_effect`).
    """
    per_low = min(per_record_ci_low, per_record_ci_high, per_record_value)
    per_high = max(per_record_ci_low, per_record_ci_high, per_record_value)
    hist_low = min(historical_ci_low, historical_ci_high, historical_value)
    hist_high = max(historical_ci_low, historical_ci_high, historical_value)

    return EconomicImpactResult(
        impact_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
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
        historical_impact=EffectEstimate(
            historical_value,
            hist_low,
            hist_high,
            confidence_level,
            "cluster_bootstrap_customer_id_combined_window",
            outcome.unit,
        ),
        annualization_justified=False,
        materiality_pass=materiality_pass,
        annualized_impact=None,
    )
