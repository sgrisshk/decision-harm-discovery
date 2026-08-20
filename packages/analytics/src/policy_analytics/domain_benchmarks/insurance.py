"""Insurance claims domain benchmark (TASK-061, domain 3 of 6).

Underwriting-adjacent claim triage, fraud, and processing cost — structurally distinct from
travel/e-commerce/SaaS: claim-intake decision features (claimed amount, documentation, filing
channel), adjuster/region routing as the confounding source, and the domain's harm direction is
inverted (higher claim cost is harm, not lower margin) relative to the other three domains.
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

DOMAIN_ID = "insurance"
SCHEMA_VERSION = "insurance-canonical-v1.0.0"
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
        id="I01",
        name="Phone high-value incomplete documentation",
        rule="claim_channel=phone AND claimed_amount_usd>=15000 AND documentation_complete=false",
        behavior="stable",
        configured_effect={
            "processing_cost_delta_usd": 60,
            "fraud_loss_delta_usd": 220,
            "denied_logit_delta": -0.4,
        },
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="I02",
        name="Winter auto collision surge",
        rule="policy_type=auto AND claim_type=collision AND claimed_amount_usd>=8000 "
        "AND month IN [12,1]",
        behavior="seasonal",
        configured_effect={
            "processing_cost_delta_usd": {
                "intercept": 45,
                "amount_coefficient": 0.004,
                "formula": "45 + 0.004 * claimed_amount_usd",
            },
            "fraud_loss_delta_usd": 90,
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [12, 1],
        },
    ),
    PatternDefinition(
        id="I03",
        name="Frequent new-policyholder online claims",
        rule="prior_claims_count>=3 AND policy_tenure_months<12 AND claim_channel=online",
        behavior="stable",
        configured_effect={"fraud_loss_delta_usd": 260, "processing_cost_delta_usd": 35},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="I04",
        name="Region D summer wildfire home claims",
        rule="region=Region D AND policy_type=home AND claim_type=fire AND month IN [6,7,8]",
        behavior="seasonal",
        configured_effect={"processing_cost_delta_usd": 75, "fraud_loss_delta_usd": 60},
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [6, 7, 8],
        },
    ),
    PatternDefinition(
        id="I05",
        name="Adjuster 4 high-value approval override",
        rule="adjuster=Adjuster 4 AND documentation_complete=true AND claimed_amount_usd>=20000",
        behavior="stable",
        configured_effect={"processing_cost_delta_usd": 85},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="I06",
        name="Rushed app health triage",
        rule="claim_channel=app AND filed_within_24h=true AND policy_type=health",
        behavior="stable",
        configured_effect={"processing_cost_delta_usd": 50, "fraud_loss_delta_usd": 70},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="I07",
        name="Region C senior liability late-period drift",
        rule="region=Region C AND claim_type=liability AND policyholder_age_band=senior "
        "AND drift_period=late",
        behavior="drift",
        configured_effect={"processing_cost_delta_usd": 55, "fraud_loss_delta_usd": 40},
        valid_interval={"start_inclusive": "2025-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="I08",
        name="Large first-time life claim mismatch",
        rule="policy_type=life AND claimed_amount_usd>=25000 AND documentation_complete=true",
        behavior="stable",
        configured_effect={"processing_cost_delta_usd": 65, "fraud_loss_delta_usd": 50},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="I09",
        name="Region B spring bulk heterogeneous by age band",
        rule="region=Region B AND month IN [3,4,5] AND claimed_amount_usd>=10000",
        behavior="heterogeneous",
        configured_effect={
            "processing_cost_delta_usd": {
                "by_policyholder_age_band": {"senior": 95, "otherwise": 35}
            },
            "fraud_loss_delta_usd": {"by_policyholder_age_band": {"senior": 30, "otherwise": 80}},
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [3, 4, 5],
        },
    ),
)

#: Designed from the start against `HANDOFF-053`'s lessons: every mechanism gated behind
#: `config.trap_active(...)`, riding a direct (not complexity-mediated) pathway to
#: `net_claim_cost_usd`, independently verified `|z| > 2` active / `|z| < 2` inactive before being
#: declared here.
TRAPS: tuple[TrapDefinition, ...] = (
    TrapDefinition(
        id="IT01",
        apparent_feature="adjuster=Adjuster 2",
        confounded_by=("claimed_amount_usd",),
        note="High-value claims route to Adjuster 2; claimed_amount_usd drives payout directly.",
    ),
    TrapDefinition(
        id="IT02",
        apparent_feature="region=Region A",
        confounded_by=("claim_type",),
        note="Region A skews toward fire/theft claims, which carry a higher direct base cost.",
    ),
    TrapDefinition(
        id="IT03",
        apparent_feature="claim_channel=online",
        confounded_by=("deductible_usd",),
        note="Online filers skew toward low-deductible policies, which directly raises net payout.",
    ),
    TrapDefinition(
        id="IT04",
        apparent_feature="filed_within_24h=true",
        confounded_by=("claimed_amount_usd",),
        note="Small/simple claims get filed quickly — opposite tail from IT01, no overlap.",
    ),
    TrapDefinition(
        id="IT05",
        apparent_feature="documentation_complete=true",
        confounded_by=("prior_claims_count",),
        note=(
            "I05 is a genuine interaction; the main effect is a trap. Repeat claimants have more "
            "practice assembling complete documentation; prior_claims_count directly raises "
            "processing cost (cross-referencing overhead) independent of this trap."
        ),
    ),
)

FEATURE_TIMING: dict[str, tuple[str, str]] = {
    "claim_id": ("IDENTIFIER", "Unique claim identifier"),
    "policyholder_id": ("IDENTIFIER", "Stable policyholder identifier"),
    "claim_filed_date": ("DECISION_TIME", "Decision timestamp"),
    "policy_type": ("DECISION_TIME", "Policy line"),
    "claim_type": ("DECISION_TIME", "Claim type"),
    "claimed_amount_usd": ("DECISION_TIME", "Amount claimed at filing"),
    "policy_tenure_months": ("DECISION_TIME", "Months the policy has been active at filing"),
    "policyholder_age_band": ("DECISION_TIME", "Policyholder age band"),
    "claim_channel": ("DECISION_TIME", "Channel the claim was filed through"),
    "prior_claims_count": ("DECISION_TIME", "Prior claims on file at filing time"),
    "adjuster": ("DECISION_TIME", "Assigned claims adjuster"),
    "region": ("DECISION_TIME", "Policyholder region"),
    "documentation_complete": ("DECISION_TIME", "Whether documentation was complete at filing"),
    "deductible_usd": ("DECISION_TIME", "Policy deductible on file"),
    "filed_within_24h": ("DECISION_TIME", "Whether the claim was filed within 24 hours"),
    "currency": ("METADATA", "Settlement currency"),
    "denied": ("OUTCOME", "Claim denied"),
    "fraud_flagged": ("OUTCOME", "Claim flagged for fraud"),
    "payout_amount_usd": ("OUTCOME", "Realized payout amount"),
    "investigation_opened_date": ("POST_DECISION", "Date a fraud investigation opened"),
    "adjuster_notes_count": ("POST_DECISION", "Adjuster note events after filing"),
    "processing_cost_usd": ("OUTCOME", "Realized claim-processing cost"),
    "fraud_loss_usd": ("OUTCOME", "Realized unrecovered fraud loss"),
    "processing_days": ("OUTCOME", "Days to process the claim"),
    "net_claim_cost_usd": ("OUTCOME", "Realized total cost of the claim (payout+processing+fraud)"),
    "reopened_90d": ("OUTCOME", "Claim reopened within outcome window"),
    "last_modified_at": ("POST_DECISION", "Operational update timestamp; leakage field"),
}

DECLARED_TYPES: dict[str, Any] = {
    "claim_id": "string",
    "policyholder_id": "string",
    "claim_filed_date": "date",
    "policy_type": "string",
    "claim_type": "string",
    "claimed_amount_usd": "decimal",
    "policy_tenure_months": "integer",
    "policyholder_age_band": "string",
    "claim_channel": "string",
    "prior_claims_count": "integer",
    "adjuster": "string",
    "region": "string",
    "documentation_complete": "boolean",
    "deductible_usd": "decimal",
    "filed_within_24h": "boolean",
    "currency": "string",
    "denied": "boolean",
    "fraud_flagged": "boolean",
    "payout_amount_usd": "decimal",
    "investigation_opened_date": "nullable_date",
    "adjuster_notes_count": "integer",
    "processing_cost_usd": "decimal",
    "fraud_loss_usd": "decimal",
    "processing_days": "integer",
    "net_claim_cost_usd": "decimal",
    "reopened_90d": "nullable_boolean",
    "last_modified_at": "date",
}

OUTCOME_COLUMNS = (
    "denied",
    "fraud_flagged",
    "payout_amount_usd",
    "processing_cost_usd",
    "fraud_loss_usd",
    "net_claim_cost_usd",
    "reopened_90d",
)


def _pattern_scale(config: DomainRunConfig, pattern_id: str) -> float:
    return config.scale_for(pattern_id) if config.is_active(pattern_id) else 0.0


def generate_row(
    index: int, rng: random.Random, config: DomainRunConfig, disabled_pattern_id: str | None
) -> tuple[Row, list[str]]:
    claim_filed_date = START_DATE + timedelta(days=rng.randrange(731))
    month = claim_filed_date.month
    drift_period = "late" if claim_filed_date >= date(2025, 1, 1) else "early"

    policy_type = _weighted(rng, ["auto", "home", "health", "life"], [0.38, 0.27, 0.24, 0.11])
    claim_type_by_policy = {
        "auto": (["collision", "theft", "liability"], [0.55, 0.20, 0.25]),
        "home": (["fire", "theft", "liability"], [0.30, 0.35, 0.35]),
        "health": (["medical", "liability"], [0.85, 0.15]),
        "life": (["medical", "liability"], [0.70, 0.30]),
    }
    claim_type_choices, claim_type_weights = claim_type_by_policy[policy_type]
    claim_type = _weighted(rng, claim_type_choices, claim_type_weights)

    policyholder_age_band = _weighted(rng, ["young_adult", "adult", "senior"], [0.28, 0.44, 0.28])
    policy_tenure_months = max(1, min(240, int(rng.gauss(48, 36))))
    prior_claims_count = max(0, min(8, int(rng.expovariate(1 / 1.1))))
    filed_within_24h = rng.random() < 0.45

    # Deliberately non-random assignment creates observed confounding traps (IT01/IT02/IT03/IT04)
    # — each gated behind config.trap_active so the "0 traps" variant is genuinely trap-free, not
    # just undocumented (HANDOFF-053). adjuster/region/claim_channel/filed_within_24h themselves
    # have zero baseline effect of their own; only the direct-pathway confounder does the work.
    claim_type_base_cost = {
        "collision": 1.0,
        "theft": 1.35,
        "fire": 1.6,
        "liability": 1.15,
        "medical": 0.85,
    }[claim_type]
    claimed_amount = max(
        200.0, rng.gauss(6000, 3200) * claim_type_base_cost * (1.0 + 0.15 * prior_claims_count)
    )

    adjuster_weights = [1.0] * 8
    if config.trap_active("IT01") and claimed_amount >= 12000:
        adjuster_weights[1] += 5.0  # Adjuster 2 receives intrinsically high-value claims.
    adjuster = _weighted(rng, [f"Adjuster {number}" for number in range(1, 9)], adjuster_weights)

    region_weights = [1.0, 1.0, 1.0, 1.0]  # Region A, B, C, D
    if config.trap_active("IT02") and claim_type in {"fire", "theft"}:
        region_weights[0] += 3.0  # Region A skews toward property-crime-prone claim types.
    region = _weighted(rng, ["Region A", "Region B", "Region C", "Region D"], region_weights)

    deductible_choices = [250.0, 500.0, 1000.0, 2500.0]
    deductible_weights = [0.20, 0.35, 0.30, 0.15]
    deductible = rng.choices(deductible_choices, weights=deductible_weights, k=1)[0]

    channel_weights = [0.30, 0.24, 0.24, 0.22]  # phone, app, agent, online
    if config.trap_active("IT03") and deductible <= 500:
        # Deductible only ranges $250-$2,500 against claimed_amount's much larger variance, so a
        # mild weight nudge here is invisible against net_claim_cost_usd's noise floor — the skew
        # has to be this hard for the mean-deductible gap between channels to clear the outcome's
        # background variance (verified empirically, |z|~4-5 at n=10,000; a 0.26/0.22/0.20/0.32
        # nudge measured |z|<0.1).
        channel_weights = [0.12, 0.08, 0.05, 0.75]  # low-deductible policyholders skew online hard.
    claim_channel = _weighted(rng, ["phone", "app", "agent", "online"], channel_weights)

    if config.trap_active("IT04") and claimed_amount <= 3000:
        filed_within_24h = rng.random() < 0.75  # small/simple claims get filed quickly.

    doc_probability = 0.55
    if config.trap_active("IT05") and prior_claims_count >= 2:
        doc_probability = 0.85  # repeat claimants are practiced at documentation.
    documentation_complete = rng.random() < doc_probability

    complexity = (
        int(claimed_amount >= 15000)
        + int(not documentation_complete)
        + int(prior_claims_count >= 3)
        + int(claim_channel == "phone")
    )
    denied_logit = -1.55 - 0.28 * complexity
    fraud_logit = -3.3 + 0.35 * complexity
    processing_cost_delta = 0.0
    fraud_loss_delta = 0.0
    denied_logit_delta = 0.0

    def active(pattern_id: str) -> bool:
        return config.is_active(pattern_id) and disabled_pattern_id != pattern_id

    patterns: list[str] = []

    if claim_channel == "phone" and claimed_amount >= 15000 and not documentation_complete:
        patterns.append("I01")
        if active("I01"):
            scale = _pattern_scale(config, "I01")
            processing_cost_delta += 60 * scale
            fraud_loss_delta += 220 * scale
            denied_logit_delta += -0.4 * scale
    if (
        policy_type == "auto"
        and claim_type == "collision"
        and claimed_amount >= 8000
        and month in {12, 1}
    ):
        patterns.append("I02")
        if active("I02"):
            scale = _pattern_scale(config, "I02")
            processing_cost_delta += (45 + 0.004 * claimed_amount) * scale
            fraud_loss_delta += 90 * scale
    if prior_claims_count >= 3 and policy_tenure_months < 12 and claim_channel == "online":
        patterns.append("I03")
        if active("I03"):
            scale = _pattern_scale(config, "I03")
            fraud_loss_delta += 260 * scale
            processing_cost_delta += 35 * scale
    if (
        region == "Region D"
        and policy_type == "home"
        and claim_type == "fire"
        and month in {6, 7, 8}
    ):
        patterns.append("I04")
        if active("I04"):
            scale = _pattern_scale(config, "I04")
            processing_cost_delta += 75 * scale
            fraud_loss_delta += 60 * scale
    if adjuster == "Adjuster 4" and documentation_complete and claimed_amount >= 20000:
        patterns.append("I05")
        if active("I05"):
            processing_cost_delta += 85 * _pattern_scale(config, "I05")
    if claim_channel == "app" and filed_within_24h and policy_type == "health":
        patterns.append("I06")
        if active("I06"):
            scale = _pattern_scale(config, "I06")
            processing_cost_delta += 50 * scale
            fraud_loss_delta += 70 * scale
    if (
        region == "Region C"
        and claim_type == "liability"
        and policyholder_age_band == "senior"
        and drift_period == "late"
    ):
        patterns.append("I07")
        if active("I07"):
            scale = _pattern_scale(config, "I07")
            processing_cost_delta += 55 * scale
            fraud_loss_delta += 40 * scale
    if policy_type == "life" and claimed_amount >= 25000 and documentation_complete:
        patterns.append("I08")
        if active("I08"):
            scale = _pattern_scale(config, "I08")
            processing_cost_delta += 65 * scale
            fraud_loss_delta += 50 * scale
    if region == "Region B" and month in {3, 4, 5} and claimed_amount >= 10000:
        patterns.append("I09")
        if active("I09"):
            scale = _pattern_scale(config, "I09")
            senior = policyholder_age_band == "senior"
            processing_cost_delta += (95 if senior else 35) * scale
            fraud_loss_delta += (30 if senior else 80) * scale

    denied = rng.random() < _sigmoid(denied_logit + denied_logit_delta)
    fraud_flagged = rng.random() < _sigmoid(fraud_logit)
    payout_amount = 0.0 if denied else max(0.0, claimed_amount - deductible)
    processing_cost = max(
        0.0, rng.gauss(35 + processing_cost_delta, 20 + 0.1 * processing_cost_delta)
    )
    processing_cost += 4.0 * prior_claims_count  # cross-referencing overhead — always on, real.
    fraud_loss = (
        max(0.0, rng.gauss(fraud_loss_delta, 15 + 0.1 * fraud_loss_delta)) if fraud_flagged else 0.0
    )
    net_claim_cost = payout_amount + processing_cost + fraud_loss
    reopen_probability = _sigmoid(
        -1.4 + 0.9 * fraud_flagged + 0.0006 * max(0, net_claim_cost - 500)
    )
    reopened: bool | None = rng.random() < reopen_probability
    if rng.random() < (0.38 if fraud_flagged else 0.08):
        reopened = None
    investigation_date = (
        claim_filed_date + timedelta(days=rng.randint(1, 30)) if fraud_flagged else None
    )

    row: Row = {
        "claim_id": f"INS-{index + 1:05d}",
        "policyholder_id": f"INS-PH-{((index * 2_654_435_761) % 3_200) + 1:04d}",
        "claim_filed_date": claim_filed_date.isoformat(),
        "policy_type": policy_type,
        "claim_type": claim_type,
        "claimed_amount_usd": round(claimed_amount, 2),
        "policy_tenure_months": policy_tenure_months,
        "policyholder_age_band": policyholder_age_band,
        "claim_channel": claim_channel,
        "prior_claims_count": prior_claims_count,
        "adjuster": adjuster,
        "region": region,
        "documentation_complete": documentation_complete,
        "deductible_usd": deductible,
        "filed_within_24h": filed_within_24h,
        "currency": "USD",
        "denied": denied,
        "fraud_flagged": fraud_flagged,
        "payout_amount_usd": round(payout_amount, 2),
        "investigation_opened_date": investigation_date.isoformat() if investigation_date else "",
        "adjuster_notes_count": min(6, int(rng.expovariate(1 / (0.3 + 0.15 * complexity)))),
        "processing_cost_usd": round(processing_cost, 2),
        "fraud_loss_usd": round(fraud_loss, 2),
        "processing_days": max(1, min(90, int(rng.gauss(7 + 2 * complexity, 4)))),
        "net_claim_cost_usd": round(net_claim_cost, 2),
        "reopened_90d": reopened if reopened is not None else "",
        "last_modified_at": (claim_filed_date + timedelta(days=rng.randint(0, 60))).isoformat(),
    }
    return row, patterns


def corruption_ops(config: DomainRunConfig) -> tuple[CorruptionOp, ...]:
    def clear_adjuster(row: Row) -> None:
        row["adjuster"] = ""

    def mixed_date(row: Row) -> None:
        parsed = date.fromisoformat(str(row["claim_filed_date"]))
        row["claim_filed_date"] = parsed.strftime("%d/%m/%Y")

    def currency_symbol(row: Row) -> None:
        row["claimed_amount_usd"] = f"${row['claimed_amount_usd']}"

    def claim_type_upper(row: Row) -> None:
        row["claim_type"] = str(row["claim_type"]).upper()

    def invalid_prior_claims(row: Row) -> None:
        row["prior_claims_count"] = -1

    def invalid_deductible(row: Row) -> None:
        row["deductible_usd"] = -500.0

    def whitespace_adjuster(row: Row) -> None:
        row["adjuster"] = f" {row['adjuster']} "

    return (
        CorruptionOp("missing_adjuster", 18, clear_adjuster),
        CorruptionOp("mixed_date_format", 13, mixed_date),
        CorruptionOp("currency_symbol", 9, currency_symbol),
        CorruptionOp("claim_type_variant", 14, claim_type_upper),
        CorruptionOp("invalid_prior_claims", 3, invalid_prior_claims),
        CorruptionOp("invalid_deductible", 2, invalid_deductible),
        CorruptionOp("whitespace_adjuster", 11, whitespace_adjuster),
        CorruptionOp("duplicate_source_rows", config.dirty_duplicate_rows, lambda row: None),
    )


SPEC = DomainSpec(
    domain_id=DOMAIN_ID,
    schema_version=SCHEMA_VERSION,
    primary_id_column="claim_id",
    clustering_key="policyholder_id",
    decision_timestamp_column="claim_filed_date",
    outcome_columns=OUTCOME_COLUMNS,
    primary_outcome_column="net_claim_cost_usd",
    feature_timing=FEATURE_TIMING,
    declared_types=DECLARED_TYPES,
    patterns=PATTERNS,
    traps=TRAPS,
    generate_row=generate_row,
    corruption_ops=corruption_ops,
    development_end=DEVELOPMENT_END,
    validation_end=VALIDATION_END,
    future_holdout_end=FUTURE_HOLDOUT_END,
    harm_direction="increase_is_harm",
)
