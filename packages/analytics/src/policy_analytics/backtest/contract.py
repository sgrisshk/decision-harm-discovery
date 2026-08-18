"""Policy backtest result contract v1.0.0 (TASK-032).

Implements `docs/analytics/validation-contract.md` §9's pre-registered backtest methodology and
fills `docs/product/policy-candidate-domain-model.md` §7's reserved, until-now-`null`
`backtest_result` field. Full semantics, worked derivation, and disclosed scope limits:
`docs/analytics/policy-backtest-contract.md`.

**This is not a causal or forward-looking estimate.** Every number here is a *mechanical replay*
of the trigger condition against the out-of-period `future_holdout` split — "what would this rule
have flagged, and what did those decisions' outcomes actually look like" — never "what will
happen if we enforce this," which would require an actual experiment (`EXPERIMENT_ONLY`
readiness, `docs/analytics/validation-contract.md` §7) or a live shadow-mode rollout, neither of
which this module performs. §9's own words: "an upper bound on mechanical effect, labelled as
such, and is not a forecast."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from policy_analytics.validation.report import EffectEstimate

BACKTEST_CONTRACT_VERSION = "1.0.0"

#: §9's "out-of-period first" rule, made a hard constant rather than a caller-supplied parameter —
#: a backtest computed against any other split is not a backtest under this contract.
BACKTEST_WINDOW_SPLIT = "future_holdout"

#: v1.0.0 only defines a "bad outcome" threshold for the primary outcome, using its own
#: already-documented absolute meaning ("a negative value... is a booking that lost money
#: outright," `policy_analytics.outcomes.contract`) — not a new invented threshold. Extending the
#: avoided/suppressed count split to a secondary outcome needs its own disclosed threshold
#: decision, out of scope here.
BAD_OUTCOME_SUPPORTED_OUTCOME_ID = "contribution_margin_eur"
BAD_OUTCOME_THRESHOLD = 0.0  # contribution_margin_eur < 0.0 is "bad" (loses money outright)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """One trigger condition's mechanical replay against `future_holdout`.

    **Both sides, always** (§9): `avoided_bad_outcomes` and `suppressed_good_outcomes` are always
    both present and always sum to `affected_decisions` (missing outcome values are a contract
    violation for `contribution_margin_eur`, which has `MissingDataPolicy.COMPLETE` — never
    silently excluded). A rule is never reported as if it only ever caught bad outcomes.

    **`benefit` is deliberately unadjusted (raw, not stratified/confounder-adjusted).** §9's
    "upper bound on mechanical effect" framing calls for the *largest* honest mechanical estimate,
    not the validation contract's own more conservative adjusted effect — using the smaller
    adjusted number here would misstate the disclosed upper bound as something more certain than
    it is. `benefit_is_adjusted` is always `False` in v1.0.0, checkable rather than assumed.

    **`operational_cost` is `None` unless a real `cost_per_review_eur` was supplied.** This module
    never invents a cost-per-review figure (`ADR-004`) — the same disclosed-placeholder posture
    `ValidationThresholds.min_material_annual_impact` already takes pending real customer
    economics. When `operational_cost` is `None`, `net_effect` equals `benefit` exactly and
    `net_effect_is_cost_exclusive` is `True` — the field name that distinguishes a *known* net
    figure from a benefit-only figure not yet netted against cost, so a caller cannot mistake one
    for the other by inspecting `net_effect` alone.

    **`no_measurable_net_effect`** mirrors §9's own rule and the identical rule already used for
    economic impact and G15: a net-effect interval that includes zero must be reported as "no
    measurable net effect," never as a positive.
    """

    backtest_contract_version: str
    outcome_name: str
    outcome_unit: str
    window: str
    affected_decisions: int
    avoided_bad_outcomes: int
    suppressed_good_outcomes: int
    bad_outcome_definition: str
    benefit: EffectEstimate
    benefit_is_adjusted: bool
    operational_cost_per_review_eur: float | None
    operational_cost: EffectEstimate | None
    net_effect: EffectEstimate
    net_effect_is_cost_exclusive: bool
    no_measurable_net_effect: bool
    methodology_disclosure: str

    def __post_init__(self) -> None:
        if self.window != BACKTEST_WINDOW_SPLIT:
            raise ValueError(
                f"window must be {BACKTEST_WINDOW_SPLIT!r} (§9 out-of-period rule); "
                f"got {self.window!r}"
            )
        if self.affected_decisions < 0:
            raise ValueError("affected_decisions cannot be negative")
        if self.avoided_bad_outcomes + self.suppressed_good_outcomes != self.affected_decisions:
            raise ValueError(
                "avoided_bad_outcomes + suppressed_good_outcomes must equal affected_decisions "
                "(both sides always, §9) — a missing outcome value is a contract violation for "
                "contribution_margin_eur, not something to silently exclude"
            )
        if (self.operational_cost is not None) == (self.operational_cost_per_review_eur is None):
            raise ValueError(
                "operational_cost must be present exactly when operational_cost_per_review_eur "
                "is supplied"
            )
        if self.net_effect_is_cost_exclusive != (self.operational_cost is None):
            raise ValueError(
                "net_effect_is_cost_exclusive must be true exactly when no operational cost was "
                "netted in"
            )
        excludes_zero = self.net_effect.ci_low > 0 or self.net_effect.ci_high < 0
        if self.no_measurable_net_effect == excludes_zero:
            raise ValueError(
                "no_measurable_net_effect must be the negation of net_effect's interval excluding "
                "zero"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "backtest_contract_version": self.backtest_contract_version,
            "outcome_name": self.outcome_name,
            "outcome_unit": self.outcome_unit,
            "window": self.window,
            "affected_decisions": self.affected_decisions,
            "avoided_bad_outcomes": self.avoided_bad_outcomes,
            "suppressed_good_outcomes": self.suppressed_good_outcomes,
            "bad_outcome_definition": self.bad_outcome_definition,
            "benefit": _estimate_to_dict(self.benefit),
            "benefit_is_adjusted": self.benefit_is_adjusted,
            "operational_cost_per_review_eur": self.operational_cost_per_review_eur,
            "operational_cost": _estimate_to_dict(self.operational_cost),
            "net_effect": _estimate_to_dict(self.net_effect),
            "net_effect_is_cost_exclusive": self.net_effect_is_cost_exclusive,
            "no_measurable_net_effect": self.no_measurable_net_effect,
            "methodology_disclosure": self.methodology_disclosure,
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
