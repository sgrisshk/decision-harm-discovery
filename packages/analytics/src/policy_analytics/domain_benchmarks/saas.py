"""SaaS subscription/churn domain benchmark (TASK-061, domain 2 of 6).

Subscriptions, churn, expansion, and onboarding — structurally distinct from both travel and
e-commerce: recurring-revenue decision features (plan tier, seat count, billing cycle),
onboarding-track/account-owner routing as the confounding source, and a churn/expansion outcome
decomposition rather than cancellation/return.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from typing import Any

from policy_analytics.domain_benchmarks.common import (
    CorruptionOp,
    DomainRunConfig,
    DomainSpec,
    PatternDefinition,
    Row,
    TrapDefinition,
)

DOMAIN_ID = "saas"
SCHEMA_VERSION = "saas-canonical-v1.0.0"
START_DATE = date(2024, 1, 1)
DEVELOPMENT_END = "2024-12-31"
VALIDATION_END = "2025-06-30"
FUTURE_HOLDOUT_END = "2025-12-31"


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _weighted(rng: random.Random, values: list[str], weights: list[float]) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


PATTERNS: tuple[PatternDefinition, ...] = (
    PatternDefinition(
        id="S01",
        name="Self-serve high-discount monthly churn",
        rule="onboarding_track=self_serve AND discount_pct>=0.35 AND billing_cycle=monthly",
        behavior="stable",
        configured_effect={
            "csm_cost_delta_usd": 30,
            "churn_logit_delta": 1.0,
            "support_ticket_rate_delta": 0.55,
        },
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="S02",
        name="Enterprise Q4 budget-season bulk deal",
        rule="plan_tier=enterprise AND seat_count>=50 AND discount_pct>=0.25 AND month IN [11,12]",
        behavior="seasonal",
        configured_effect={
            "csm_cost_delta_usd": {
                "intercept": 38,
                "seat_count_coefficient": 0.6,
                "formula": "38 + 0.6 * seat_count",
            },
            "support_ticket_rate_delta": 0.75,
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [11, 12],
        },
    ),
    PatternDefinition(
        id="S03",
        name="No-trial small-company paid-channel risk",
        rule="trial_used=false AND company_size_band=small AND acquisition_channel=paid",
        behavior="stable",
        configured_effect={"csm_cost_delta_usd": 16, "churn_logit_delta": 0.66},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="S04",
        name="White-glove finance winter integration migration",
        rule="onboarding_track=white_glove AND industry=finance AND integrations_connected>=4 "
        "AND month IN [12,1,2]",
        behavior="seasonal",
        configured_effect={"csm_cost_delta_usd": 26, "support_ticket_rate_delta": 0.5},
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [12, 1, 2],
        },
    ),
    PatternDefinition(
        id="S05",
        name="Owner 4 trial-conversion override",
        rule="account_owner=Owner 4 AND trial_used=true AND mrr_usd>=800",
        behavior="stable",
        configured_effect={"csm_cost_delta_usd": 34},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="S06",
        name="Mobile monthly ACH checkout friction",
        rule="signup_source_device=mobile AND billing_cycle=monthly AND payment_method=ach",
        behavior="stable",
        configured_effect={"csm_cost_delta_usd": 20, "churn_logit_delta": 0.9},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="S07",
        name="Guided partner medium-company late-period drift",
        rule="onboarding_track=guided AND acquisition_channel=partner "
        "AND company_size_band=medium AND drift_period=late",
        behavior="drift",
        configured_effect={"csm_cost_delta_usd": 24, "support_ticket_rate_delta": 0.32},
        valid_interval={"start_inclusive": "2025-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="S08",
        name="Over-provisioned enterprise-tier mismatch",
        rule="plan_tier=enterprise AND seat_count<=2 AND integrations_connected=0",
        behavior="stable",
        configured_effect={"csm_cost_delta_usd": 31, "support_ticket_rate_delta": 0.65},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="S09",
        name="Self-serve Q4 bulk heterogeneous by company size",
        rule="onboarding_track=self_serve AND month IN [9,10,11] AND seat_count>=20",
        behavior="heterogeneous",
        configured_effect={
            "csm_cost_delta_usd": {"by_company_size_band": {"large": 42, "otherwise": 15}},
            "churn_logit_delta": {"by_company_size_band": {"large": 0.55, "otherwise": 0.18}},
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [9, 10, 11],
        },
    ),
)

#: Designed from the start against `HANDOFF-053`'s lessons (domain 1's post-hoc fix): every
#: mechanism below is gated behind `config.trap_active(...)`, rides a direct (not
#: complexity-Bernoulli-mediated) pathway to `net_contribution_usd`, and is independently
#: verified `|z| > 2` active / `|z| < 2` inactive by
#: `tests/analytics/test_domain_benchmarks.py`'s generic live-trap checks before being declared
#: here — not narratively plausible metadata written first and audited later.
TRAPS: tuple[TrapDefinition, ...] = (
    TrapDefinition(
        id="ST01",
        apparent_feature="account_owner=Owner 2",
        confounded_by=("seat_count",),
        note="seat_count feeds mrr_usd directly (+3.5/seat), not via the complexity score.",
    ),
    TrapDefinition(
        id="ST02",
        apparent_feature="onboarding_track=white_glove",
        confounded_by=("company_size_band",),
        note="Large companies also skew toward higher plan tiers (direct via tier_price->mrr).",
    ),
    TrapDefinition(
        id="ST03",
        apparent_feature="acquisition_channel=paid",
        confounded_by=("discount_pct",),
        note=(
            "A proxy/mediator trap, not a pure non-causal assignment artifact like ST01/ST02/"
            "ST04: acquisition_channel has zero direct effect of its own, but it does causally "
            "shift discount_pct, which then genuinely reduces margin."
        ),
    ),
    TrapDefinition(
        id="ST04",
        apparent_feature="payment_method=ach",
        confounded_by=("mrr_usd",),
        note="High-mrr accounts skew toward ACH (enterprise-style invoicing), a direct pathway.",
    ),
    TrapDefinition(
        id="ST05",
        apparent_feature="trial_used=true",
        confounded_by=("seat_count",),
        note=(
            "S05 is a genuine interaction; the main effect is a trap. Driven by seat_count<=3 "
            "(the opposite tail from ST01's seat_count>=30 — no overlap), independent of ST03's "
            "discount_pct pathway."
        ),
    ),
)

FEATURE_TIMING: dict[str, tuple[str, str]] = {
    "subscription_id": ("IDENTIFIER", "Unique subscription identifier"),
    "account_id": ("IDENTIFIER", "Stable account identifier"),
    "signup_date": ("DECISION_TIME", "Decision timestamp"),
    "plan_tier": ("DECISION_TIME", "Subscribed plan tier"),
    "billing_cycle": ("DECISION_TIME", "Monthly or annual billing"),
    "seat_count": ("DECISION_TIME", "Licensed seats at signup"),
    "mrr_usd": ("DECISION_TIME", "Quoted monthly recurring revenue at signup"),
    "discount_pct": ("DECISION_TIME", "Discount negotiated at signup"),
    "acquisition_channel": ("DECISION_TIME", "Acquisition source"),
    "signup_source_device": ("DECISION_TIME", "Signup device"),
    "industry": ("DECISION_TIME", "Customer industry vertical"),
    "company_size_band": ("DECISION_TIME", "Company size band at signup"),
    "account_owner": ("DECISION_TIME", "Customer success/account owner"),
    "onboarding_track": ("DECISION_TIME", "Onboarding track selected at signup"),
    "trial_used": ("DECISION_TIME", "Whether a trial preceded this subscription"),
    "payment_method": ("DECISION_TIME", "Chosen payment method"),
    "integrations_connected": ("DECISION_TIME", "Integrations connected at signup"),
    "currency": ("METADATA", "Billing currency"),
    "churned": ("OUTCOME", "Churn observed after signup"),
    "mrr_lost_usd": ("OUTCOME", "Realized MRR lost to churn"),
    "downgrade_date": ("POST_DECISION", "Date of a downgrade or churn event"),
    "reschedule_events": ("POST_DECISION", "Plan/seat changes after signup"),
    "support_tickets": ("POST_DECISION", "Support interactions after signup"),
    "support_cost_usd": ("OUTCOME", "Realized support cost"),
    "csm_intervention_cost_usd": ("OUTCOME", "Realized unplanned CSM intervention cost"),
    "gross_margin_usd": ("OUTCOME", "Realized gross margin"),
    "net_contribution_usd": ("OUTCOME", "Realized contribution after downstream costs"),
    "expansion_90d": ("OUTCOME", "Expansion (seats/tier upgrade) within outcome window"),
    "last_modified_at": ("POST_DECISION", "Operational update timestamp; leakage field"),
}

DECLARED_TYPES: dict[str, Any] = {
    "subscription_id": "string",
    "account_id": "string",
    "signup_date": "date",
    "plan_tier": "string",
    "billing_cycle": "string",
    "seat_count": "integer",
    "mrr_usd": "decimal",
    "discount_pct": "decimal",
    "acquisition_channel": "string",
    "signup_source_device": "string",
    "industry": "string",
    "company_size_band": "string",
    "account_owner": "string",
    "onboarding_track": "string",
    "trial_used": "boolean",
    "payment_method": "string",
    "integrations_connected": "integer",
    "currency": "string",
    "churned": "boolean",
    "mrr_lost_usd": "decimal",
    "downgrade_date": "nullable_date",
    "reschedule_events": "integer",
    "support_tickets": "integer",
    "support_cost_usd": "decimal",
    "csm_intervention_cost_usd": "decimal",
    "gross_margin_usd": "decimal",
    "net_contribution_usd": "decimal",
    "expansion_90d": "nullable_boolean",
    "last_modified_at": "date",
}

OUTCOME_COLUMNS = (
    "churned",
    "mrr_lost_usd",
    "support_cost_usd",
    "csm_intervention_cost_usd",
    "gross_margin_usd",
    "net_contribution_usd",
    "expansion_90d",
)


def _pattern_scale(config: DomainRunConfig, pattern_id: str) -> float:
    return config.scale_for(pattern_id) if config.is_active(pattern_id) else 0.0


def generate_row(
    index: int, rng: random.Random, config: DomainRunConfig, disabled_pattern_id: str | None
) -> tuple[Row, list[str]]:
    signup_date = START_DATE + timedelta(days=rng.randrange(731))
    month = signup_date.month
    drift_period = "late" if signup_date >= date(2025, 1, 1) else "early"

    company_size_band = _weighted(rng, ["small", "medium", "large"], [0.52, 0.33, 0.15])
    industry = _weighted(
        rng,
        ["technology", "finance", "retail", "healthcare", "manufacturing"],
        [0.26, 0.20, 0.19, 0.18, 0.17],
    )
    acquisition_channel = _weighted(
        rng, ["organic", "paid", "partner", "outbound_sales"], [0.30, 0.28, 0.22, 0.20]
    )
    signup_source_device = _weighted(rng, ["desktop", "mobile"], [0.78, 0.22])

    # ST02 (part 1/2): a real, direct-via-tier-price pathway — large companies skew toward
    # higher plan tiers, adjusted here, before plan_tier is drawn, rather than as a second
    # after-the-fact draw. Gated so the "0 traps" variant sees the plain baseline distribution.
    tier_weights = [0.55, 0.32, 0.13]
    if month in {11, 12}:
        tier_weights = [0.40, 0.35, 0.25]
    if config.trap_active("ST02") and company_size_band == "large":
        tier_weights = [
            max(0.0, tier_weights[0] - 0.15),
            max(0.0, tier_weights[1] - 0.15),
            tier_weights[2] + 0.30,
        ]
    plan_tier = _weighted(rng, ["starter", "pro", "enterprise"], tier_weights)
    seat_count = (
        rng.randint(1, 5)
        if plan_tier == "starter"
        else rng.randint(3, 25)
        if plan_tier == "pro"
        else max(1, min(200, int(rng.gauss(45, 30))))
    )
    billing_cycle = _weighted(rng, ["monthly", "annual"], [0.6, 0.4])
    # ST05: S05 is a genuine interaction; the main effect is a trap. trial_used's trap-gated
    # driver is seat_count<=3 (a direct mrr-mediated pathway), independent of ST01's
    # seat_count>=30 (opposite tail, no overlap) and of ST03's discount_pct pathway.
    trial_probability = 0.30 if company_size_band == "small" else 0.62
    if config.trap_active("ST05") and seat_count <= 3:
        trial_probability = min(0.95, trial_probability + 0.20)
    trial_used = rng.random() < trial_probability
    integrations_connected = max(0, min(12, int(rng.gauss(2.2, 2.0))))

    # Deliberately non-random assignment creates observed confounding traps (ST01/ST02/ST04/ST05)
    # — each gated behind config.trap_active so the "0 traps" variant is genuinely trap-free, not
    # just undocumented (the class of bug HANDOFF-053 found in domain 1). Each apparent feature
    # (account_owner/onboarding_track/payment_method) has zero baseline effect of its own; only
    # the real, direct-pathway confounder does the work, matching direct_effect: 0.
    owner_weights = [1.0] * 8
    if config.trap_active("ST01") and seat_count >= 30:
        owner_weights[1] += 4.5  # Owner 2 receives intrinsically difficult accounts. seat_count
        # feeds mrr directly (below), unlike a complexity-mediated driver — verified |z| > 2.
    account_owner = _weighted(rng, [f"Owner {number}" for number in range(1, 9)], owner_weights)
    track_weights = [1.0, 1.0, 1.0]
    if config.trap_active("ST02") and company_size_band == "large":
        track_weights[2] += 3.0  # white_glove skews to large accounts (part 2/2 of ST02).
    if month in {11, 12}:
        track_weights[0] += 1.2  # self_serve seasonal shift — baseline realism, not a trap.
    onboarding_track = _weighted(rng, ["self_serve", "guided", "white_glove"], track_weights)

    tier_price = {"starter": 29, "pro": 99, "enterprise": 399}[plan_tier]
    mrr = max(15.0, rng.gauss(tier_price, tier_price * 0.22) + 3.5 * seat_count)

    # ST03: acquisition_channel=paid's raw correlation with margin runs entirely through
    # discount_pct (a real, DECISION_TIME, independently-discoverable feature) — a proxy/mediator
    # trap, not a pure non-causal assignment artifact like ST01/ST02/ST04. Gated separately from
    # any other trap so it stays independently toggleable.
    discount_choices = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
    discount_weights = [0.22, 0.16, 0.20, 0.16, 0.12, 0.09, 0.05]
    if config.trap_active("ST03") and acquisition_channel == "paid":
        discount_weights[-2] += 0.10
        discount_weights[-1] += 0.08
    discount_pct = rng.choices(discount_choices, weights=discount_weights, k=1)[0]

    # ST04: ach usage skews toward high-mrr accounts (enterprise-style invoicing preference) — a
    # direct mrr-mediated pathway, not the weak signup_source_device link an earlier version used.
    payment_weights = [0.58, 0.28, 0.14]  # card, invoice, ach
    if signup_source_device == "mobile":
        payment_weights = [0.42, 0.20, 0.38]  # mobile skews toward ach — baseline realism, but see
        # module note: kept ungated deliberately, unlike ecommerce's analogous case, because this
        # branch alone (without ST04) empirically clears neither the noise- nor active-side bar on
        # its own — it is genuinely too weak to matter either way, verified.
    if config.trap_active("ST04") and mrr >= 250:
        payment_weights[2] += 0.22
    payment_method = _weighted(rng, ["card", "invoice", "ach"], payment_weights)

    complexity = (
        int(company_size_band == "large")
        + int(seat_count >= 30)
        + int(mrr >= 300)
        + int(payment_method == "ach")
    )
    churn_logit = -3.05 + 0.30 * complexity
    support_lambda = 0.15 + 0.09 * complexity
    csm_cost_delta = 0.0

    def active(pattern_id: str) -> bool:
        return config.is_active(pattern_id) and disabled_pattern_id != pattern_id

    patterns: list[str] = []

    if onboarding_track == "self_serve" and discount_pct >= 0.35 and billing_cycle == "monthly":
        patterns.append("S01")
        if active("S01"):
            scale = _pattern_scale(config, "S01")
            csm_cost_delta += 30 * scale
            churn_logit += 1.0 * scale
            support_lambda += 0.55 * scale
    if (
        plan_tier == "enterprise"
        and seat_count >= 50
        and discount_pct >= 0.25
        and month in {11, 12}
    ):
        patterns.append("S02")
        if active("S02"):
            scale = _pattern_scale(config, "S02")
            csm_cost_delta += (38 + 0.6 * seat_count) * scale
            support_lambda += 0.75 * scale
    if not trial_used and company_size_band == "small" and acquisition_channel == "paid":
        patterns.append("S03")
        if active("S03"):
            scale = _pattern_scale(config, "S03")
            csm_cost_delta += 16 * scale
            churn_logit += 0.66 * scale
    if (
        onboarding_track == "white_glove"
        and industry == "finance"
        and integrations_connected >= 4
        and month in {12, 1, 2}
    ):
        patterns.append("S04")
        if active("S04"):
            scale = _pattern_scale(config, "S04")
            csm_cost_delta += 26 * scale
            support_lambda += 0.5 * scale
    if account_owner == "Owner 4" and trial_used and mrr >= 800:
        patterns.append("S05")
        if active("S05"):
            csm_cost_delta += 34 * _pattern_scale(config, "S05")
    if signup_source_device == "mobile" and billing_cycle == "monthly" and payment_method == "ach":
        patterns.append("S06")
        if active("S06"):
            scale = _pattern_scale(config, "S06")
            csm_cost_delta += 20 * scale
            churn_logit += 0.9 * scale
    if (
        onboarding_track == "guided"
        and acquisition_channel == "partner"
        and company_size_band == "medium"
        and drift_period == "late"
    ):
        patterns.append("S07")
        if active("S07"):
            scale = _pattern_scale(config, "S07")
            csm_cost_delta += 24 * scale
            support_lambda += 0.32 * scale
    if plan_tier == "enterprise" and seat_count <= 2 and integrations_connected == 0:
        patterns.append("S08")
        if active("S08"):
            scale = _pattern_scale(config, "S08")
            csm_cost_delta += 31 * scale
            support_lambda += 0.65 * scale
    if onboarding_track == "self_serve" and month in {9, 10, 11} and seat_count >= 20:
        patterns.append("S09")
        if active("S09"):
            scale = _pattern_scale(config, "S09")
            segment_cost = 42 if company_size_band == "large" else 15
            segment_logit = 0.55 if company_size_band == "large" else 0.18
            csm_cost_delta += segment_cost * scale
            churn_logit += segment_logit * scale

    churned = rng.random() < _sigmoid(churn_logit)
    support_tickets = min(6, int(rng.expovariate(1 / max(support_lambda, 0.01))))
    support_cost = support_tickets * rng.uniform(7, 20)
    payment_fee = mrr * (0.01 + 0.004 * max(0, integrations_connected - 4))
    base_cost_ratio = rng.uniform(0.32, 0.45) + 0.01 * complexity
    base_cost = mrr * base_cost_ratio
    csm_cost = max(0.0, rng.gauss(5 + csm_cost_delta, 8 + 0.08 * csm_cost_delta))
    gross_revenue = mrr * (1 - discount_pct)
    lost_ratio = rng.uniform(0.7, 1.0) if churned else 0.0
    mrr_lost = gross_revenue * lost_ratio
    gross_margin = gross_revenue - base_cost - mrr_lost
    net_contribution = gross_margin - csm_cost - support_cost - payment_fee
    expansion_probability = _sigmoid(-0.55 - 0.9 * churned - 0.0006 * max(0, -net_contribution))
    expansion: bool | None = rng.random() < expansion_probability
    if rng.random() < (0.40 if churned else 0.07):
        expansion = None
    downgrade_date = signup_date + timedelta(days=rng.randint(3, 60)) if churned else None

    row: Row = {
        "subscription_id": f"SAAS-{index + 1:05d}",
        "account_id": f"SAAS-ACC-{((index * 2_654_435_761) % 3_200) + 1:04d}",
        "signup_date": signup_date.isoformat(),
        "plan_tier": plan_tier,
        "billing_cycle": billing_cycle,
        "seat_count": seat_count,
        "mrr_usd": round(mrr, 2),
        "discount_pct": discount_pct,
        "acquisition_channel": acquisition_channel,
        "signup_source_device": signup_source_device,
        "industry": industry,
        "company_size_band": company_size_band,
        "account_owner": account_owner,
        "onboarding_track": onboarding_track,
        "trial_used": trial_used,
        "payment_method": payment_method,
        "integrations_connected": integrations_connected,
        "currency": "USD",
        "churned": churned,
        "mrr_lost_usd": round(mrr_lost, 2),
        "downgrade_date": downgrade_date.isoformat() if downgrade_date else "",
        "reschedule_events": min(5, int(rng.expovariate(1 / (0.22 + 0.13 * complexity)))),
        "support_tickets": support_tickets,
        "support_cost_usd": round(support_cost, 2),
        "csm_intervention_cost_usd": round(csm_cost, 2),
        "gross_margin_usd": round(gross_margin, 2),
        "net_contribution_usd": round(net_contribution, 2),
        "expansion_90d": expansion if expansion is not None else "",
        "last_modified_at": (signup_date + timedelta(days=rng.randint(0, 90))).isoformat(),
    }
    return row, patterns


def corruption_ops(config: DomainRunConfig) -> tuple[CorruptionOp, ...]:
    def clear_owner(row: Row) -> None:
        row["account_owner"] = ""

    def mixed_date(row: Row) -> None:
        parsed = date.fromisoformat(str(row["signup_date"]))
        row["signup_date"] = parsed.strftime("%d/%m/%Y")

    def currency_symbol(row: Row) -> None:
        row["mrr_usd"] = f"${row['mrr_usd']}"

    def industry_upper(row: Row) -> None:
        row["industry"] = str(row["industry"]).upper()

    def invalid_seats(row: Row) -> None:
        row["seat_count"] = -1

    def invalid_discount(row: Row) -> None:
        row["discount_pct"] = 1.3

    def whitespace_owner(row: Row) -> None:
        row["account_owner"] = f" {row['account_owner']} "

    return (
        CorruptionOp("missing_account_owner", 18, clear_owner),
        CorruptionOp("mixed_date_format", 13, mixed_date),
        CorruptionOp("currency_symbol", 9, currency_symbol),
        CorruptionOp("industry_variant", 14, industry_upper),
        CorruptionOp("invalid_seat_count", 3, invalid_seats),
        CorruptionOp("invalid_discount", 2, invalid_discount),
        CorruptionOp("whitespace_owner", 11, whitespace_owner),
        CorruptionOp("duplicate_source_rows", config.dirty_duplicate_rows, lambda row: None),
    )


SPEC = DomainSpec(
    domain_id=DOMAIN_ID,
    schema_version=SCHEMA_VERSION,
    primary_id_column="subscription_id",
    clustering_key="account_id",
    decision_timestamp_column="signup_date",
    outcome_columns=OUTCOME_COLUMNS,
    primary_outcome_column="net_contribution_usd",
    feature_timing=FEATURE_TIMING,
    declared_types=DECLARED_TYPES,
    patterns=PATTERNS,
    traps=TRAPS,
    generate_row=generate_row,
    corruption_ops=corruption_ops,
    development_end=DEVELOPMENT_END,
    validation_end=VALIDATION_END,
    future_holdout_end=FUTURE_HOLDOUT_END,
)
