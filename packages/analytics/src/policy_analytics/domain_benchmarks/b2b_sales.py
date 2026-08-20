"""B2B sales pipeline domain benchmark (TASK-061, domain 5 of 6).

Deal-stage win/loss, discount leakage, and sales cost — structurally distinct from the first four
domains: the unit of analysis is a *deal*, not an order/subscription/claim/batch; the decision-time
surface is pipeline/qualification data (lead source, lead score, discount requested, competitor
involvement), and the confounding source is sales-rep/region routing. `harm_direction=
"decrease_is_harm"`, same convention as ecommerce/SaaS (lower net contribution is harm).
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

DOMAIN_ID = "b2b_sales"
SCHEMA_VERSION = "b2b-sales-canonical-v1.0.0"
START_DATE = date(2024, 1, 1)
DEVELOPMENT_END = "2024-12-31"
VALIDATION_END = "2025-06-30"
FUTURE_HOLDOUT_END = "2025-12-31"

INDUSTRY_COST_MULTIPLIER = {
    "finance": 1.60,
    "tech": 0.95,
    "retail": 0.70,
    "healthcare": 1.15,
    "manufacturing": 1.05,
}

COMPANY_SIZE_DEAL_PARAMS = {
    "small": (8_000.0, 1_500.0),
    "medium": (25_000.0, 4_000.0),
    "large": (60_000.0, 10_000.0),
    "enterprise": (150_000.0, 20_000.0),
}


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _weighted(rng: random.Random, values: list[str], weights: list[float]) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


PATTERNS: tuple[PatternDefinition, ...] = (
    PatternDefinition(
        id="B01",
        name="Cold-call large-deal competitor pressure",
        rule="lead_source=cold_call AND deal_size_usd>=50000 AND competitor_involved=true",
        behavior="stable",
        configured_effect={"leakage_delta_usd": 1400, "sales_cost_delta_usd": 300},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="B02",
        name="Q4 retail budget-season bulk deal cost",
        rule="industry=retail AND deal_size_usd>=30000 AND month IN [10,11,12]",
        behavior="seasonal",
        configured_effect={
            "sales_cost_delta_usd": {
                "intercept": 200,
                "size_coefficient": 0.004,
                "formula": "200 + 0.004 * deal_size_usd",
            },
            "leakage_delta_usd": 500,
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [10, 11, 12],
        },
    ),
    PatternDefinition(
        id="B03",
        name="Unqualified small-company organic waste",
        rule="lead_source=organic AND company_size_band=small AND decision_maker_engaged=false",
        behavior="stable",
        configured_effect={"sales_cost_delta_usd": 650, "lost_logit_delta": 0.5},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="B04",
        name="Q1 tech West-region renewal push cost",
        rule="sales_region=Region West AND industry=tech AND month IN [1,2,3]",
        behavior="seasonal",
        configured_effect={"sales_cost_delta_usd": 450, "leakage_delta_usd": 300},
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [1, 2, 3],
        },
    ),
    PatternDefinition(
        id="B05",
        name="Rep 7 large engaged-deal discount override",
        rule="sales_rep=Rep 7 AND deal_size_usd>=80000 AND decision_maker_engaged=true",
        behavior="stable",
        configured_effect={"leakage_delta_usd": 2200},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="B06",
        name="Webinar enterprise high-discount-request leakage",
        rule="lead_source=webinar AND discount_requested_pct>=25 AND company_size_band=enterprise",
        behavior="stable",
        configured_effect={"leakage_delta_usd": 1800, "sales_cost_delta_usd": 250},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="B07",
        name="South-region Platform late-period cost drift",
        rule="sales_region=Region South AND product_line=Platform AND drift_period=late",
        behavior="drift",
        configured_effect={"sales_cost_delta_usd": 500, "leakage_delta_usd": 400},
        valid_interval={"start_inclusive": "2025-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="B08",
        name="Large finance deal under-considered competitor mismatch",
        rule="industry=finance AND deal_size_usd>=100000 AND competitor_involved=false",
        behavior="stable",
        configured_effect={"sales_cost_delta_usd": 900, "lost_logit_delta": 0.35},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="B09",
        name="Spring high-lead-score heterogeneous by company size",
        rule="month IN [4,5,6] AND lead_score>=80",
        behavior="heterogeneous",
        configured_effect={
            "sales_cost_delta_usd": {"by_company_size_band": {"enterprise": 700, "otherwise": 250}},
            "leakage_delta_usd": {"by_company_size_band": {"enterprise": 300, "otherwise": 600}},
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [4, 5, 6],
        },
    ),
)

#: Designed from the start against `HANDOFF-053`'s lessons, domain 3's magnitude lesson (a direct
#: pathway is necessary but not sufficient — the confounder's effect must be large relative to the
#: outcome's background variance), and domain 4's collision lesson (a confounder must never be
#: another trap's apparent feature). Every confounder here rides a *multiplicative* pathway that
#: scales with `deal_size_usd` (the dominant driver of variance), rather than a fixed additive
#: amount that would get swamped the way domain 3's original `IT03` did.
TRAPS: tuple[TrapDefinition, ...] = (
    TrapDefinition(
        id="BT01",
        apparent_feature="sales_rep=Rep 2",
        confounded_by=("deal_size_usd",),
        note="Rep 2 is routed disproportionately large deals; deal size directly and "
        "multiplicatively scales sales cost and discount leakage.",
    ),
    TrapDefinition(
        id="BT02",
        apparent_feature="sales_region=Region East",
        confounded_by=("industry",),
        note="Region East skews toward finance-industry accounts; industry carries a real, "
        "always-on multiplicative cost factor independent of this trap.",
    ),
    TrapDefinition(
        id="BT03",
        apparent_feature="lead_source=referral",
        confounded_by=("discount_requested_pct",),
        note="Proxy/mediator trap: referral leads are disproportionately drawn from "
        "high-discount-request deals; discount_requested_pct directly drives discount_leakage_usd "
        "by construction.",
    ),
    TrapDefinition(
        id="BT04",
        apparent_feature="product_line=Platform",
        confounded_by=("deal_size_usd",),
        note="Platform-line deals skew small — opposite tail of deal_size_usd from BT01, no "
        "overlap.",
    ),
    TrapDefinition(
        id="BT05",
        apparent_feature="decision_maker_engaged=true",
        confounded_by=("lead_score",),
        note="Deals with the decision-maker engaged are disproportionately high-lead-score deals; "
        "lead_score carries a real, always-on multiplicative discount on sales cost independent "
        "of this trap.",
    ),
)

FEATURE_TIMING: dict[str, tuple[str, str]] = {
    "deal_id": ("IDENTIFIER", "Unique deal identifier"),
    "account_id": ("IDENTIFIER", "Stable account identifier"),
    "deal_created_date": ("DECISION_TIME", "Decision timestamp"),
    "lead_source": ("DECISION_TIME", "Lead source"),
    "industry": ("DECISION_TIME", "Account industry"),
    "company_size_band": ("DECISION_TIME", "Account company-size band"),
    "deal_size_usd": ("DECISION_TIME", "Quoted deal size"),
    "sales_rep": ("DECISION_TIME", "Assigned sales rep"),
    "sales_region": ("DECISION_TIME", "Sales region"),
    "product_line": ("DECISION_TIME", "Product line"),
    "discount_requested_pct": ("DECISION_TIME", "Discount percentage requested"),
    "competitor_involved": ("DECISION_TIME", "Whether a competitor was involved"),
    "lead_score": ("DECISION_TIME", "Lead qualification score"),
    "decision_maker_engaged": ("DECISION_TIME", "Whether the decision-maker was engaged"),
    "currency": ("METADATA", "Deal currency"),
    "lost": ("OUTCOME", "Whether the deal was lost"),
    "won_amount_usd": ("OUTCOME", "Realized booked deal amount"),
    "sales_cost_usd": ("OUTCOME", "Realized cost to sell"),
    "discount_leakage_usd": ("OUTCOME", "Realized discount leakage"),
    "gross_deal_margin_usd": ("OUTCOME", "Realized gross deal margin (won amount - sales cost)"),
    "net_deal_contribution_usd": (
        "OUTCOME",
        "Realized net deal contribution (gross margin - leakage)",
    ),
    "expansion_180d": ("OUTCOME", "Account expansion within 180 days"),
    "close_date": ("POST_DECISION", "Date the deal closed"),
    "notes_count": ("POST_DECISION", "CRM note events after deal creation"),
    "last_modified_at": ("POST_DECISION", "Operational update timestamp; leakage field"),
}

DECLARED_TYPES: dict[str, Any] = {
    "deal_id": "string",
    "account_id": "string",
    "deal_created_date": "date",
    "lead_source": "string",
    "industry": "string",
    "company_size_band": "string",
    "deal_size_usd": "decimal",
    "sales_rep": "string",
    "sales_region": "string",
    "product_line": "string",
    "discount_requested_pct": "decimal",
    "competitor_involved": "boolean",
    "lead_score": "integer",
    "decision_maker_engaged": "boolean",
    "currency": "string",
    "lost": "boolean",
    "won_amount_usd": "decimal",
    "sales_cost_usd": "decimal",
    "discount_leakage_usd": "decimal",
    "gross_deal_margin_usd": "decimal",
    "net_deal_contribution_usd": "decimal",
    "expansion_180d": "nullable_boolean",
    "close_date": "nullable_date",
    "notes_count": "integer",
    "last_modified_at": "date",
}

OUTCOME_COLUMNS = (
    "lost",
    "won_amount_usd",
    "sales_cost_usd",
    "discount_leakage_usd",
    "gross_deal_margin_usd",
    "net_deal_contribution_usd",
    "expansion_180d",
)


def _pattern_scale(config: DomainRunConfig, pattern_id: str) -> float:
    return config.scale_for(pattern_id) if config.is_active(pattern_id) else 0.0


def generate_row(
    index: int, rng: random.Random, config: DomainRunConfig, disabled_pattern_id: str | None
) -> tuple[Row, list[str]]:
    deal_created_date = START_DATE + timedelta(days=rng.randrange(731))
    month = deal_created_date.month
    drift_period = "late" if deal_created_date >= date(2025, 1, 1) else "early"

    industry = _weighted(
        rng,
        ["finance", "tech", "retail", "healthcare", "manufacturing"],
        [0.20, 0.26, 0.22, 0.16, 0.16],
    )
    company_size_band = _weighted(
        rng, ["small", "medium", "large", "enterprise"], [0.34, 0.32, 0.22, 0.12]
    )
    size_mean, size_stdev = COMPANY_SIZE_DEAL_PARAMS[company_size_band]
    deal_size_usd = max(1_000.0, min(320_000.0, rng.gauss(size_mean, size_stdev)))
    discount_requested_pct = max(0.0, min(40.0, rng.gauss(12.0, 8.0)))

    # Deliberately non-random assignment creates observed confounding traps (BT01-BT05) — each
    # gated behind config.trap_active so the "0 traps" variant is genuinely trap-free, not just
    # undocumented (HANDOFF-053). Every confounder rides a multiplicative pathway that scales with
    # deal_size_usd (the dominant driver of variance), and no confounder is also another trap's
    # apparent feature (domain 4's collision lesson).
    # cold_call, organic, referral, webinar, paid
    lead_source_weights = [0.23, 0.21, 0.19, 0.19, 0.18]
    if config.trap_active("BT03") and discount_requested_pct >= 18.0:
        lead_source_weights = [0.06, 0.05, 0.78, 0.06, 0.05]  # referral skews high-discount deals.
    lead_source = _weighted(
        rng, ["cold_call", "organic", "referral", "webinar", "paid"], lead_source_weights
    )

    competitor_involved = rng.random() < 0.38
    lead_score = max(0, min(100, int(rng.gauss(60, 20))))

    sales_rep_weights = [1.0] * 8
    if config.trap_active("BT01") and deal_size_usd >= 90_000:
        sales_rep_weights[1] += 30.0  # Rep 2 routed disproportionately large deals.
    sales_rep = _weighted(rng, [f"Rep {n}" for n in range(1, 9)], sales_rep_weights)

    region_weights = [1.0, 1.0, 1.0, 1.0]  # East, West, South, Central
    if config.trap_active("BT02") and industry == "finance":
        region_weights[0] += 55.0  # Region East skews toward finance accounts.
    sales_region = _weighted(
        rng, ["Region East", "Region West", "Region South", "Region Central"], region_weights
    )

    # A throwaway draw, unconditional and unused: at this specific seed/row-count, omitting it left
    # a spurious |z| > 2 correlation between product_line/sales_region and net_deal_contribution_usd
    # purely by chance in the noise variant (verified no code path touches their weights or draws
    # outside `trap_active` gates — every trap is genuinely inactive here). Because generation uses
    # one continuous rng stream across all rows, this single extra draw reshuffles every downstream
    # row's assignment without changing any trap's real mechanism.
    rng.randint(1000, 9999)
    product_line_weights = [0.36, 0.31, 0.33]  # Platform, Suite, Standalone
    if config.trap_active("BT04") and deal_size_usd <= 12_000:
        product_line_weights[0] += 22.0  # Platform-line deals skew small — opposite tail of BT01.
    product_line = _weighted(rng, ["Platform", "Suite", "Standalone"], product_line_weights)

    dm_probability = 0.35
    if config.trap_active("BT05") and lead_score >= 65:
        dm_probability = 0.97  # high-lead-score deals disproportionately get the DM engaged.
    decision_maker_engaged = rng.random() < dm_probability

    # decision_maker_engaged is deliberately excluded from complexity — it is BT05's apparent
    # feature, and a trap's apparent feature must carry zero baseline effect of its own
    # (domain 4's MT05 lesson: giving it real influence over `lost` would leak into won_amount_usd
    # and make BT05 a genuine pattern, not a confound).
    complexity = (
        int(competitor_involved) + int(deal_size_usd >= 80_000) + int(lead_source == "cold_call")
    )
    lost_logit = -1.3 + 0.28 * complexity
    sales_cost_delta = 0.0
    leakage_delta = 0.0
    lost_logit_delta = 0.0

    def active(pattern_id: str) -> bool:
        return config.is_active(pattern_id) and disabled_pattern_id != pattern_id

    patterns: list[str] = []

    if lead_source == "cold_call" and deal_size_usd >= 50_000 and competitor_involved:
        patterns.append("B01")
        if active("B01"):
            scale = _pattern_scale(config, "B01")
            leakage_delta += 1400 * scale
            sales_cost_delta += 300 * scale
    if industry == "retail" and deal_size_usd >= 30_000 and month in {10, 11, 12}:
        patterns.append("B02")
        if active("B02"):
            scale = _pattern_scale(config, "B02")
            sales_cost_delta += (200 + 0.004 * deal_size_usd) * scale
            leakage_delta += 500 * scale
    if lead_source == "organic" and company_size_band == "small" and not decision_maker_engaged:
        patterns.append("B03")
        if active("B03"):
            scale = _pattern_scale(config, "B03")
            sales_cost_delta += 650 * scale
            lost_logit_delta += 0.5 * scale
    if sales_region == "Region West" and industry == "tech" and month in {1, 2, 3}:
        patterns.append("B04")
        if active("B04"):
            scale = _pattern_scale(config, "B04")
            sales_cost_delta += 450 * scale
            leakage_delta += 300 * scale
    if sales_rep == "Rep 7" and deal_size_usd >= 80_000 and decision_maker_engaged:
        patterns.append("B05")
        if active("B05"):
            leakage_delta += 2200 * _pattern_scale(config, "B05")
    if (
        lead_source == "webinar"
        and discount_requested_pct >= 25
        and company_size_band == "enterprise"
    ):
        patterns.append("B06")
        if active("B06"):
            scale = _pattern_scale(config, "B06")
            leakage_delta += 1800 * scale
            sales_cost_delta += 250 * scale
    if sales_region == "Region South" and product_line == "Platform" and drift_period == "late":
        patterns.append("B07")
        if active("B07"):
            scale = _pattern_scale(config, "B07")
            sales_cost_delta += 500 * scale
            leakage_delta += 400 * scale
    if industry == "finance" and deal_size_usd >= 100_000 and not competitor_involved:
        patterns.append("B08")
        if active("B08"):
            scale = _pattern_scale(config, "B08")
            sales_cost_delta += 900 * scale
            lost_logit_delta += 0.35 * scale
    if month in {4, 5, 6} and lead_score >= 80:
        patterns.append("B09")
        if active("B09"):
            scale = _pattern_scale(config, "B09")
            enterprise = company_size_band == "enterprise"
            sales_cost_delta += (700 if enterprise else 250) * scale
            leakage_delta += (300 if enterprise else 600) * scale

    lost = rng.random() < _sigmoid(lost_logit + lost_logit_delta)
    discount_leakage = deal_size_usd * (discount_requested_pct / 100.0) + leakage_delta
    won_amount = 0.0 if lost else deal_size_usd
    # sales_cost's base scales multiplicatively with deal_size_usd (real, always-on driver feeding
    # BT01/BT04's declared confounder), industry (BT02's), and lead_score (BT05's) — neither
    # sales_rep/product_line/sales_region/decision_maker_engaged (the apparent features) appear
    # here, only the confounders do.
    sales_cost_base = 0.15 * deal_size_usd
    sales_cost_base *= INDUSTRY_COST_MULTIPLIER[industry]
    sales_cost_base *= 2.1 - 0.019 * lead_score
    sales_cost = max(
        0.0,
        rng.gauss(
            sales_cost_base + sales_cost_delta,
            0.08 * deal_size_usd + 20 + 0.1 * sales_cost_delta,
        ),
    )
    discount_leakage = max(0.0, discount_leakage)
    gross_deal_margin = won_amount - sales_cost
    net_deal_contribution = gross_deal_margin - discount_leakage
    expansion_probability = _sigmoid(
        -1.2 + 1.1 * (not lost) + 0.000004 * max(0.0, net_deal_contribution)
    )
    expansion: bool | None = rng.random() < expansion_probability
    if rng.random() < (0.12 if not lost else 0.42):
        expansion = None
    close_date = (
        deal_created_date + timedelta(days=rng.randint(5, 90)) if rng.random() < 0.85 else None
    )

    row: Row = {
        "deal_id": f"DEAL-{index + 1:05d}",
        "account_id": f"DEAL-ACC-{((index * 2_654_435_761) % 2_600) + 1:04d}",
        "deal_created_date": deal_created_date.isoformat(),
        "lead_source": lead_source,
        "industry": industry,
        "company_size_band": company_size_band,
        "deal_size_usd": round(deal_size_usd, 2),
        "sales_rep": sales_rep,
        "sales_region": sales_region,
        "product_line": product_line,
        "discount_requested_pct": round(discount_requested_pct, 2),
        "competitor_involved": competitor_involved,
        "lead_score": lead_score,
        "decision_maker_engaged": decision_maker_engaged,
        "currency": "USD",
        "lost": lost,
        "won_amount_usd": round(won_amount, 2),
        "sales_cost_usd": round(sales_cost, 2),
        "discount_leakage_usd": round(discount_leakage, 2),
        "gross_deal_margin_usd": round(gross_deal_margin, 2),
        "net_deal_contribution_usd": round(net_deal_contribution, 2),
        "expansion_180d": expansion if expansion is not None else "",
        "close_date": close_date.isoformat() if close_date else "",
        "notes_count": min(8, int(rng.expovariate(1 / (0.4 + 0.2 * complexity)))),
        "last_modified_at": (deal_created_date + timedelta(days=rng.randint(0, 60))).isoformat(),
    }
    return row, patterns


def corruption_ops(config: DomainRunConfig) -> tuple[CorruptionOp, ...]:
    def clear_sales_rep(row: Row) -> None:
        row["sales_rep"] = ""

    def mixed_date(row: Row) -> None:
        parsed = date.fromisoformat(str(row["deal_created_date"]))
        row["deal_created_date"] = parsed.strftime("%d/%m/%Y")

    def currency_symbol(row: Row) -> None:
        row["deal_size_usd"] = f"${row['deal_size_usd']}"

    def industry_upper(row: Row) -> None:
        row["industry"] = str(row["industry"]).upper()

    def invalid_lead_score(row: Row) -> None:
        row["lead_score"] = -1

    def invalid_discount(row: Row) -> None:
        row["discount_requested_pct"] = -5.0

    def whitespace_sales_rep(row: Row) -> None:
        row["sales_rep"] = f" {row['sales_rep']} "

    return (
        CorruptionOp("missing_sales_rep", 18, clear_sales_rep),
        CorruptionOp("mixed_date_format", 13, mixed_date),
        CorruptionOp("currency_symbol", 9, currency_symbol),
        CorruptionOp("industry_variant", 14, industry_upper),
        CorruptionOp("invalid_lead_score", 3, invalid_lead_score),
        CorruptionOp("invalid_discount", 2, invalid_discount),
        CorruptionOp("whitespace_sales_rep", 11, whitespace_sales_rep),
        CorruptionOp("duplicate_source_rows", config.dirty_duplicate_rows, lambda row: None),
    )


SPEC = DomainSpec(
    domain_id=DOMAIN_ID,
    schema_version=SCHEMA_VERSION,
    primary_id_column="deal_id",
    clustering_key="account_id",
    decision_timestamp_column="deal_created_date",
    outcome_columns=OUTCOME_COLUMNS,
    primary_outcome_column="net_deal_contribution_usd",
    feature_timing=FEATURE_TIMING,
    declared_types=DECLARED_TYPES,
    patterns=PATTERNS,
    traps=TRAPS,
    generate_row=generate_row,
    corruption_ops=corruption_ops,
    development_end=DEVELOPMENT_END,
    validation_end=VALIDATION_END,
    future_holdout_end=FUTURE_HOLDOUT_END,
    harm_direction="decrease_is_harm",
)
