"""Manufacturing QA domain benchmark (TASK-061, domain 4 of 6).

Production-batch quality/scrap/downtime cost — structurally distinct from the first three domains:
the unit of analysis is a *batch*, not a customer transaction/account/claim; the decision-time
surface is process/environmental (machine, shift, material grade, humidity/temperature) rather than
customer-facing; and the confounding source is operator/supplier routing rather than
agent/account-owner/adjuster routing. `harm_direction="increase_is_harm"`, same convention as
insurance (higher quality cost is harm).
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

DOMAIN_ID = "manufacturing"
SCHEMA_VERSION = "manufacturing-canonical-v1.0.0"
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
        id="M01",
        name="Rush standard-material large-batch scrap",
        rule="rush_order=true AND batch_size_units>=800 AND material_grade=standard",
        behavior="stable",
        configured_effect={
            "scrap_cost_delta_usd": 140,
            "downtime_cost_delta_usd": 60,
            "defective_logit_delta": 0.5,
        },
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="M02",
        name="Summer humidity Line B defect surge",
        rule="product_line=Line B AND humidity_pct>=65 AND month IN [6,7,8]",
        behavior="seasonal",
        configured_effect={
            "scrap_cost_delta_usd": {
                "intercept": 40,
                "humidity_coefficient": 1.6,
                "formula": "40 + 1.6 * (humidity_pct - 65)",
            },
            "rework_cost_delta_usd": 55,
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [6, 7, 8],
        },
    ),
    PatternDefinition(
        id="M03",
        name="Night short-cycle Machine 3 downtime",
        rule="shift=night AND machine_id=Machine 3 AND planned_cycle_time_min<=25",
        behavior="stable",
        configured_effect={"downtime_cost_delta_usd": 180, "yield_loss_delta_usd": 45},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="M04",
        name="Winter cold-temperature Line D premium defects",
        rule="product_line=Line D AND temperature_c<=8 AND month IN [12,1,2]",
        behavior="seasonal",
        configured_effect={"scrap_cost_delta_usd": 95, "rework_cost_delta_usd": 70},
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [12, 1, 2],
        },
    ),
    PatternDefinition(
        id="M05",
        name="Operator 6 premium large-batch inexperience",
        rule="operator=Operator 6 AND material_grade=premium AND batch_size_units>=800",
        behavior="stable",
        configured_effect={"rework_cost_delta_usd": 165},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="M06",
        name="Rushed night Line C downtime",
        rule="shift=night AND rush_order=true AND product_line=Line C",
        behavior="stable",
        configured_effect={"downtime_cost_delta_usd": 110, "scrap_cost_delta_usd": 50},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="M07",
        name="Premium-grade late-period supplier drift",
        rule="material_grade=premium AND raw_material_supplier=Supplier 4 AND drift_period=late",
        behavior="drift",
        configured_effect={"scrap_cost_delta_usd": 100, "rework_cost_delta_usd": 60},
        valid_interval={"start_inclusive": "2025-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="M08",
        name="Large-batch Supplier 3 grade mismatch",
        rule="batch_size_units>=1200 AND raw_material_supplier=Supplier 3 "
        "AND material_grade=standard",
        behavior="stable",
        configured_effect={"yield_loss_delta_usd": 150, "scrap_cost_delta_usd": 40},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="M09",
        name="Spring high-humidity heterogeneous by product line",
        rule="month IN [3,4,5] AND humidity_pct>=70",
        behavior="heterogeneous",
        configured_effect={
            "scrap_cost_delta_usd": {"by_product_line": {"Line B": 120, "otherwise": 45}},
            "rework_cost_delta_usd": {"by_product_line": {"Line B": 30, "otherwise": 65}},
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [3, 4, 5],
        },
    ),
)

#: Designed from the start against `HANDOFF-053`'s three lessons, plus the magnitude lesson from
#: domain 3's `IT03` (a mathematically direct pathway is necessary but not sufficient — the
#: confounder's own effect on the outcome must be large relative to the outcome's background
#: variance, so every skew below is tuned deliberately hard, not just "plausibly nudged").
TRAPS: tuple[TrapDefinition, ...] = (
    TrapDefinition(
        id="MT01",
        apparent_feature="operator=Operator 2",
        confounded_by=("batch_size_units",),
        note="Operator 2 is routed disproportionately large batches; batch size directly scales "
        "scrap/rework cost through per-unit defect economics.",
    ),
    TrapDefinition(
        id="MT02",
        apparent_feature="raw_material_supplier=Supplier 3",
        confounded_by=("planned_cycle_time_min",),
        note="Supplier 3 batches are disproportionately scheduled on tight, expedited cycle "
        "times; a tight planned cycle time directly raises downtime cost independent of this "
        "trap. (Not material_grade — that is MT05's own apparent feature, and a trap's apparent "
        "feature must carry zero baseline effect of its own, per HANDOFF-053.)",
    ),
    TrapDefinition(
        id="MT03",
        apparent_feature="shift=night",
        confounded_by=("rush_order",),
        note="Proxy/mediator trap: night shift exists largely to absorb rush turnaround demand, "
        "so it correlates with rush_order, which directly raises cost — not a pure non-causal "
        "confound like MT01/MT02/MT04.",
    ),
    TrapDefinition(
        id="MT04",
        apparent_feature="machine_id=Machine 5",
        confounded_by=("batch_size_units",),
        note="Machine 5 runs small quick jobs — opposite tail of batch_size_units from MT01, no "
        "overlap.",
    ),
    TrapDefinition(
        id="MT05",
        apparent_feature="material_grade=premium",
        confounded_by=("humidity_pct",),
        note="Premium-grade lots are disproportionately scheduled during low-humidity windows "
        "(the material is humidity-sensitive to store); humidity_pct itself has a real, "
        "always-on effect on scrap cost independent of this trap.",
    ),
)

FEATURE_TIMING: dict[str, tuple[str, str]] = {
    "batch_id": ("IDENTIFIER", "Unique production batch identifier"),
    "production_line_id": ("IDENTIFIER", "Stable production-line identifier"),
    "batch_date": ("DECISION_TIME", "Decision timestamp"),
    "product_line": ("DECISION_TIME", "Product line"),
    "raw_material_supplier": ("DECISION_TIME", "Raw material supplier for this batch"),
    "shift": ("DECISION_TIME", "Production shift"),
    "batch_size_units": ("DECISION_TIME", "Units produced in this batch"),
    "operator": ("DECISION_TIME", "Operator of record for this batch"),
    "machine_id": ("DECISION_TIME", "Machine used for this batch"),
    "planned_cycle_time_min": ("DECISION_TIME", "Planned per-unit cycle time in minutes"),
    "material_grade": ("DECISION_TIME", "Raw material grade on file"),
    "humidity_pct": ("DECISION_TIME", "Facility humidity at batch start"),
    "temperature_c": ("DECISION_TIME", "Facility temperature at batch start"),
    "rush_order": ("DECISION_TIME", "Whether this batch was a rush order"),
    "currency": ("METADATA", "Cost currency"),
    "defective": ("OUTCOME", "Whether the batch failed QA inspection"),
    "scrap_cost_usd": ("OUTCOME", "Realized scrap cost"),
    "rework_cost_usd": ("OUTCOME", "Realized rework cost"),
    "downtime_cost_usd": ("OUTCOME", "Realized unplanned-downtime cost"),
    "yield_loss_usd": ("OUTCOME", "Realized yield-loss cost"),
    "total_quality_cost_usd": (
        "OUTCOME",
        "Realized total quality cost (scrap+rework+downtime+yield)",
    ),
    "recurrence_90d": ("OUTCOME", "Defect recurrence within 90 days"),
    "inspection_completed_date": ("POST_DECISION", "Date QA inspection completed"),
    "quality_notes_count": ("POST_DECISION", "QA note events after batch completion"),
    "last_modified_at": ("POST_DECISION", "Operational update timestamp; leakage field"),
}

DECLARED_TYPES: dict[str, Any] = {
    "batch_id": "string",
    "production_line_id": "string",
    "batch_date": "date",
    "product_line": "string",
    "raw_material_supplier": "string",
    "shift": "string",
    "batch_size_units": "integer",
    "operator": "string",
    "machine_id": "string",
    "planned_cycle_time_min": "decimal",
    "material_grade": "string",
    "humidity_pct": "decimal",
    "temperature_c": "decimal",
    "rush_order": "boolean",
    "currency": "string",
    "defective": "boolean",
    "scrap_cost_usd": "decimal",
    "rework_cost_usd": "decimal",
    "downtime_cost_usd": "decimal",
    "yield_loss_usd": "decimal",
    "total_quality_cost_usd": "decimal",
    "recurrence_90d": "nullable_boolean",
    "inspection_completed_date": "nullable_date",
    "quality_notes_count": "integer",
    "last_modified_at": "date",
}

OUTCOME_COLUMNS = (
    "defective",
    "scrap_cost_usd",
    "rework_cost_usd",
    "downtime_cost_usd",
    "yield_loss_usd",
    "total_quality_cost_usd",
    "recurrence_90d",
)


def _pattern_scale(config: DomainRunConfig, pattern_id: str) -> float:
    return config.scale_for(pattern_id) if config.is_active(pattern_id) else 0.0


def generate_row(
    index: int, rng: random.Random, config: DomainRunConfig, disabled_pattern_id: str | None
) -> tuple[Row, list[str]]:
    batch_date = START_DATE + timedelta(days=rng.randrange(731))
    month = batch_date.month
    drift_period = "late" if batch_date >= date(2025, 1, 1) else "early"

    product_line = _weighted(
        rng, ["Line A", "Line B", "Line C", "Line D"], [0.30, 0.26, 0.24, 0.20]
    )
    shift_baseline = ["day", "evening", "night"]
    shift_weights = [0.42, 0.32, 0.26]
    rush_order = rng.random() < 0.22

    # Deliberately non-random assignment creates observed confounding traps (MT01-MT05) — each
    # gated behind config.trap_active so the "0 traps" variant is genuinely trap-free, not just
    # undocumented (HANDOFF-053). operator/raw_material_supplier/shift/machine_id/material_grade
    # itself never appear in an outcome-affecting code path except through the gated confounder,
    # and every skew is tuned hard enough to clear the outcome's background variance (the lesson
    # from domain 3's IT03 near-miss), not just plausibly nudged.
    batch_size_units = max(50, min(2000, int(rng.gauss(650, 350))))
    planned_cycle_time_min = max(5.0, rng.gauss(32, 12))
    humidity_pct = max(20.0, min(95.0, rng.gauss(50, 15)))
    temperature_c = max(-5.0, min(40.0, rng.gauss(21, 7)))

    material_grade_weights = [0.62, 0.38]  # standard, premium
    if config.trap_active("MT05") and humidity_pct <= 50:
        # Split point deliberately matches the outcome formula's own pivot (humidity_pct > 50 is
        # where the humidity-driven scrap boost turns on) so the weight skew has real leverage.
        material_grade_weights = [0.04, 0.96]  # premium lots scheduled during low-humidity windows.
    material_grade = _weighted(rng, ["standard", "premium"], material_grade_weights)

    operator_weights = [1.0] * 8
    if config.trap_active("MT01") and batch_size_units >= 900:
        operator_weights[1] += 14.0  # Operator 2 routed disproportionately large batches.
    operator = _weighted(rng, [f"Operator {n}" for n in range(1, 9)], operator_weights)

    supplier_weights = [1.0] * 5
    if config.trap_active("MT02") and planned_cycle_time_min <= 20:
        supplier_weights[2] += 9.0  # Supplier 3 batches scheduled on tight, expedited cycles.
    raw_material_supplier = _weighted(rng, [f"Supplier {n}" for n in range(1, 6)], supplier_weights)

    machine_weights = [1.0] * 6
    if config.trap_active("MT04") and batch_size_units <= 300:
        machine_weights[4] += 10.0  # Machine 5 handles small quick jobs — opposite tail of MT01.
    machine_id = _weighted(rng, [f"Machine {n}" for n in range(1, 7)], machine_weights)

    shift_weights_local = list(shift_weights)
    if config.trap_active("MT03") and rush_order:
        shift_weights_local = [0.18, 0.22, 0.60]  # rush turnaround absorbed by night shift.
    shift = _weighted(rng, shift_baseline, shift_weights_local)

    complexity = (
        int(rush_order)
        + int(material_grade == "premium")
        + int(batch_size_units >= 1000)
        + int(shift == "night")
    )
    defective_logit = -1.9 + 0.3 * complexity
    scrap_cost_delta = 0.0
    rework_cost_delta = 0.0
    downtime_cost_delta = 0.0
    yield_loss_delta = 0.0
    defective_logit_delta = 0.0

    def active(pattern_id: str) -> bool:
        return config.is_active(pattern_id) and disabled_pattern_id != pattern_id

    patterns: list[str] = []

    if rush_order and batch_size_units >= 800 and material_grade == "standard":
        patterns.append("M01")
        if active("M01"):
            scale = _pattern_scale(config, "M01")
            scrap_cost_delta += 140 * scale
            downtime_cost_delta += 60 * scale
            defective_logit_delta += 0.5 * scale
    if product_line == "Line B" and humidity_pct >= 65 and month in {6, 7, 8}:
        patterns.append("M02")
        if active("M02"):
            scale = _pattern_scale(config, "M02")
            scrap_cost_delta += (40 + 1.6 * (humidity_pct - 65)) * scale
            rework_cost_delta += 55 * scale
    if shift == "night" and machine_id == "Machine 3" and planned_cycle_time_min <= 25:
        patterns.append("M03")
        if active("M03"):
            scale = _pattern_scale(config, "M03")
            downtime_cost_delta += 180 * scale
            yield_loss_delta += 45 * scale
    if product_line == "Line D" and temperature_c <= 8 and month in {12, 1, 2}:
        patterns.append("M04")
        if active("M04"):
            scale = _pattern_scale(config, "M04")
            scrap_cost_delta += 95 * scale
            rework_cost_delta += 70 * scale
    if operator == "Operator 6" and material_grade == "premium" and batch_size_units >= 800:
        patterns.append("M05")
        if active("M05"):
            rework_cost_delta += 165 * _pattern_scale(config, "M05")
    if shift == "night" and rush_order and product_line == "Line C":
        patterns.append("M06")
        if active("M06"):
            scale = _pattern_scale(config, "M06")
            downtime_cost_delta += 110 * scale
            scrap_cost_delta += 50 * scale
    if (
        material_grade == "premium"
        and raw_material_supplier == "Supplier 4"
        and drift_period == "late"
    ):
        patterns.append("M07")
        if active("M07"):
            scale = _pattern_scale(config, "M07")
            scrap_cost_delta += 100 * scale
            rework_cost_delta += 60 * scale
    if (
        batch_size_units >= 1200
        and raw_material_supplier == "Supplier 3"
        and material_grade == "standard"
    ):
        patterns.append("M08")
        if active("M08"):
            scale = _pattern_scale(config, "M08")
            yield_loss_delta += 150 * scale
            scrap_cost_delta += 40 * scale
    if month in {3, 4, 5} and humidity_pct >= 70:
        patterns.append("M09")
        if active("M09"):
            scale = _pattern_scale(config, "M09")
            line_b = product_line == "Line B"
            scrap_cost_delta += (120 if line_b else 45) * scale
            rework_cost_delta += (30 if line_b else 65) * scale

    defective = rng.random() < _sigmoid(defective_logit + defective_logit_delta)
    # scrap_cost's base scales with batch_size_units (real, always-on driver feeding MT01/MT04's
    # declared confounder — bigger batches produce proportionally more scrap dollars even at a
    # fixed defect rate) and with humidity_pct (real, always-on driver feeding MT05's declared
    # confounder). Neither operator/machine_id (MT01/MT04's apparent features) nor material_grade
    # (MT05's apparent feature) appear here — only the confounders do.
    scrap_cost = max(
        0.0,
        rng.gauss(0.03 * batch_size_units + scrap_cost_delta, 12 + 0.1 * scrap_cost_delta),
    )
    scrap_cost += 0.55 * max(0.0, humidity_pct - 50.0)
    rework_cost = max(0.0, rng.gauss(15 + rework_cost_delta, 10 + 0.1 * rework_cost_delta))
    downtime_cost = max(0.0, rng.gauss(10 + downtime_cost_delta, 10 + 0.1 * downtime_cost_delta))
    # rush_order and a tight planned_cycle_time_min are real, always-on downtime-cost drivers
    # feeding MT03's and MT02's declared confounders respectively — neither shift (MT03's apparent
    # feature) nor raw_material_supplier (MT02's apparent feature) appear here.
    downtime_cost += 22.0 if rush_order else 0.0
    downtime_cost += max(0.0, 1.4 * (25.0 - planned_cycle_time_min))
    yield_loss = max(0.0, rng.gauss(8 + yield_loss_delta, 8 + 0.1 * yield_loss_delta))
    total_quality_cost = scrap_cost + rework_cost + downtime_cost + yield_loss
    recurrence_probability = _sigmoid(
        -1.5 + 0.85 * defective + 0.0009 * max(0, total_quality_cost - 60)
    )
    recurrence: bool | None = rng.random() < recurrence_probability
    if rng.random() < (0.35 if defective else 0.10):
        recurrence = None
    inspection_date = batch_date + timedelta(days=rng.randint(0, 5)) if defective else None

    row: Row = {
        "batch_id": f"MFG-{index + 1:05d}",
        "production_line_id": f"MFG-PL-{((index * 2_654_435_761) % 900) + 1:03d}",
        "batch_date": batch_date.isoformat(),
        "product_line": product_line,
        "raw_material_supplier": raw_material_supplier,
        "shift": shift,
        "batch_size_units": batch_size_units,
        "operator": operator,
        "machine_id": machine_id,
        "planned_cycle_time_min": round(planned_cycle_time_min, 2),
        "material_grade": material_grade,
        "humidity_pct": round(humidity_pct, 2),
        "temperature_c": round(temperature_c, 2),
        "rush_order": rush_order,
        "currency": "USD",
        "defective": defective,
        "scrap_cost_usd": round(scrap_cost, 2),
        "rework_cost_usd": round(rework_cost, 2),
        "downtime_cost_usd": round(downtime_cost, 2),
        "yield_loss_usd": round(yield_loss, 2),
        "total_quality_cost_usd": round(total_quality_cost, 2),
        "recurrence_90d": recurrence if recurrence is not None else "",
        "inspection_completed_date": inspection_date.isoformat() if inspection_date else "",
        "quality_notes_count": min(6, int(rng.expovariate(1 / (0.3 + 0.15 * complexity)))),
        "last_modified_at": (batch_date + timedelta(days=rng.randint(0, 60))).isoformat(),
    }
    return row, patterns


def corruption_ops(config: DomainRunConfig) -> tuple[CorruptionOp, ...]:
    def clear_operator(row: Row) -> None:
        row["operator"] = ""

    def mixed_date(row: Row) -> None:
        parsed = date.fromisoformat(str(row["batch_date"]))
        row["batch_date"] = parsed.strftime("%d/%m/%Y")

    def currency_symbol(row: Row) -> None:
        row["scrap_cost_usd"] = f"${row['scrap_cost_usd']}"

    def product_line_upper(row: Row) -> None:
        row["product_line"] = str(row["product_line"]).upper()

    def invalid_batch_size(row: Row) -> None:
        row["batch_size_units"] = -1

    def invalid_humidity(row: Row) -> None:
        row["humidity_pct"] = -10.0

    def whitespace_operator(row: Row) -> None:
        row["operator"] = f" {row['operator']} "

    return (
        CorruptionOp("missing_operator", 18, clear_operator),
        CorruptionOp("mixed_date_format", 13, mixed_date),
        CorruptionOp("currency_symbol", 9, currency_symbol),
        CorruptionOp("product_line_variant", 14, product_line_upper),
        CorruptionOp("invalid_batch_size", 3, invalid_batch_size),
        CorruptionOp("invalid_humidity", 2, invalid_humidity),
        CorruptionOp("whitespace_operator", 11, whitespace_operator),
        CorruptionOp("duplicate_source_rows", config.dirty_duplicate_rows, lambda row: None),
    )


SPEC = DomainSpec(
    domain_id=DOMAIN_ID,
    schema_version=SCHEMA_VERSION,
    primary_id_column="batch_id",
    clustering_key="production_line_id",
    decision_timestamp_column="batch_date",
    outcome_columns=OUTCOME_COLUMNS,
    primary_outcome_column="total_quality_cost_usd",
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
