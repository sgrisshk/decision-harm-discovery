"""E-commerce/retail domain benchmark (TASK-061, domain 1 of 6).

Orders, returns, discounts, and warehouse fulfillment — structurally distinct from the travel
booking domain: different decision-time attribute set (cart/checkout mechanics, warehouse/
fulfillment-agent routing, coupon/BNPL risk), different outcome decomposition (returns/restocking/
refund-processing cost rather than cancellation/support-case cost), different confounding sources.
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

DOMAIN_ID = "ecommerce"
SCHEMA_VERSION = "ecommerce-canonical-v1.0.0"
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
        id="E01",
        name="WH2 high-discount BNPL",
        rule="warehouse_id=WH2 AND discount_pct>=0.35 AND payment_method=buy_now_pay_later",
        behavior="stable",
        configured_effect={
            "restocking_cost_delta_usd": 32,
            "return_logit_delta": 1.0,
            "support_ticket_rate_delta": 0.6,
        },
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="E02",
        name="Holiday apparel bulk buying",
        rule="product_category=apparel AND quantity>=5 AND discount_pct>=0.30 AND month IN [11,12]",
        behavior="seasonal",
        configured_effect={
            "restocking_cost_delta_usd": {
                "intercept": 40,
                "quantity_coefficient": 4,
                "formula": "40 + 4 * quantity",
            },
            "support_ticket_rate_delta": 0.8,
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [11, 12],
        },
    ),
    PatternDefinition(
        id="E03",
        name="BNPL new-customer paid-search risk",
        rule="payment_method=buy_now_pay_later AND customer_segment=new "
        "AND acquisition_channel=paid_search",
        behavior="stable",
        configured_effect={"restocking_cost_delta_usd": 18, "return_logit_delta": 0.68},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="E04",
        name="WH1 winter heavy electronics",
        rule="warehouse_id=WH1 AND product_category=electronics AND items_in_cart>=4 "
        "AND month IN [12,1,2]",
        behavior="seasonal",
        configured_effect={"restocking_cost_delta_usd": 28, "support_ticket_rate_delta": 0.5},
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [12, 1, 2],
        },
    ),
    PatternDefinition(
        id="E05",
        name="Agent 4 coupon price override",
        rule="fulfillment_agent=Agent 4 AND coupon_used=true AND product_price_usd>=250",
        behavior="stable",
        configured_effect={"restocking_cost_delta_usd": 36},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="E06",
        name="Mobile next-day gift-card checkout errors",
        rule="device_type=mobile AND shipping_method=next_day AND payment_method=gift_card",
        behavior="stable",
        configured_effect={"restocking_cost_delta_usd": 22, "return_logit_delta": 0.95},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="E07",
        name="WH3 late-period affiliate returning drift",
        rule="warehouse_id=WH3 AND acquisition_channel=affiliate AND customer_segment=returning "
        "AND drift_period=late",
        behavior="drift",
        configured_effect={"restocking_cost_delta_usd": 26, "support_ticket_rate_delta": 0.35},
        valid_interval={"start_inclusive": "2025-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="E08",
        name="Luxury single-item long-consideration mismatch",
        rule="product_tier=luxury AND items_in_cart=1 AND days_since_last_visit>=45",
        behavior="stable",
        configured_effect={"restocking_cost_delta_usd": 33, "support_ticket_rate_delta": 0.7},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="E09",
        name="WH4 Q4 bulk heterogeneous by segment",
        rule="warehouse_id=WH4 AND month IN [9,10,11] AND items_in_cart>=4",
        behavior="heterogeneous",
        configured_effect={
            "restocking_cost_delta_usd": {"by_customer_segment": {"vip": 45, "otherwise": 17}},
            "return_logit_delta": {"by_customer_segment": {"vip": 0.6, "otherwise": 0.2}},
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [9, 10, 11],
        },
    ),
)

#: Corrected 2026-08-20 (`HANDOFF-053`) against a direct empirical audit — raw marginal
#: `net_contribution_usd` differences recomputed on the `traps_only`/`noise` variants (patterns
#: off, so no active-pattern signal can leak into the measurement) after gating every mechanism
#: below behind `config.trap_active(...)`. Every `confounded_by` entry here is now independently
#: verified wired in `generate_row`, not merely narratively plausible — see
#: `tests/analytics/test_domain_benchmarks.py`'s live-trap and noise-is-clean checks, which verify
#: this mechanically for every registered domain from now on, not just this one.
TRAPS: tuple[TrapDefinition, ...] = (
    TrapDefinition(
        id="ET01",
        apparent_feature="fulfillment_agent=Agent 2",
        confounded_by=("product_category", "items_in_cart"),
    ),
    TrapDefinition(
        id="ET02",
        apparent_feature="warehouse_id=WH1",
        confounded_by=("product_category", "order_month"),
        note=(
            "order_month's WH1 boost is a genuine summer (Jun-Aug) effect, deliberately disjoint "
            "from pattern E04's winter [12,1,2] window."
        ),
    ),
    TrapDefinition(
        id="ET03",
        apparent_feature="acquisition_channel=paid_search",
        confounded_by=("discount_pct",),
        note=(
            "A proxy/mediator trap, not a pure non-causal assignment artifact like ET01/ET02/"
            "ET04: acquisition_channel has zero direct effect of its own, but it does causally "
            "shift discount_pct (a real, independently-discoverable DECISION_TIME feature), "
            "which then genuinely reduces margin. Tests whether a candidate condition correctly "
            "attributes the effect to discount_pct rather than to the correlated channel proxy."
        ),
    ),
    TrapDefinition(
        id="ET04",
        apparent_feature="payment_method=gift_card",
        confounded_by=("product_tier",),
        note=(
            "Gift-card usage skews toward premium/luxury tier (upsell/gifting behavior). "
            "Deliberately independent of pattern E06's device_type=mobile trigger — the earlier "
            "device-linked wiring this trap was audited against created partial overlap with "
            "E06's real effect; product_tier does not appear in any pattern's condition."
        ),
    ),
    TrapDefinition(
        id="ET05",
        apparent_feature="coupon_used=true",
        confounded_by=("quantity",),
        note=(
            "E05 is a genuine interaction; the main effect is a trap. The live mechanism is "
            "quantity<=1, chosen because it affects gross_revenue/base_cost/payment_fee "
            "directly rather than through the same weak, multi-step complexity->Bernoulli path "
            "ET01 relies on — an earlier version tried a customer_segment/items_in_cart pathway "
            "here and it was real but too faint to detect reliably. Independent of ET03's "
            "discount_pct pathway — the two traps are independently toggleable, not two labels "
            "on one shared code path — and disjoint from pattern E02's quantity>=5 trigger."
        ),
    ),
)

FEATURE_TIMING: dict[str, tuple[str, str]] = {
    "order_id": ("IDENTIFIER", "Unique order identifier"),
    "customer_id": ("IDENTIFIER", "Stable customer identifier"),
    "order_date": ("DECISION_TIME", "Decision timestamp"),
    "product_category": ("DECISION_TIME", "Product department"),
    "product_tier": ("DECISION_TIME", "Product tier (standard/premium/luxury)"),
    "product_price_usd": ("DECISION_TIME", "Quoted unit price"),
    "quantity": ("DECISION_TIME", "Units ordered"),
    "items_in_cart": ("DECISION_TIME", "Distinct line items in cart at checkout"),
    "discount_pct": ("DECISION_TIME", "Discount applied at checkout"),
    "payment_method": ("DECISION_TIME", "Chosen payment method"),
    "shipping_method": ("DECISION_TIME", "Chosen shipping method"),
    "customer_segment": ("DECISION_TIME", "Customer segment at order time"),
    "acquisition_channel": ("DECISION_TIME", "Acquisition source"),
    "device_type": ("DECISION_TIME", "Checkout device"),
    "warehouse_id": ("DECISION_TIME", "Fulfilling warehouse selected at order time"),
    "fulfillment_agent": ("DECISION_TIME", "Order owner/fulfillment agent"),
    "coupon_used": ("DECISION_TIME", "Coupon code applied"),
    "days_since_last_visit": ("DECISION_TIME", "Days since the customer's last site visit"),
    "currency": ("METADATA", "Source currency"),
    "returned": ("OUTCOME", "Return observed after order"),
    "return_amount_usd": ("OUTCOME", "Realized return amount"),
    "return_date": ("POST_DECISION", "Date a return occurred"),
    "delivery_delay_days": ("POST_DECISION", "Delivery delay after initial dispatch"),
    "support_tickets": ("POST_DECISION", "Support interactions after order"),
    "refund_processing_cost_usd": ("OUTCOME", "Realized refund-processing cost"),
    "restocking_cost_usd": ("OUTCOME", "Realized unplanned restocking cost"),
    "gross_margin_usd": ("OUTCOME", "Realized gross margin"),
    "net_contribution_usd": ("OUTCOME", "Realized contribution after downstream costs"),
    "repeat_purchase_90d": ("OUTCOME", "Repeat purchase within outcome window"),
    "last_modified_at": ("POST_DECISION", "Operational update timestamp; leakage field"),
}

DECLARED_TYPES: dict[str, Any] = {
    "order_id": "string",
    "customer_id": "string",
    "order_date": "date",
    "product_category": "string",
    "product_tier": "string",
    "product_price_usd": "decimal",
    "quantity": "integer",
    "items_in_cart": "integer",
    "discount_pct": "decimal",
    "payment_method": "string",
    "shipping_method": "string",
    "customer_segment": "string",
    "acquisition_channel": "string",
    "device_type": "string",
    "warehouse_id": "string",
    "fulfillment_agent": "string",
    "coupon_used": "boolean",
    "days_since_last_visit": "integer",
    "currency": "string",
    "returned": "boolean",
    "return_amount_usd": "decimal",
    "return_date": "nullable_date",
    "delivery_delay_days": "integer",
    "support_tickets": "integer",
    "refund_processing_cost_usd": "decimal",
    "restocking_cost_usd": "decimal",
    "gross_margin_usd": "decimal",
    "net_contribution_usd": "decimal",
    "repeat_purchase_90d": "nullable_boolean",
    "last_modified_at": "date",
}

OUTCOME_COLUMNS = (
    "returned",
    "return_amount_usd",
    "refund_processing_cost_usd",
    "restocking_cost_usd",
    "gross_margin_usd",
    "net_contribution_usd",
    "repeat_purchase_90d",
)


def _pattern_scale(config: DomainRunConfig, pattern_id: str) -> float:
    return config.scale_for(pattern_id) if config.is_active(pattern_id) else 0.0


def generate_row(
    index: int, rng: random.Random, config: DomainRunConfig, disabled_pattern_id: str | None
) -> tuple[Row, list[str]]:
    order_date = START_DATE + timedelta(days=rng.randrange(731))
    month = order_date.month
    drift_period = "late" if order_date >= date(2025, 1, 1) else "early"

    customer_segment = _weighted(rng, ["new", "returning", "vip"], [0.55, 0.32, 0.13])
    acquisition_channel = _weighted(
        rng,
        ["organic", "paid_search", "email", "social", "affiliate"],
        [0.28, 0.27, 0.17, 0.18, 0.10],
    )
    device_type = _weighted(rng, ["mobile", "desktop", "tablet"], [0.55, 0.35, 0.10])

    category_weights = [0.24, 0.22, 0.20, 0.19, 0.15]
    if month in {11, 12}:
        category_weights = [0.30, 0.30, 0.15, 0.13, 0.12]
    product_category = _weighted(
        rng,
        ["electronics", "apparel", "home_goods", "beauty", "toys"],
        category_weights,
    )
    product_tier = _weighted(rng, ["standard", "premium", "luxury"], [0.62, 0.29, 0.09])

    items_in_cart = rng.randint(1, 3) if customer_segment == "new" else rng.randint(1, 6)
    quantity = max(1, min(20, int(rng.gauss(3 if product_category == "apparel" else 2, 2))))
    days_since_last_visit = max(0, min(180, int(rng.gauss(20, 25))))

    # Deliberately non-random assignment creates observed confounding traps (ET01/ET02) — each
    # gated behind config.trap_active so the "0 traps" variant is genuinely trap-free, not just
    # undocumented (HANDOFF-053). fulfillment_agent/warehouse_id themselves have zero baseline
    # effect on any outcome elsewhere in this function (verified: neither name appears in the
    # complexity/cost formulas below) — only the real confounders (product_category,
    # items_in_cart, order_month) do the work, matching direct_effect: 0.
    agent_weights = [1.0] * 8
    if config.trap_active("ET01") and (
        product_category in {"electronics", "home_goods"} or items_in_cart >= 5
    ):
        agent_weights[1] += 16.0  # Agent 2 receives intrinsically difficult orders. Strong enough
        # that the confound is empirically detectable through complexity's genuinely weak,
        # multi-step path to margin (complexity -> return/support Bernoulli-ish draws -> a small
        # dollar effect) — verified at |z| > 3 on a 10,000-row sample, not just plausible on paper.
    fulfillment_agent = _weighted(rng, [f"Agent {number}" for number in range(1, 9)], agent_weights)
    warehouse_weights = [1.0, 1.0, 1.0, 1.0]
    if config.trap_active("ET02"):
        if product_category in {"electronics", "home_goods"}:
            warehouse_weights[0] += 3.5  # WH1 handles heavy/bulky categories.
        if month in {6, 7, 8}:
            warehouse_weights[0] += 1.2  # WH1 also absorbs summer volume — genuinely wired to
            # WH1 (index 0), unlike the pre-fix version, which boosted WH4 (index 3) here while
            # claiming to confound WH1 (HANDOFF-053). Summer is deliberately disjoint from E04's
            # winter [12,1,2] window, so this never dilutes E04's real population.
    if month in {11, 12}:
        warehouse_weights[3] += 1.5  # WH4 Q4 volume — baseline realism feeding E09, not a
        # declared trap; E09's own pattern effect is what's being tested there, not confounding.
    warehouse_id = _weighted(rng, ["WH1", "WH2", "WH3", "WH4"], warehouse_weights)

    tier_multiplier = {"standard": 1.0, "premium": 1.65, "luxury": 2.8}[product_tier]
    category_multiplier = {
        "electronics": 1.4,
        "apparel": 0.7,
        "home_goods": 1.1,
        "beauty": 0.55,
        "toys": 0.6,
    }[product_category]
    product_price = max(8.0, rng.gauss(60, 22) * tier_multiplier * category_multiplier)

    # ET03: acquisition_channel=paid_search's raw correlation with margin runs entirely through
    # discount_pct (a real, DECISION_TIME, independently-discoverable feature) — a proxy/mediator
    # trap, not a pure non-causal assignment artifact like ET01/ET02/ET04. Gated separately from
    # ET05 below so the two are independently toggleable, not two labels on one shared code path
    # (the pre-fix bug HANDOFF-053 flagged).
    discount_choices = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
    discount_weights = [0.20, 0.16, 0.20, 0.16, 0.13, 0.09, 0.06]
    if config.trap_active("ET03") and acquisition_channel == "paid_search":
        discount_weights[-2] += 0.10
        discount_weights[-1] += 0.08
    discount_pct = rng.choices(discount_choices, weights=discount_weights, k=1)[0]

    # ET04: gift_card's real (trap-gated) driver is product_tier, not device_type — verified
    # disjoint from pattern E06 (device_type=mobile AND shipping_method=next_day AND
    # payment_method=gift_card): tier never appears in E06's condition, so activating ET04 never
    # inflates E06's exposed population. The mobile-device shift below is unrelated baseline
    # realism (away from card, not toward gift_card) and stays ungated.
    payment_weights = [0.52, 0.24, 0.16, 0.08]  # card, paypal, buy_now_pay_later, gift_card
    if device_type == "mobile":
        payment_weights = [0.40, 0.28, 0.24, 0.08]
    if config.trap_active("ET04") and product_tier != "standard":
        payment_weights[3] += 0.14
    payment_method = _weighted(
        rng, ["card", "paypal", "buy_now_pay_later", "gift_card"], payment_weights
    )
    shipping_method = _weighted(rng, ["standard", "express", "next_day"], [0.62, 0.26, 0.12])

    # ET05: coupon_used is deliberately decoupled from discount_pct entirely (an earlier version
    # tied it to discount_pct>0 as "baseline realism," but that created an always-on mechanical
    # correlation that persisted at full strength even with ET05 inactive, defeating the "0 traps"
    # variant the same way the pre-fix ET01-ET04 mechanisms did). A first replacement driver
    # (customer_segment=="new", via its items_in_cart pathway) was real but too weak to detect
    # reliably — that pathway only reaches the outcome through the same noisy
    # complexity->return/support-Bernoulli chain ET01 relies on, which turned out to have a low
    # ceiling. quantity<=1 instead feeds gross_revenue/base_cost/payment_fee *directly* (no
    # Bernoulli draw in between) — verified at |z| > 3, disjoint from pattern E02's quantity>=5
    # trigger.
    coupon_probability = 0.14
    if config.trap_active("ET05") and quantity <= 1:
        coupon_probability = 0.55
    coupon_used = rng.random() < coupon_probability

    complexity = (
        int(product_category in {"electronics", "home_goods"})
        + int(items_in_cart >= 5)
        + int(product_price >= 150)
        + int(shipping_method == "next_day")
    )
    return_logit = -3.10 + 0.32 * complexity
    support_lambda = 0.14 + 0.09 * complexity
    restocking_delta = 0.0

    def active(pattern_id: str) -> bool:
        return config.is_active(pattern_id) and disabled_pattern_id != pattern_id

    patterns: list[str] = []

    if warehouse_id == "WH2" and discount_pct >= 0.35 and payment_method == "buy_now_pay_later":
        patterns.append("E01")
        if active("E01"):
            scale = _pattern_scale(config, "E01")
            restocking_delta += 32 * scale
            return_logit += 1.0 * scale
            support_lambda += 0.6 * scale
    if (
        product_category == "apparel"
        and quantity >= 5
        and discount_pct >= 0.30
        and month in {11, 12}
    ):
        patterns.append("E02")
        if active("E02"):
            scale = _pattern_scale(config, "E02")
            restocking_delta += (40 + 4 * quantity) * scale
            support_lambda += 0.8 * scale
    if (
        payment_method == "buy_now_pay_later"
        and customer_segment == "new"
        and acquisition_channel == "paid_search"
    ):
        patterns.append("E03")
        if active("E03"):
            scale = _pattern_scale(config, "E03")
            restocking_delta += 18 * scale
            return_logit += 0.68 * scale
    if (
        warehouse_id == "WH1"
        and product_category == "electronics"
        and items_in_cart >= 4
        and month in {12, 1, 2}
    ):
        patterns.append("E04")
        if active("E04"):
            scale = _pattern_scale(config, "E04")
            restocking_delta += 28 * scale
            support_lambda += 0.5 * scale
    if fulfillment_agent == "Agent 4" and coupon_used and product_price >= 250:
        patterns.append("E05")
        if active("E05"):
            restocking_delta += 36 * _pattern_scale(config, "E05")
    if device_type == "mobile" and shipping_method == "next_day" and payment_method == "gift_card":
        patterns.append("E06")
        if active("E06"):
            scale = _pattern_scale(config, "E06")
            restocking_delta += 22 * scale
            return_logit += 0.95 * scale
    if (
        warehouse_id == "WH3"
        and acquisition_channel == "affiliate"
        and customer_segment == "returning"
        and drift_period == "late"
    ):
        patterns.append("E07")
        if active("E07"):
            scale = _pattern_scale(config, "E07")
            restocking_delta += 26 * scale
            support_lambda += 0.35 * scale
    if product_tier == "luxury" and items_in_cart == 1 and days_since_last_visit >= 45:
        patterns.append("E08")
        if active("E08"):
            scale = _pattern_scale(config, "E08")
            restocking_delta += 33 * scale
            support_lambda += 0.7 * scale
    if warehouse_id == "WH4" and month in {9, 10, 11} and items_in_cart >= 4:
        patterns.append("E09")
        if active("E09"):
            scale = _pattern_scale(config, "E09")
            segment_restock = 45 if customer_segment == "vip" else 17
            segment_logit = 0.6 if customer_segment == "vip" else 0.2
            restocking_delta += segment_restock * scale
            return_logit += segment_logit * scale

    returned = rng.random() < _sigmoid(return_logit)
    support_tickets = min(6, int(rng.expovariate(1 / max(support_lambda, 0.01))))
    refund_processing_cost = support_tickets * rng.uniform(6, 18)
    payment_fee = product_price * quantity * (0.018 + 0.006 * max(0, items_in_cart - 4))
    base_cost_ratio = rng.uniform(0.55, 0.68) + 0.01 * complexity
    base_cost = product_price * quantity * base_cost_ratio
    restocking_cost = max(0.0, rng.gauss(6 + restocking_delta, 9 + 0.08 * restocking_delta))
    gross_revenue = product_price * quantity * (1 - discount_pct)
    return_ratio = rng.uniform(0.75, 1.0) if returned else 0.0
    return_amount = gross_revenue * return_ratio
    gross_margin = gross_revenue - base_cost - return_amount
    net_contribution = gross_margin - restocking_cost - refund_processing_cost - payment_fee
    repeat_probability = _sigmoid(-0.6 - 0.85 * returned - 0.0004 * max(0, -net_contribution))
    repeat_purchase: bool | None = rng.random() < repeat_probability
    if rng.random() < (0.42 if returned else 0.06):
        repeat_purchase = None
    return_date = order_date + timedelta(days=rng.randint(2, 45)) if returned else None

    row: Row = {
        "order_id": f"ECM-{index + 1:05d}",
        "customer_id": f"ECM-CUST-{((index * 2_654_435_761) % 3_200) + 1:04d}",
        "order_date": order_date.isoformat(),
        "product_category": product_category,
        "product_tier": product_tier,
        "product_price_usd": round(product_price, 2),
        "quantity": quantity,
        "items_in_cart": items_in_cart,
        "discount_pct": discount_pct,
        "payment_method": payment_method,
        "shipping_method": shipping_method,
        "customer_segment": customer_segment,
        "acquisition_channel": acquisition_channel,
        "device_type": device_type,
        "warehouse_id": warehouse_id,
        "fulfillment_agent": fulfillment_agent,
        "coupon_used": coupon_used,
        "days_since_last_visit": days_since_last_visit,
        "currency": "USD",
        "returned": returned,
        "return_amount_usd": round(return_amount, 2),
        "return_date": return_date.isoformat() if return_date else "",
        "delivery_delay_days": min(5, int(rng.expovariate(1 / (0.2 + 0.12 * complexity)))),
        "support_tickets": support_tickets,
        "refund_processing_cost_usd": round(refund_processing_cost, 2),
        "restocking_cost_usd": round(restocking_cost, 2),
        "gross_margin_usd": round(gross_margin, 2),
        "net_contribution_usd": round(net_contribution, 2),
        "repeat_purchase_90d": repeat_purchase if repeat_purchase is not None else "",
        "last_modified_at": (order_date + timedelta(days=rng.randint(0, 90))).isoformat(),
    }
    return row, patterns


def corruption_ops(config: DomainRunConfig) -> tuple[CorruptionOp, ...]:
    def clear_warehouse(row: Row) -> None:
        row["warehouse_id"] = ""

    def mixed_date(row: Row) -> None:
        parsed = date.fromisoformat(str(row["order_date"]))
        row["order_date"] = parsed.strftime("%d/%m/%Y")

    def currency_symbol(row: Row) -> None:
        row["product_price_usd"] = f"${row['product_price_usd']}"

    def category_upper(row: Row) -> None:
        row["product_category"] = str(row["product_category"]).upper()

    def invalid_items(row: Row) -> None:
        row["items_in_cart"] = -1

    def invalid_discount(row: Row) -> None:
        row["discount_pct"] = 1.4

    def whitespace_agent(row: Row) -> None:
        row["fulfillment_agent"] = f" {row['fulfillment_agent']} "

    return (
        CorruptionOp("missing_warehouse", 18, clear_warehouse),
        CorruptionOp("mixed_date_format", 13, mixed_date),
        CorruptionOp("currency_symbol", 9, currency_symbol),
        CorruptionOp("category_variant", 14, category_upper),
        CorruptionOp("invalid_items_in_cart", 3, invalid_items),
        CorruptionOp("invalid_discount", 2, invalid_discount),
        CorruptionOp("whitespace_agent", 11, whitespace_agent),
        CorruptionOp("duplicate_source_rows", config.dirty_duplicate_rows, lambda row: None),
    )


SPEC = DomainSpec(
    domain_id=DOMAIN_ID,
    schema_version=SCHEMA_VERSION,
    primary_id_column="order_id",
    clustering_key="customer_id",
    decision_timestamp_column="order_date",
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
