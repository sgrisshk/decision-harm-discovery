"""Deterministic hidden-ground-truth travel benchmark generation."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from policy_analytics.blind_isolation import verify_candidate_commitment
from policy_analytics.outcomes.contract import OUTCOME_DEFINITIONS, PRIMARY_OUTCOME_ID

SEED = 20260813
ROW_COUNT = 10_000
START_DATE = date(2024, 1, 1)
PUBLIC_DIRECTORIES = ("raw", "reference", "metadata")
EVALUATION_DIRECTORY = "evaluation"

PATTERN_CONFIGURED_EFFECTS: dict[str, dict[str, Any]] = {
    "P01": {
        "additional_cost_location_delta_eur": 410,
        "cancellation_logit_delta": 1.05,
        "support_case_rate_delta": 0.75,
    },
    "P02": {
        "additional_cost_location_delta_eur": {
            "intercept": 520,
            "party_size_coefficient": 45,
            "formula": "520 + 45 * party_size",
        },
        "support_case_rate_delta": 1.0,
    },
    "P03": {
        "additional_cost_location_delta_eur": 240,
        "cancellation_logit_delta": 0.72,
    },
    "P04": {
        "additional_cost_location_delta_eur": 365,
        "support_case_rate_delta": 0.55,
    },
    "P05": {"additional_cost_location_delta_eur": 475},
    "P06": {
        "additional_cost_location_delta_eur": 300,
        "cancellation_logit_delta": 1.15,
    },
    "P07": {
        "additional_cost_location_delta_eur": 390,
        "support_case_rate_delta": 0.45,
    },
    "P08": {
        "additional_cost_location_delta_eur": 440,
        "support_case_rate_delta": 0.85,
    },
    "P09": {
        "additional_cost_location_delta_eur": {
            "by_customer_segment": {"corporate": 610, "otherwise": 230}
        },
        "cancellation_logit_delta": {"by_customer_segment": {"corporate": 0.85, "otherwise": 0.25}},
    },
}

PATTERN_VALID_INTERVALS: dict[str, dict[str, Any]] = {
    pattern_id: {
        "start_inclusive": "2024-01-01",
        "end_inclusive": "2025-12-31",
    }
    for pattern_id in PATTERN_CONFIGURED_EFFECTS
}
PATTERN_VALID_INTERVALS["P02"]["active_booking_months"] = [6, 7, 8]
PATTERN_VALID_INTERVALS["P04"]["active_booking_months"] = [1, 2, 12]
PATTERN_VALID_INTERVALS["P07"]["start_inclusive"] = "2025-01-01"
PATTERN_VALID_INTERVALS["P09"]["active_booking_months"] = [9, 10, 11]


@dataclass(frozen=True)
class BenchmarkConfig:
    seed: int = SEED
    row_count: int = ROW_COUNT
    start_date: str = START_DATE.isoformat()
    months: int = 24
    dirty_duplicate_rows: int = 37
    #: TASK-004 difficulty knobs. Every default below is the identity value for its own
    #: mechanism (1.0 = unscaled, 0 extra draws) so that `BenchmarkConfig()` — the config every
    #: already-frozen artifact (`5c41aab8...` hidden ground truth, `98ad4e7e...` analytical
    #: dataset identity, and every downstream discovery/validation/blind run built on them) was
    #: generated with — reproduces byte-identical output. None of these fields add, remove, or
    #: reorder a single `rng.*()` call versus the pre-TASK-004 generator; every one multiplies or
    #: nudges an already-existing magnitude or threshold in place. See `Difficulty`/
    #: `DIFFICULTY_PRESETS` for the named EASY/MEDIUM/HARD/BRUTAL combinations; `MEDIUM` is these
    #: defaults.
    effect_scale: float = 1.0
    noise_scale: float = 1.0
    confounding_scale: float = 1.0
    missingness_scale: float = 1.0
    rarity_scale: float = 1.0
    drift_scale: float = 1.0


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    BRUTAL = "brutal"


@dataclass(frozen=True, slots=True)
class DifficultyScales:
    effect_scale: float
    noise_scale: float
    confounding_scale: float
    missingness_scale: float
    rarity_scale: float
    drift_scale: float


#: Named combinations of the six TASK-004 knobs above, applied on top of `BenchmarkConfig`'s other
#: fields (seed/row_count/etc. stay caller-supplied). `MEDIUM` is exactly the pre-TASK-004
#: defaults — the currently frozen benchmark is `difficulty_config(Difficulty.MEDIUM)`, byte-
#: identical to `BenchmarkConfig()`. Larger effects/rarity, smaller noise/confounding/missingness,
#: are easier to discover; the reverse is harder. Chosen to move each knob a meaningful but not
#: destabilizing amount per step — see `docs/benchmark/difficulty-presets.md` for the full
#: rationale and verified per-preset support numbers.
DIFFICULTY_PRESETS: dict[Difficulty, DifficultyScales] = {
    Difficulty.EASY: DifficultyScales(
        effect_scale=1.6,
        noise_scale=0.7,
        confounding_scale=0.5,
        missingness_scale=0.5,
        rarity_scale=1.3,
        drift_scale=0.5,
    ),
    Difficulty.MEDIUM: DifficultyScales(
        effect_scale=1.0,
        noise_scale=1.0,
        confounding_scale=1.0,
        missingness_scale=1.0,
        rarity_scale=1.0,
        drift_scale=1.0,
    ),
    Difficulty.HARD: DifficultyScales(
        effect_scale=0.6,
        noise_scale=1.5,
        confounding_scale=1.6,
        missingness_scale=1.6,
        rarity_scale=0.7,
        drift_scale=1.6,
    ),
    Difficulty.BRUTAL: DifficultyScales(
        effect_scale=0.35,
        noise_scale=2.2,
        confounding_scale=2.4,
        missingness_scale=2.2,
        # 0.65, not a smaller (more aggressive) value: verified empirically that every one of the
        # 9 patterns keeps nonzero support on the full 10,000-row benchmark down to ~0.6; below
        # that, P04/P08's own already-narrow trigger conditions (each requires reaching the tail
        # of a capped gaussian on top of two other conditions) start losing all support outright,
        # which is "the pattern no longer exists in this sample," not "hard to find."
        rarity_scale=0.65,
        drift_scale=2.4,
    ),
}


def difficulty_config(
    difficulty: Difficulty, *, seed: int = SEED, row_count: int = ROW_COUNT
) -> BenchmarkConfig:
    """Build the `BenchmarkConfig` for a named preset. `Difficulty.MEDIUM` is exactly
    `BenchmarkConfig()` — asserted by `tests/analytics/test_difficulty_presets.py`."""
    scales = DIFFICULTY_PRESETS[difficulty]
    return BenchmarkConfig(
        seed=seed,
        row_count=row_count,
        effect_scale=scales.effect_scale,
        noise_scale=scales.noise_scale,
        confounding_scale=scales.confounding_scale,
        missingness_scale=scales.missingness_scale,
        rarity_scale=scales.rarity_scale,
        drift_scale=scales.drift_scale,
    )


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def scaled_uniform(rng: random.Random, low: float, high: float, scale: float) -> float:
    """`rng.uniform(low, high)` with its width scaled around its own mean. Exactly
    `rng.uniform(low, high)` (same single `rng.random()` draw, same arguments) when `scale == 1.0`
    — never adds or removes a draw, so this never shifts the PRNG sequence for later calls."""
    mean = (low + high) / 2
    half_width = (high - low) / 2 * scale
    return rng.uniform(mean - half_width, mean + half_width)


def _tightened_min(base: float, rarity: float, domain_max: float) -> float:
    """A ">=" trigger threshold tightened by `rarity` (identity at `rarity == 1.0`), capped at
    `domain_max` so a small `rarity` doesn't push the threshold past the field's actual achievable
    range and make it structurally impossible (as opposed to merely rare). This caps *reachability*
    only — a capped threshold can still have near-zero real support if reaching it requires an
    extreme tail of its own generating distribution (e.g. `trip_duration_days`'s gaussian, capped
    well below where its mass actually lives); `DIFFICULTY_PRESETS[Difficulty.BRUTAL].rarity_scale`
    was chosen empirically so every pattern keeps nonzero support on the full 10,000-row benchmark
    — see that field's own comment and `docs/benchmark/difficulty-presets.md`."""
    return min(domain_max, base / rarity)


def scale_effect_leaves(value: object, scale: float) -> object:
    """Recursively multiply every numeric leaf of a `PATTERN_CONFIGURED_EFFECTS[pattern_id]`
    entry by `scale`, leaving strings (e.g. the descriptive `"formula"` field) untouched. Linear
    scaling distributes over the `intercept`/`party_size_coefficient` shape exactly the same as
    scaling the whole hardcoded expression in `_generate_row` — the two are mathematically
    guaranteed consistent without sharing code, verified directly in
    `tests/analytics/test_difficulty_presets.py`.

    `scale == 1.0` returns `value` completely untouched (not `value * 1.0`) so the already-frozen
    `hidden_ground_truth.json` (`5c41aab8...`) stays byte-identical at `Difficulty.MEDIUM` — an int
    leaf like `410` must stay the JSON integer `410`, never become the float `410.0`, or every
    downstream consumer pinned to that exact SHA-256 (already-completed discovery/validation/blind
    runs) would silently see a changed artifact.
    """
    if scale == 1.0:
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value * scale
    if isinstance(value, dict):
        typed_value = cast(dict[str, object], value)
        return {key: scale_effect_leaves(item, scale) for key, item in typed_value.items()}
    return value


def _money(value: float) -> float:
    return round(value, 2)


def _weighted(rng: random.Random, values: list[str], weights: list[float]) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


def _generate_row(
    index: int,
    rng: random.Random,
    config: BenchmarkConfig,
    disabled_pattern_id: str | None = None,
) -> tuple[dict[str, object], list[str]]:
    booking_date = START_DATE + timedelta(days=rng.randrange(731))
    month = booking_date.month
    drift_period = "late" if booking_date >= date(2025, 1, 1) else "early"
    segment = _weighted(rng, ["leisure", "family", "corporate"], [0.57, 0.27, 0.16])
    customer_type = _weighted(rng, ["new", "returning"], [0.62, 0.38])
    destination_weights = [0.22, 0.16, 0.23, 0.22, 0.17]
    if month in {6, 7, 8}:
        destination_weights = [0.18, 0.10, 0.17, 0.22, 0.33]
    destination = _weighted(
        rng, ["Lisbon", "Reykjavik", "Rome", "Tokyo", "Zanzibar"], destination_weights
    )
    lead_base = 22 if segment == "corporate" else 62
    lead_time = max(2, min(240, int(rng.gauss(lead_base, 35))))
    travel_date = booking_date + timedelta(days=lead_time)
    party_size = rng.randint(3, 7) if segment == "family" else rng.randint(1, 3)
    trip_duration = max(2, min(28, int(rng.gauss(8 if segment != "corporate" else 5, 4))))
    category = _weighted(rng, ["standard", "premium", "luxury"], [0.58, 0.31, 0.11])
    channel = _weighted(
        rng, ["direct", "partner", "paid_search", "referral"], [0.35, 0.25, 0.27, 0.13]
    )

    # Deliberately non-random assignment creates observed confounding traps. Strength scales with
    # config.confounding_scale (1.0 = unscaled); the weight itself is compared/consumed by
    # rng.choices() the same way regardless, so this never changes the draw count.
    manager_weights = [1.0] * 8
    if destination in {"Tokyo", "Zanzibar"} or lead_time < 14:
        manager_weights[1] += 3.5 * config.confounding_scale  # Manager 2's bookings are harder.
    manager = _weighted(rng, [f"Manager {number}" for number in range(1, 9)], manager_weights)
    supplier_weights = [1.0, 1.0, 1.0, 1.0]
    if trip_duration >= 14:
        supplier_weights[0] += 4.0 * config.confounding_scale  # Atlas handles long trips.
    if destination == "Tokyo":
        supplier_weights[1] += 2.0 * config.confounding_scale
    supplier = _weighted(rng, ["Atlas", "BlueWing", "Cedar", "DeltaSun"], supplier_weights)

    price_multiplier = {"standard": 1.0, "premium": 1.42, "luxury": 2.15}[category]
    destination_multiplier = {
        "Lisbon": 0.82,
        "Reykjavik": 1.18,
        "Rome": 0.9,
        "Tokyo": 1.38,
        "Zanzibar": 1.25,
    }[destination]
    customer_price = max(
        450.0,
        rng.gauss(1750, 360 * config.noise_scale) * price_multiplier * destination_multiplier
        + 115 * party_size
        + 48 * trip_duration,
    )
    discount_choices = [0.0, 0.03, 0.05, 0.08, 0.12, 0.18]
    discount_weights = [0.22, 0.14, 0.25, 0.21, 0.13, 0.05]
    if channel == "paid_search" or customer_type == "new":
        discount_weights[-2] += 0.12
        discount_weights[-1] += 0.08
    discount = rng.choices(discount_choices, weights=discount_weights, k=1)[0]
    payment_method = _weighted(rng, ["card", "bank_transfer", "wallet"], [0.62, 0.28, 0.10])
    if lead_time < 14:
        payment_method = _weighted(rng, ["card", "bank_transfer", "wallet"], [0.4, 0.5, 0.1])
    installments = rng.choices([1, 2, 3, 4], weights=[0.58, 0.21, 0.15, 0.06], k=1)[0]
    complexity = (
        int(destination in {"Tokyo", "Zanzibar"})
        + int(lead_time < 14)
        + int(party_size >= 5)
        + int(trip_duration >= 14)
    )
    manual_exception = rng.random() < 0.025 + 0.055 * complexity

    patterns: list[str] = []
    loss = 0.0
    cancel_logit = -3.05 + 0.34 * complexity
    support_lambda = 0.16 + 0.10 * complexity

    # Trigger thresholds are nudged by config.rarity_scale (>1 loosens/more support, <1 tightens/
    # less support; identity at 1.0 — every comparison below reduces to its original literal).
    # Effect magnitudes are multiplied by config.effect_scale (identity at 1.0). Neither changes
    # which or how many rng.*() calls happen, so MEDIUM (all scales 1.0) is byte-identical to the
    # pre-TASK-004 generator — verified in tests/analytics/test_difficulty_presets.py.
    rarity = config.rarity_scale
    effect = config.effect_scale
    if supplier == "BlueWing" and discount >= 0.12 and lead_time < 21 * rarity:
        patterns.append("P01")
        if disabled_pattern_id != "P01":
            loss += 410 * effect
            cancel_logit += 1.05 * effect
            support_lambda += 0.75 * effect
    if (
        destination == "Zanzibar"
        and segment == "family"
        and party_size >= _tightened_min(5, rarity, 7)  # 7 = max party_size (family segment)
        and month in {6, 7, 8}
    ):
        patterns.append("P02")
        if disabled_pattern_id != "P02":
            loss += (520 + 45 * party_size) * effect
            support_lambda += 1.0 * effect
    if (
        installments >= _tightened_min(3, rarity, 4)  # 4 = max installments
        and customer_type == "new"
        and channel == "paid_search"
    ):
        patterns.append("P03")
        if disabled_pattern_id != "P03":
            loss += 240 * effect
            cancel_logit += 0.72 * effect
    if (
        supplier == "Atlas"
        and trip_duration >= _tightened_min(14, rarity, 28)  # 28 = max trip_duration_days
        and month in {1, 2, 12}
    ):
        patterns.append("P04")
        if disabled_pattern_id != "P04":
            loss += 365 * effect
            support_lambda += 0.55 * effect
    if manager == "Manager 4" and manual_exception and customer_price >= 3500 / rarity:
        patterns.append("P05")
        if disabled_pattern_id != "P05":
            loss += 475 * effect
    if destination == "Tokyo" and lead_time < 10 * rarity and payment_method == "bank_transfer":
        patterns.append("P06")
        if disabled_pattern_id != "P06":
            loss += 300 * effect
            cancel_logit += 1.15 * effect
    if (
        supplier == "Cedar"
        and channel == "partner"
        and customer_type == "returning"
        and drift_period == "late"
    ):
        patterns.append("P07")
        if disabled_pattern_id != "P07":
            # The one pattern whose trigger is itself temporal — drift_scale represents how much
            # more (or less) unstable this drift-linked relationship is (identity at 1.0).
            drift_effect = effect * config.drift_scale
            loss += 390 * drift_effect
            support_lambda += 0.45 * drift_effect
    if (
        category == "luxury"
        and party_size == 1
        and lead_time >= _tightened_min(90, rarity, 240)  # 240 = max lead_time
    ):
        patterns.append("P08")
        if disabled_pattern_id != "P08":
            loss += 440 * effect
            support_lambda += 0.85 * effect
    if (
        supplier == "DeltaSun"
        and month in {9, 10, 11}
        and party_size >= _tightened_min(4, rarity, 7)  # 7 = max party_size (family segment)
    ):
        patterns.append("P09")
        if disabled_pattern_id != "P09":
            heterogeneous_loss = 610 if segment == "corporate" else 230
            loss += heterogeneous_loss * effect
            cancel_logit += (0.85 if segment == "corporate" else 0.25) * effect

    cancellation = rng.random() < _sigmoid(cancel_logit)
    support_cases = min(6, int(rng.expovariate(1 / max(support_lambda, 0.01))))
    support_cost = support_cases * scaled_uniform(rng, 38, 92, config.noise_scale)
    payment_fee = customer_price * (0.012 + 0.008 * max(0, installments - 1))
    base_cost_ratio = scaled_uniform(rng, 0.66, 0.79, config.noise_scale) + 0.015 * complexity
    base_cost = customer_price * base_cost_ratio
    additional_cost = max(0.0, rng.gauss(42 + loss, (55 + 0.08 * loss) * config.noise_scale))
    net_revenue = customer_price * (1 - discount)
    refund_ratio = scaled_uniform(rng, 0.82, 1.0, config.noise_scale) if cancellation else 0.0
    refund_amount = net_revenue * refund_ratio
    gross_profit = net_revenue - base_cost - refund_amount
    contribution_margin = gross_profit - additional_cost - support_cost - payment_fee
    repeat_probability = _sigmoid(
        -0.55 - 0.95 * cancellation - 0.00022 * max(0, -contribution_margin)
    )
    repeat_purchase: bool | None = rng.random() < repeat_probability
    # Selection bias: repeat behavior is unobservable more often after cancellation. Scaled by
    # config.missingness_scale (identity at 1.0), clamped so it always stays a valid probability.
    missingness_threshold = min(1.0, (0.46 if cancellation else 0.07) * config.missingness_scale)
    if rng.random() < missingness_threshold:
        repeat_purchase = None
    refund_date = booking_date + timedelta(days=rng.randint(2, 75)) if cancellation else None

    row: dict[str, object] = {
        "booking_id": f"SYN-{index + 1:05d}",
        "customer_id": f"SYN-CUST-{((index * 2_654_435_761) % 3_200) + 1:04d}",
        "booking_date": booking_date.isoformat(),
        "travel_date": travel_date.isoformat(),
        "destination": destination,
        "supplier": supplier,
        "product_category": category,
        "customer_price_eur": _money(customer_price),
        "quoted_cost_eur": _money(base_cost),
        "discount_rate": discount,
        "manager": manager,
        "acquisition_channel": channel,
        "customer_segment": segment,
        "customer_type": customer_type,
        "party_size": party_size,
        "trip_duration_days": trip_duration,
        "booking_lead_days": lead_time,
        "payment_method": payment_method,
        "installments": installments,
        "manual_exception": manual_exception,
        "currency": "EUR",
        "cancellation": cancellation,
        "refund_amount_eur": _money(refund_amount),
        "refund_date": refund_date.isoformat() if refund_date else "",
        "booking_changes": min(5, int(rng.expovariate(1 / (0.25 + 0.15 * complexity)))),
        "support_cases": support_cases,
        "support_cost_eur": _money(support_cost),
        "additional_cost_eur": _money(additional_cost),
        "gross_profit_eur": _money(gross_profit),
        "contribution_margin_eur": _money(contribution_margin),
        "repeat_purchase_180d": repeat_purchase if repeat_purchase is not None else "",
        "last_modified_at": (booking_date + timedelta(days=rng.randint(0, 120))).isoformat(),
    }
    return row, patterns


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # csv.writer's default (excel) dialect uses "\r\n" regardless of platform — deterministic, but
    # not what's committed under synthetic_data/ (plain "\n"). Pin lineterminator explicitly so a
    # freshly generated file is byte-identical to the committed one everywhere, instead of only
    # appearing identical on a machine whose git client happens to normalize CRLF/LF for comparison
    # (core.autocrlf=input) — CI's runner does not, so `git diff --exit-code -- synthetic_data`
    # always failed on a clean checkout regardless of the actual generated content. See ADR-031.
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dirty_rows(
    clean_rows: list[dict[str, object]], config: BenchmarkConfig
) -> tuple[list[dict[str, object]], dict[str, Any]]:
    rows = [row.copy() for row in clean_rows]
    corruption_rng = random.Random(config.seed + 1)
    changes: dict[str, list[int]] = {
        "missing_supplier": [],
        "mixed_date_format": [],
        "currency_symbol": [],
        "category_variant": [],
        "invalid_party_size": [],
        "invalid_discount": [],
        "whitespace_manager": [],
        "duplicate_source_rows": [],
    }

    def take(count: int) -> list[int]:
        return corruption_rng.sample(range(len(rows)), count)

    for idx in take(180):
        rows[idx]["supplier"] = ""
        changes["missing_supplier"].append(idx)
    for idx in take(125):
        parsed = date.fromisoformat(str(rows[idx]["booking_date"]))
        rows[idx]["booking_date"] = parsed.strftime("%d/%m/%Y")
        changes["mixed_date_format"].append(idx)
    for idx in take(90):
        rows[idx]["customer_price_eur"] = f"€{rows[idx]['customer_price_eur']}"
        changes["currency_symbol"].append(idx)
    for idx in take(140):
        rows[idx]["product_category"] = str(rows[idx]["product_category"]).upper()
        changes["category_variant"].append(idx)
    for idx in take(24):
        rows[idx]["party_size"] = -1
        changes["invalid_party_size"].append(idx)
    for idx in take(19):
        rows[idx]["discount_rate"] = 1.25
        changes["invalid_discount"].append(idx)
    for idx in take(110):
        rows[idx]["manager"] = f" {rows[idx]['manager']} "
        changes["whitespace_manager"].append(idx)
    duplicate_indices = take(config.dirty_duplicate_rows)
    for idx in duplicate_indices:
        rows.append(rows[idx].copy())
        changes["duplicate_source_rows"].append(idx)
    return rows, {
        "seed": config.seed + 1,
        "operations": {
            key: {"count": len(value), "zero_based_source_rows": value}
            for key, value in changes.items()
        },
    }


def _feature_metadata() -> dict[str, Any]:
    classifications = {
        "booking_id": ("IDENTIFIER", "Unique synthetic booking identifier"),
        "customer_id": ("IDENTIFIER", "Stable synthetic customer identifier"),
        "booking_date": ("DECISION_TIME", "Decision timestamp"),
        "travel_date": ("DECISION_TIME", "Known scheduled travel date"),
        "destination": ("DECISION_TIME", "Quoted destination"),
        "supplier": ("DECISION_TIME", "Supplier selected at booking"),
        "product_category": ("DECISION_TIME", "Booked product tier"),
        "customer_price_eur": ("DECISION_TIME", "Quoted gross price"),
        "quoted_cost_eur": ("DECISION_TIME", "Cost estimate available at booking"),
        "discount_rate": ("DECISION_TIME", "Discount approved at booking"),
        "manager": ("DECISION_TIME", "Booking owner"),
        "acquisition_channel": ("DECISION_TIME", "Acquisition source"),
        "customer_segment": ("DECISION_TIME", "Pre-existing customer segment"),
        "customer_type": ("DECISION_TIME", "New or returning at booking"),
        "party_size": ("DECISION_TIME", "Booked travellers"),
        "trip_duration_days": ("DECISION_TIME", "Scheduled duration"),
        "booking_lead_days": ("DECISION_TIME", "Days between booking and travel"),
        "payment_method": ("DECISION_TIME", "Chosen payment method"),
        "installments": ("DECISION_TIME", "Agreed installment count"),
        "manual_exception": ("DECISION_TIME", "Exception recorded during approval"),
        "currency": ("METADATA", "Source currency"),
        "cancellation": ("OUTCOME", "Cancellation observed after booking"),
        "refund_amount_eur": ("OUTCOME", "Realized refund amount"),
        "refund_date": ("POST_DECISION", "Date a refund occurred"),
        "booking_changes": ("POST_DECISION", "Changes after initial booking"),
        "support_cases": ("POST_DECISION", "Support interactions after booking"),
        "support_cost_eur": ("OUTCOME", "Realized support cost"),
        "additional_cost_eur": ("OUTCOME", "Unplanned realized cost"),
        "gross_profit_eur": ("OUTCOME", "Realized gross profit"),
        "contribution_margin_eur": ("OUTCOME", "Realized contribution after downstream costs"),
        "repeat_purchase_180d": ("OUTCOME", "Repeat purchase within outcome window"),
        "last_modified_at": ("POST_DECISION", "Operational update timestamp; leakage field"),
    }
    return {
        "schema_version": "1.0.0",
        "columns": [
            {
                "name": name,
                "classification": classification,
                "semantic_meaning": meaning,
                "discovery_feature_allowed": classification == "DECISION_TIME",
                "leakage_risk": "HIGH"
                if classification in {"POST_DECISION", "OUTCOME"}
                else "NONE",
            }
            for name, (classification, meaning) in classifications.items()
        ],
    }


def _schema_profile(rows: list[dict[str, object]]) -> dict[str, Any]:
    """Produce deterministic profiling metadata for the clean reference data."""
    declared_types = {
        "booking_id": "string",
        "customer_id": "string",
        "booking_date": "date",
        "travel_date": "date",
        "destination": "categorical_string",
        "supplier": "categorical_string",
        "product_category": "categorical_string",
        "customer_price_eur": "decimal",
        "quoted_cost_eur": "decimal",
        "discount_rate": "decimal",
        "manager": "categorical_string",
        "acquisition_channel": "categorical_string",
        "customer_segment": "categorical_string",
        "customer_type": "categorical_string",
        "party_size": "integer",
        "trip_duration_days": "integer",
        "booking_lead_days": "integer",
        "payment_method": "categorical_string",
        "installments": "integer",
        "manual_exception": "boolean",
        "currency": "categorical_string",
        "cancellation": "boolean",
        "refund_amount_eur": "decimal",
        "refund_date": "nullable_date",
        "booking_changes": "integer",
        "support_cases": "integer",
        "support_cost_eur": "decimal",
        "additional_cost_eur": "decimal",
        "gross_profit_eur": "decimal",
        "contribution_margin_eur": "decimal",
        "repeat_purchase_180d": "nullable_boolean",
        "last_modified_at": "date",
    }
    columns: list[dict[str, Any]] = []
    for name in rows[0]:
        values = [row[name] for row in rows]
        present = [value for value in values if value != "" and value is not None]
        profile: dict[str, Any] = {
            "name": name,
            "declared_type": declared_types[name],
            "missing_count": len(values) - len(present),
            "missing_percentage": round(100 * (len(values) - len(present)) / len(values), 4),
            "distinct_count": len({str(value) for value in present}),
            "suspicious_values": [],
        }
        if present and declared_types[name] in {"decimal", "integer"}:
            numeric_values = [float(str(value)) for value in present]
            profile["min"] = min(numeric_values)
            profile["max"] = max(numeric_values)
        elif present and declared_types[name] in {"date", "nullable_date"}:
            date_values = [str(value) for value in present]
            profile["min"] = min(date_values)
            profile["max"] = max(date_values)
        columns.append(profile)
    return {
        "schema_version": "1.0.0",
        "record_count": len(rows),
        "column_count": len(rows[0]),
        "columns": columns,
    }


def _realized_pattern_effects(
    config: BenchmarkConfig,
    factual_rows: list[dict[str, object]],
    memberships: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    """Compute paired factual-minus-disabled effects under identical random draws."""
    outcome_columns = (
        "cancellation",
        "refund_amount_eur",
        "support_cost_eur",
        "additional_cost_eur",
        "gross_profit_eur",
        "contribution_margin_eur",
        "repeat_purchase_180d",
    )
    effects: dict[str, dict[str, Any]] = {}
    for pattern_id, affected_ids in memberships.items():
        affected = set(affected_ids)
        counterfactual_rng = random.Random(config.seed)
        counterfactual_rows = [
            _generate_row(index, counterfactual_rng, config, disabled_pattern_id=pattern_id)[0]
            for index in range(config.row_count)
        ]
        outcome_effects: dict[str, Any] = {}
        for column in outcome_columns:
            paired_differences: list[float] = []
            for factual, counterfactual in zip(factual_rows, counterfactual_rows, strict=True):
                if factual["booking_id"] not in affected:
                    continue
                factual_value = factual[column]
                counterfactual_value = counterfactual[column]
                if factual_value == "" or counterfactual_value == "":
                    continue
                if isinstance(factual_value, bool) and isinstance(counterfactual_value, bool):
                    paired_differences.append(float(int(factual_value) - int(counterfactual_value)))
                    continue
                paired_differences.append(
                    float(str(factual_value)) - float(str(counterfactual_value))
                )
            outcome_effects[column] = {
                "estimand": "mean(factual - counterfactual_with_only_this_pattern_disabled)",
                "mean_effect": (
                    round(sum(paired_differences) / len(paired_differences), 6)
                    if paired_differences
                    else None
                ),
                "paired_record_count": len(paired_differences),
            }
        effects[pattern_id] = {
            "affected_record_count": len(affected),
            "outcomes": outcome_effects,
        }
    return effects


def _ground_truth(
    config: BenchmarkConfig,
    memberships: dict[str, list[str]],
    realized_effects: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    primary_outcome = next(
        definition
        for definition in OUTCOME_DEFINITIONS
        if definition.outcome_id == PRIMARY_OUTCOME_ID
    )

    def true_effect(pattern_id: str) -> dict[str, Any]:
        realized = realized_effects[pattern_id]["outcomes"][primary_outcome.column]
        realized_value = realized["mean_effect"]
        affected_n = realized_effects[pattern_id]["affected_record_count"]
        # P07 is the one drift-linked pattern (see _generate_row) — its applied magnitude is
        # additionally scaled by drift_scale, so its reported configured_effect must be too, to
        # stay consistent with what was actually applied (identity at effect_scale=drift_scale=1.0).
        pattern_scale = config.effect_scale * (config.drift_scale if pattern_id == "P07" else 1.0)
        return {
            "pattern_id": pattern_id,
            "configured_effect": scale_effect_leaves(
                PATTERN_CONFIGURED_EFFECTS[pattern_id], pattern_scale
            ),
            "realized_effect": realized_value,
            "direction": "decrease_is_harm",
            "affected_n": affected_n,
            "affected_support": round(affected_n / config.row_count, 8),
            "realized_economic_impact": (
                round(-realized_value * affected_n, 2) if realized_value is not None else None
            ),
            "valid_time_interval": PATTERN_VALID_INTERVALS[pattern_id],
            "relevant_outcome": primary_outcome.column,
            "units": {
                "configured_effect": {
                    "additional_cost_location_delta_eur": "EUR",
                    "cancellation_logit_delta": "log-odds",
                    "support_case_rate_delta": "expected cases per booking",
                },
                "realized_effect": primary_outcome.unit,
                "affected_support": "fraction of benchmark rows",
                "realized_economic_impact": "EUR over affected benchmark bookings",
            },
            "estimand": realized["estimand"],
            "economic_impact_sign_convention": (
                "positive means realized harm; harm_multiplier=-1 from outcome contract"
            ),
        }

    patterns = [
        (
            "P01",
            "BlueWing high-discount short-lead",
            "supplier=BlueWing AND discount_rate>=0.12 AND booking_lead_days<21",
            "stable",
        ),
        (
            "P02",
            "Large Zanzibar summer families",
            "destination=Zanzibar AND customer_segment=family AND party_size>=5 "
            "AND booking_month IN [6,7,8]",
            "seasonal",
        ),
        (
            "P03",
            "Installment risk for paid-search newcomers",
            "installments>=3 AND customer_type=new AND acquisition_channel=paid_search",
            "stable",
        ),
        (
            "P04",
            "Atlas long winter itinerary cost",
            "supplier=Atlas AND trip_duration_days>=14 AND booking_month IN [1,2,12]",
            "seasonal",
        ),
        (
            "P05",
            "Manager 4 expensive manual exceptions",
            "manager=Manager 4 AND manual_exception=true AND customer_price_eur>=3500",
            "stable",
        ),
        (
            "P06",
            "Tokyo urgent bank transfers",
            "destination=Tokyo AND booking_lead_days<10 AND payment_method=bank_transfer",
            "stable",
        ),
        (
            "P07",
            "Late-period Cedar partner regression",
            "supplier=Cedar AND acquisition_channel=partner AND customer_type=returning "
            "AND booking_date>=2025-01-01",
            "drift",
        ),
        (
            "P08",
            "Solo luxury long-lead servicing",
            "product_category=luxury AND party_size=1 AND booking_lead_days>=90",
            "stable",
        ),
        (
            "P09",
            "DeltaSun autumn groups",
            "supplier=DeltaSun AND booking_month IN [9,10,11] AND party_size>=4",
            "heterogeneous_by_customer_segment",
        ),
    ]
    traps = [
        {
            "id": "T01",
            "apparent_feature": "manager=Manager 2",
            "confounded_by": [
                "destination",
                "booking_lead_days",
                "party_size",
                "trip_duration_days",
            ],
            "direct_effect": 0,
        },
        {
            "id": "T02",
            "apparent_feature": "supplier=Atlas",
            "confounded_by": ["trip_duration_days", "booking_month"],
            "direct_effect": 0,
        },
        {
            "id": "T03",
            "apparent_feature": "acquisition_channel=paid_search",
            "confounded_by": ["customer_type", "discount_rate", "installments"],
            "direct_effect": 0,
        },
        {
            "id": "T04",
            "apparent_feature": "payment_method=bank_transfer",
            "confounded_by": ["booking_lead_days", "destination"],
            "direct_effect": 0,
        },
        {
            "id": "T05",
            "apparent_feature": "manual_exception=true",
            "confounded_by": [
                "destination",
                "party_size",
                "trip_duration_days",
                "booking_lead_days",
            ],
            "direct_effect": 0,
            "note": "P05 is a genuine interaction; the main effect is a trap.",
        },
    ]
    return {
        "benchmark_version": "1.0.0",
        "seed": config.seed,
        "warning": "RESTRICTED: do not expose to ML Discovery before candidate persistence.",
        "patterns": [
            {
                "id": pattern_id,
                "name": name,
                "rule": rule,
                "behavior": behavior,
                "affected_booking_ids": memberships[pattern_id],
                "realized_counterfactual_effects": realized_effects[pattern_id],
                "true_effect": true_effect(pattern_id),
            }
            for pattern_id, name, rule, behavior in patterns
        ],
        "confounding_traps": traps,
        "selection_bias": {
            "field": "repeat_purchase_180d",
            "mechanism": (
                "Outcome-dependent missingness; cancellations have a much higher missing "
                "probability."
            ),
        },
    }


def generate_benchmark(output_root: Path, config: BenchmarkConfig | None = None) -> dict[str, str]:
    """Generate all benchmark artifacts and return their checksums."""
    config = config or BenchmarkConfig()
    scale_fields = (
        config.effect_scale,
        config.noise_scale,
        config.confounding_scale,
        config.missingness_scale,
        config.rarity_scale,
        config.drift_scale,
    )
    if (
        config.row_count < 180
        or config.dirty_duplicate_rows < 0
        or config.dirty_duplicate_rows > config.row_count
        or config.months != 24
        or config.start_date != START_DATE.isoformat()
        or any(scale <= 0 for scale in scale_fields)
    ):
        raise ValueError(
            "benchmark requires at least 180 rows, a feasible duplicate count, the configured "
            "24-month window, and every TASK-004 difficulty scale factor strictly positive"
        )
    rng = random.Random(config.seed)
    clean_rows: list[dict[str, object]] = []
    memberships: dict[str, list[str]] = {f"P{number:02d}": [] for number in range(1, 10)}
    for index in range(config.row_count):
        row, matched_patterns = _generate_row(index, rng, config)
        clean_rows.append(row)
        for pattern_id in matched_patterns:
            memberships[pattern_id].append(str(row["booking_id"]))
    dirty_rows, corruption_manifest = _dirty_rows(clean_rows, config)
    realized_effects = _realized_pattern_effects(config, clean_rows, memberships)

    clean_path = output_root / "reference" / "travel_bookings_clean.csv"
    dirty_path = output_root / "raw" / "travel_bookings_dirty.csv"
    _write_csv(clean_path, clean_rows)
    _write_csv(dirty_path, dirty_rows)
    _write_json(output_root / "metadata" / "feature_timing.json", _feature_metadata())
    _write_json(output_root / "metadata" / "schema_profile.json", _schema_profile(clean_rows))
    _write_json(output_root / "metadata" / "corruption_manifest.json", corruption_manifest)
    _write_json(
        output_root / "evaluation" / "hidden_ground_truth.json",
        _ground_truth(config, memberships, realized_effects),
    )

    split_manifest = {
        "strategy": "booking_date chronological boundaries; no random shuffling",
        "development": {"start": "2024-01-01", "end_inclusive": "2024-12-31"},
        "validation": {"start": "2025-01-01", "end_inclusive": "2025-06-30"},
        "future_holdout": {"start": "2025-07-01", "end_inclusive": "2025-12-31"},
    }
    _write_json(output_root / "metadata" / "temporal_splits.json", split_manifest)
    config_payload = {**asdict(config), "generator_version": "1.0.0"}
    _write_json(output_root / "metadata" / "generation_config.json", config_payload)

    checksums_path = output_root / "metadata" / "checksums.json"
    artifact_paths = sorted(
        path
        for directory in PUBLIC_DIRECTORIES
        for path in (output_root / directory).rglob("*")
        if path.is_file() and path != checksums_path
    )
    readme_path = output_root / "README.md"
    if readme_path.exists():
        artifact_paths.append(readme_path)
    checksums = {str(path.relative_to(output_root)): _sha256(path) for path in artifact_paths}
    _write_json(checksums_path, checksums)
    _write_json(
        output_root / EVALUATION_DIRECTORY / "checksums.json",
        {
            "hidden_ground_truth.json": _sha256(
                output_root / EVALUATION_DIRECTORY / "hidden_ground_truth.json"
            )
        },
    )
    return checksums


def evaluate_persisted_candidates(
    candidates_path: Path, ground_truth_path: Path, receipt_path: Path, signing_key: bytes
) -> dict[str, Any]:
    """Open truth only after verifying an evaluator-signed commitment.

    This narrow evaluator is intentionally mechanical; full statistical benchmark scoring belongs
    to TASK-028.
    """
    receipt = verify_candidate_commitment(candidates_path, receipt_path, signing_key)
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    if not isinstance(truth.get("patterns"), list):
        raise ValueError("ground truth patterns must be a list")
    raw_candidate_items: object = candidates.get("candidates")
    if not isinstance(raw_candidate_items, list):
        raise ValueError("candidate artifact must contain a candidates list")
    candidate_items = cast(list[object], raw_candidate_items)
    return {
        "candidate_file_sha256": _sha256(candidates_path),
        "blind_bundle_id": receipt["blind_bundle_id"],
        "committed_at": receipt["committed_at"],
        "evaluated_at": datetime.now(UTC).isoformat(),
        "candidate_count": len(candidate_items),
        "ground_truth_pattern_count": len(truth["patterns"]),
        "note": (
            "Commitment verified. Rule matching, precision/recall, confounder scoring, direction, "
            "and impact error are owned by TASK-028; caller-claimed truth IDs are ignored."
        ),
    }
