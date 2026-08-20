"""Healthcare scheduling domain benchmark (TASK-061, domain 6 of 6, final domain).

Appointment no-show/rescheduling/overtime cost — structurally distinct from the first five domains:
the unit of analysis is a scheduled *appointment*, not an order/subscription/claim/batch/deal; the
decision-time surface is booking/scheduling data (lead time, channel, reminder opt-in, time of day);
the confounding source is provider/clinic-location routing. `harm_direction="increase_is_harm"`,
same convention as insurance/manufacturing (higher scheduling cost is harm).
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta
from typing import Any

from policy_analytics.domain_benchmarks.common import (
    CorruptionOp,
    DomainRunConfig,
    DomainSpec,
    PatternDefinition,
    Row,
    TrapDefinition,
)

DOMAIN_ID = "healthcare"
SCHEMA_VERSION = "healthcare-canonical-v1.0.0"
START_DATE = date(2024, 1, 1)
DEVELOPMENT_END = "2024-12-31"
VALIDATION_END = "2025-06-30"
FUTURE_HOLDOUT_END = "2025-12-31"

DEPARTMENT_BASE_VALUE = {
    "primary_care": 150.0,
    "pediatrics": 140.0,
    "dermatology": 230.0,
    "orthopedics": 340.0,
    "urgent_care": 200.0,
}
APPOINTMENT_TYPE_MULTIPLIER = {"routine": 0.85, "specialist": 1.5, "urgent": 1.25}
AGE_BAND_NOSHOW_ADJUSTMENT = {"child": -0.2, "young_adult": 0.6, "adult": 0.0, "senior": -0.5}


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _weighted(rng: random.Random, values: list[str], weights: list[float]) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


PATTERNS: tuple[PatternDefinition, ...] = (
    PatternDefinition(
        id="H01",
        name="Phone same-day specialist no-show risk",
        rule="booking_channel=phone AND lead_time_days<=1 AND appointment_type=specialist",
        behavior="stable",
        configured_effect={
            "overtime_cost_delta_usd": 40,
            "resched_cost_delta_usd": 90,
            "no_show_logit_delta": 0.5,
        },
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="H02",
        name="Winter pediatrics urgent-visit overtime surge",
        rule="department=pediatrics AND appointment_type=urgent AND month IN [12,1]",
        behavior="seasonal",
        configured_effect={
            "overtime_cost_delta_usd": {
                "intercept": 35,
                "lead_time_coefficient": 0.6,
                "formula": "35 + 0.6 * lead_time_days",
            },
            "resched_cost_delta_usd": 45,
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [12, 1],
        },
    ),
    PatternDefinition(
        id="H03",
        name="Young-adult no-reminder long-lead no-show",
        rule="patient_age_band=young_adult AND reminder_opted_in=false AND lead_time_days>=14",
        behavior="stable",
        configured_effect={"no_show_logit_delta": 0.45, "resched_cost_delta_usd": 30},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="H04",
        name="Summer Location D dermatology reschedules",
        rule="clinic_location=Location D AND department=dermatology AND month IN [6,7,8]",
        behavior="seasonal",
        configured_effect={"resched_cost_delta_usd": 70, "overtime_cost_delta_usd": 25},
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [6, 7, 8],
        },
    ),
    PatternDefinition(
        id="H05",
        name="Provider 5 long-lead specialist overbooking",
        rule="provider=Provider 5 AND appointment_type=specialist AND lead_time_days>=21",
        behavior="stable",
        configured_effect={"overtime_cost_delta_usd": 95},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="H06",
        name="Online evening urgent-care rescheduling errors",
        rule="booking_channel=online AND time_of_day=evening AND department=urgent_care",
        behavior="stable",
        configured_effect={"resched_cost_delta_usd": 85, "overtime_cost_delta_usd": 30},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="H07",
        name="Location C Group 3 late-period cost drift",
        rule="clinic_location=Location C AND insurance_group=Group 3 AND drift_period=late",
        behavior="drift",
        configured_effect={"overtime_cost_delta_usd": 50, "resched_cost_delta_usd": 40},
        valid_interval={"start_inclusive": "2025-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="H08",
        name="Long-lead reminded orthopedics no-show mismatch",
        rule="department=orthopedics AND lead_time_days>=30 AND reminder_opted_in=true",
        behavior="stable",
        configured_effect={"no_show_logit_delta": 0.4, "overtime_cost_delta_usd": 35},
        valid_interval={"start_inclusive": "2024-01-01", "end_inclusive": "2025-12-31"},
    ),
    PatternDefinition(
        id="H09",
        name="Spring long-lead heterogeneous by age band",
        rule="month IN [3,4,5] AND lead_time_days>=21",
        behavior="heterogeneous",
        configured_effect={
            "resched_cost_delta_usd": {"by_patient_age_band": {"senior": 80, "otherwise": 35}},
            "overtime_cost_delta_usd": {"by_patient_age_band": {"senior": 20, "otherwise": 45}},
        },
        valid_interval={
            "start_inclusive": "2024-01-01",
            "end_inclusive": "2025-12-31",
            "active_months": [3, 4, 5],
        },
    ),
)

#: Designed from the start against every prior domain's lessons: every confounder gated behind
#: `config.trap_active(...)`, riding a direct/multiplicative pathway (never a `complexity`-style
#: composite that could accidentally leak into an apparent feature — domain 5's `BT05` lesson), no
#: confounder shared with another trap's apparent feature (domain 4's `MT02`/`MT05` lesson), and
#: every skew tuned hard from the outset rather than starting weak (domain 3's `IT03` lesson).
TRAPS: tuple[TrapDefinition, ...] = (
    TrapDefinition(
        id="HT01",
        apparent_feature="provider=Provider 2",
        confounded_by=("lead_time_days",),
        note="Provider 2 is routed disproportionately long-lead-time appointments; lead time "
        "directly raises no-show probability, which gates lost_revenue_usd.",
    ),
    TrapDefinition(
        id="HT02",
        apparent_feature="clinic_location=Location A",
        confounded_by=("department",),
        note="Location A skews toward higher-value departments (orthopedics/dermatology); "
        "department carries a real, always-on base-value multiplier independent of this trap.",
    ),
    TrapDefinition(
        id="HT03",
        apparent_feature="booking_channel=phone",
        confounded_by=("appointment_type",),
        note="Proxy/mediator trap: phone bookings are disproportionately specialist "
        "appointments; appointment_type carries a real, always-on value multiplier by "
        "construction.",
    ),
    TrapDefinition(
        id="HT04",
        apparent_feature="time_of_day=evening",
        confounded_by=("lead_time_days",),
        note="Evening slots absorb same-day/short-lead demand — opposite tail of lead_time_days "
        "from HT01, no overlap.",
    ),
    TrapDefinition(
        id="HT05",
        apparent_feature="reminder_opted_in=true",
        confounded_by=("patient_age_band",),
        note="Reminder opt-in is disproportionately drawn from senior patients; patient age band "
        "carries a real, always-on no-show-probability adjustment independent of this trap.",
    ),
)

FEATURE_TIMING: dict[str, tuple[str, str]] = {
    "appointment_id": ("IDENTIFIER", "Unique appointment identifier"),
    "patient_id": ("IDENTIFIER", "Stable patient identifier"),
    "booking_date": ("DECISION_TIME", "Decision timestamp"),
    "appointment_date": ("DECISION_TIME", "Scheduled appointment date"),
    "department": ("DECISION_TIME", "Clinical department"),
    "provider": ("DECISION_TIME", "Assigned provider"),
    "clinic_location": ("DECISION_TIME", "Clinic location"),
    "insurance_group": ("DECISION_TIME", "Patient insurance group"),
    "appointment_type": ("DECISION_TIME", "Appointment type"),
    "booking_channel": ("DECISION_TIME", "Channel the appointment was booked through"),
    "lead_time_days": ("DECISION_TIME", "Days between booking and appointment"),
    "appointment_duration_min": ("DECISION_TIME", "Planned appointment duration in minutes"),
    "patient_age_band": ("DECISION_TIME", "Patient age band"),
    "reminder_opted_in": ("DECISION_TIME", "Whether the patient opted into reminders"),
    "time_of_day": ("DECISION_TIME", "Scheduled time of day"),
    "currency": ("METADATA", "Cost currency"),
    "no_show": ("OUTCOME", "Whether the patient no-showed"),
    "lost_revenue_usd": ("OUTCOME", "Realized lost revenue from a no-show"),
    "overtime_staffing_cost_usd": ("OUTCOME", "Realized overtime staffing cost"),
    "rescheduling_cost_usd": ("OUTCOME", "Realized rescheduling cost"),
    "net_scheduling_cost_usd": (
        "OUTCOME",
        "Realized total scheduling cost (lost revenue+overtime+rescheduling)",
    ),
    "return_visit_180d": ("OUTCOME", "Patient return visit within 180 days"),
    "checkin_time": ("POST_DECISION", "Check-in timestamp"),
    "notes_count": ("POST_DECISION", "Scheduling note events after booking"),
    "last_modified_at": ("POST_DECISION", "Operational update timestamp; leakage field"),
}

DECLARED_TYPES: dict[str, Any] = {
    "appointment_id": "string",
    "patient_id": "string",
    "booking_date": "date",
    "appointment_date": "date",
    "department": "string",
    "provider": "string",
    "clinic_location": "string",
    "insurance_group": "string",
    "appointment_type": "string",
    "booking_channel": "string",
    "lead_time_days": "integer",
    "appointment_duration_min": "integer",
    "patient_age_band": "string",
    "reminder_opted_in": "boolean",
    "time_of_day": "string",
    "currency": "string",
    "no_show": "boolean",
    "lost_revenue_usd": "decimal",
    "overtime_staffing_cost_usd": "decimal",
    "rescheduling_cost_usd": "decimal",
    "net_scheduling_cost_usd": "decimal",
    "return_visit_180d": "nullable_boolean",
    "checkin_time": "nullable_date",
    "notes_count": "integer",
    "last_modified_at": "date",
}

OUTCOME_COLUMNS = (
    "no_show",
    "lost_revenue_usd",
    "overtime_staffing_cost_usd",
    "rescheduling_cost_usd",
    "net_scheduling_cost_usd",
    "return_visit_180d",
)


def _pattern_scale(config: DomainRunConfig, pattern_id: str) -> float:
    return config.scale_for(pattern_id) if config.is_active(pattern_id) else 0.0


def generate_row(
    index: int, rng: random.Random, config: DomainRunConfig, disabled_pattern_id: str | None
) -> tuple[Row, list[str]]:
    booking_date = START_DATE + timedelta(days=rng.randrange(700))

    department = _weighted(
        rng,
        ["primary_care", "pediatrics", "dermatology", "orthopedics", "urgent_care"],
        [0.30, 0.20, 0.16, 0.14, 0.20],
    )
    appointment_type = _weighted(rng, ["routine", "specialist", "urgent"], [0.55, 0.30, 0.15])
    patient_age_band = _weighted(
        rng, ["child", "young_adult", "adult", "senior"], [0.18, 0.24, 0.36, 0.22]
    )
    lead_time_days = max(0, min(90, int(rng.gauss(14, 10))))
    appointment_date = booking_date + timedelta(days=lead_time_days)
    month = appointment_date.month
    drift_period = "late" if appointment_date >= date(2025, 1, 1) else "early"
    appointment_duration_min = max(10, min(90, int(rng.gauss(30, 10))))
    insurance_group = _weighted(
        rng, ["Group 1", "Group 2", "Group 3", "Group 4"], [0.30, 0.26, 0.24, 0.20]
    )
    time_of_day_weights = [0.40, 0.36, 0.24]  # morning, afternoon, evening

    # Deliberately non-random assignment creates observed confounding traps (HT01-HT05) — each
    # gated behind config.trap_active so the "0 traps" variant is genuinely trap-free, not just
    # undocumented (HANDOFF-053). Every confounder rides a direct/multiplicative pathway, no
    # composite "complexity" score is used (domain 5's BT05 lesson — a composite risks leaking an
    # apparent feature's own real effect in), and no confounder is also another trap's apparent
    # feature (domain 4's MT02/MT05 lesson).
    reminder_probability = 0.55
    if config.trap_active("HT05") and patient_age_band == "senior":
        reminder_probability = 0.94  # seniors disproportionately opt into reminders.
    reminder_opted_in = rng.random() < reminder_probability

    channel_weights = [0.28, 0.34, 0.24, 0.14]  # phone, online, app, walk_in
    if config.trap_active("HT03") and appointment_type == "specialist":
        channel_weights = [0.80, 0.08, 0.07, 0.05]  # specialist bookings skew phone hard.
    booking_channel = _weighted(rng, ["phone", "online", "app", "walk_in"], channel_weights)

    provider_weights = [1.0] * 8
    if config.trap_active("HT01") and lead_time_days >= 21:
        provider_weights[1] += 30.0  # Provider 2 routed disproportionately long-lead bookings.
    provider = _weighted(rng, [f"Provider {n}" for n in range(1, 9)], provider_weights)

    location_weights = [1.0, 1.0, 1.0, 1.0]  # A, B, C, D
    if config.trap_active("HT02") and department in {"orthopedics", "dermatology"}:
        location_weights[0] += 30.0  # Location A skews toward higher-value departments.
    clinic_location = _weighted(
        rng, ["Location A", "Location B", "Location C", "Location D"], location_weights
    )

    time_of_day_weights_local = list(time_of_day_weights)
    if config.trap_active("HT04") and lead_time_days <= 2:
        time_of_day_weights_local = [0.15, 0.15, 0.70]  # short-lead demand absorbed by evening.
    time_of_day = _weighted(rng, ["morning", "afternoon", "evening"], time_of_day_weights_local)

    no_show_logit_delta = 0.0
    overtime_cost_delta = 0.0
    resched_cost_delta = 0.0

    def active(pattern_id: str) -> bool:
        return config.is_active(pattern_id) and disabled_pattern_id != pattern_id

    patterns: list[str] = []

    if booking_channel == "phone" and lead_time_days <= 1 and appointment_type == "specialist":
        patterns.append("H01")
        if active("H01"):
            scale = _pattern_scale(config, "H01")
            overtime_cost_delta += 40 * scale
            resched_cost_delta += 90 * scale
            no_show_logit_delta += 0.5 * scale
    if department == "pediatrics" and appointment_type == "urgent" and month in {12, 1}:
        patterns.append("H02")
        if active("H02"):
            scale = _pattern_scale(config, "H02")
            overtime_cost_delta += (35 + 0.6 * lead_time_days) * scale
            resched_cost_delta += 45 * scale
    if patient_age_band == "young_adult" and not reminder_opted_in and lead_time_days >= 14:
        patterns.append("H03")
        if active("H03"):
            scale = _pattern_scale(config, "H03")
            no_show_logit_delta += 0.45 * scale
            resched_cost_delta += 30 * scale
    if clinic_location == "Location D" and department == "dermatology" and month in {6, 7, 8}:
        patterns.append("H04")
        if active("H04"):
            scale = _pattern_scale(config, "H04")
            resched_cost_delta += 70 * scale
            overtime_cost_delta += 25 * scale
    if provider == "Provider 5" and appointment_type == "specialist" and lead_time_days >= 21:
        patterns.append("H05")
        if active("H05"):
            overtime_cost_delta += 95 * _pattern_scale(config, "H05")
    if booking_channel == "online" and time_of_day == "evening" and department == "urgent_care":
        patterns.append("H06")
        if active("H06"):
            scale = _pattern_scale(config, "H06")
            resched_cost_delta += 85 * scale
            overtime_cost_delta += 30 * scale
    if clinic_location == "Location C" and insurance_group == "Group 3" and drift_period == "late":
        patterns.append("H07")
        if active("H07"):
            scale = _pattern_scale(config, "H07")
            overtime_cost_delta += 50 * scale
            resched_cost_delta += 40 * scale
    if department == "orthopedics" and lead_time_days >= 30 and reminder_opted_in:
        patterns.append("H08")
        if active("H08"):
            scale = _pattern_scale(config, "H08")
            no_show_logit_delta += 0.4 * scale
            overtime_cost_delta += 35 * scale
    if month in {3, 4, 5} and lead_time_days >= 21:
        patterns.append("H09")
        if active("H09"):
            scale = _pattern_scale(config, "H09")
            senior = patient_age_band == "senior"
            resched_cost_delta += (80 if senior else 35) * scale
            overtime_cost_delta += (20 if senior else 45) * scale

    # appointment_value scales multiplicatively with department (real, always-on driver feeding
    # HT02's declared confounder) and appointment_type (HT03's declared confounder). lead_time_days
    # (HT01/HT04's declared confounder) and patient_age_band (HT05's declared confounder) drive
    # no_show_logit directly. Neither clinic_location/booking_channel/provider/time_of_day/
    # reminder_opted_in (the apparent features) appear in this formula, only the confounders do.
    appointment_value = (
        DEPARTMENT_BASE_VALUE[department] * APPOINTMENT_TYPE_MULTIPLIER[appointment_type]
    )
    no_show_logit = (
        -1.7
        + 0.035 * lead_time_days
        + AGE_BAND_NOSHOW_ADJUSTMENT[patient_age_band]
        + no_show_logit_delta
    )
    no_show = rng.random() < _sigmoid(no_show_logit)
    lost_revenue = appointment_value if no_show else 0.0
    overtime_staffing_cost = max(
        0.0, rng.gauss(20 + overtime_cost_delta, 15 + 0.1 * overtime_cost_delta)
    )
    rescheduling_cost = max(0.0, rng.gauss(15 + resched_cost_delta, 12 + 0.1 * resched_cost_delta))
    net_scheduling_cost = lost_revenue + overtime_staffing_cost + rescheduling_cost
    return_visit_probability = _sigmoid(
        -1.3 + 0.7 * (not no_show) + 0.0006 * max(0.0, appointment_value - 100.0)
    )
    return_visit: bool | None = rng.random() < return_visit_probability
    if rng.random() < (0.10 if not no_show else 0.40):
        return_visit = None
    checkin_time = (
        datetime.combine(appointment_date, datetime.min.time())
        + timedelta(minutes=rng.randint(-10, 30))
        if not no_show
        else None
    )

    row: Row = {
        "appointment_id": f"HC-{index + 1:05d}",
        "patient_id": f"HC-PT-{((index * 2_654_435_761) % 3_400) + 1:04d}",
        "booking_date": booking_date.isoformat(),
        "appointment_date": appointment_date.isoformat(),
        "department": department,
        "provider": provider,
        "clinic_location": clinic_location,
        "insurance_group": insurance_group,
        "appointment_type": appointment_type,
        "booking_channel": booking_channel,
        "lead_time_days": lead_time_days,
        "appointment_duration_min": appointment_duration_min,
        "patient_age_band": patient_age_band,
        "reminder_opted_in": reminder_opted_in,
        "time_of_day": time_of_day,
        "currency": "USD",
        "no_show": no_show,
        "lost_revenue_usd": round(lost_revenue, 2),
        "overtime_staffing_cost_usd": round(overtime_staffing_cost, 2),
        "rescheduling_cost_usd": round(rescheduling_cost, 2),
        "net_scheduling_cost_usd": round(net_scheduling_cost, 2),
        "return_visit_180d": return_visit if return_visit is not None else "",
        "checkin_time": checkin_time.isoformat() if checkin_time else "",
        "notes_count": min(6, int(rng.expovariate(1 / 0.4))),
        "last_modified_at": (appointment_date + timedelta(days=rng.randint(0, 30))).isoformat(),
    }
    return row, patterns


def corruption_ops(config: DomainRunConfig) -> tuple[CorruptionOp, ...]:
    def clear_provider(row: Row) -> None:
        row["provider"] = ""

    def mixed_date(row: Row) -> None:
        parsed = date.fromisoformat(str(row["booking_date"]))
        row["booking_date"] = parsed.strftime("%d/%m/%Y")

    def currency_symbol(row: Row) -> None:
        row["lost_revenue_usd"] = f"${row['lost_revenue_usd']}"

    def department_upper(row: Row) -> None:
        row["department"] = str(row["department"]).upper()

    def invalid_lead_time(row: Row) -> None:
        row["lead_time_days"] = -1

    def invalid_duration(row: Row) -> None:
        row["appointment_duration_min"] = -5

    def whitespace_provider(row: Row) -> None:
        row["provider"] = f" {row['provider']} "

    return (
        CorruptionOp("missing_provider", 18, clear_provider),
        CorruptionOp("mixed_date_format", 13, mixed_date),
        CorruptionOp("currency_symbol", 9, currency_symbol),
        CorruptionOp("department_variant", 14, department_upper),
        CorruptionOp("invalid_lead_time", 3, invalid_lead_time),
        CorruptionOp("invalid_duration", 2, invalid_duration),
        CorruptionOp("whitespace_provider", 11, whitespace_provider),
        CorruptionOp("duplicate_source_rows", config.dirty_duplicate_rows, lambda row: None),
    )


SPEC = DomainSpec(
    domain_id=DOMAIN_ID,
    schema_version=SCHEMA_VERSION,
    primary_id_column="appointment_id",
    clustering_key="patient_id",
    decision_timestamp_column="booking_date",
    outcome_columns=OUTCOME_COLUMNS,
    primary_outcome_column="net_scheduling_cost_usd",
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
