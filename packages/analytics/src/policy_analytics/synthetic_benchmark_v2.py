"""TASK-107 Phase 2a: benchmark v2 generator skeleton with RNG-isolated outcome draws.

v2 lives ALONGSIDE v1: this module imports (never edits) `synthetic_benchmark` (v1). No target is
designed or selected here (that is Phase 2b); the hook is `TargetSpec` / `generate_v2`.

**Why a new module (FC2/FC3, `ADR-107` freeze order).** In v1 one `random.Random` stream feeds a
row's covariates and its outcome-conditional draws (`refund_ratio` and the refund date are drawn
only when the row cancels). Anything that changes which rows cancel therefore shifts the stream and
changes every later row's covariates (measured in `rev1_check.py`: `n_affected` differs in 115 of
120 (pattern, seed) pairs). v2 removes that coupling:

* **Covariate stream (stream A).** One `random.Random(seed)` consumed *exactly as v1 consumes it*,
  by calling the real, unmodified v1 `_generate_row` for every row as a shadow. The covariate
  columns of each v2 row are taken from that call. Stream A is a function of `(seed, row_count)`
  only: it does not see v2 targets, so covariates are byte-identical for every target set, and
  identical to v1's covariates for the same seed (verified against the committed v1 clean CSV).
  The v1 nine-pattern effects act only inside the shadow (they decide v1's RNG consumption); they
  play no role in v2 outcomes (`ADR-107` D11: clean v2).
* **Outcome streams (stream B).** Every outcome / outcome-derived column is drawn from a per-row
  `random.Random` keyed by `sha256("travel-v2/outcome/<seed>/<index>")`, with the SAME call
  sequence for every row and target set (conditional draws such as `refund_ratio` and the refund
  offset are drawn unconditionally and used only for cancelling rows). [Rev 3] "Same call
  sequence", not "same number of RNG words": `randint` uses rejection sampling, so the number of
  Mersenne Twister words consumed per row varies, but it depends only on `(seed, index)` (the
  per-row stream is keyed by them), never on targets, so isolation holds. A target therefore changes
  only the rows that satisfy its predicate (common random numbers), never any other row.

**What is and is not reproduced relative to v1.** Reproduced byte-for-byte: every covariate column
(`COVARIATE_COLUMNS`, including `quoted_cost_eur` and identifiers). NOT reproduced: every outcome
or derived column (`OUTCOME_COLUMNS`) even with zero targets, because outcomes come from stream B
instead of v1's interleaved stream and v2 carries none of v1's nine patterns; the v2 zero-target
outcome distribution is v1's baseline mechanism (complexity-driven cancellation, support, cost),
not v1's realised values. v1 files, ground truth and the v1 generator are untouched.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from policy_analytics import synthetic_benchmark as v1
from policy_analytics.analytical_dataset import build_analytical_dataset

BENCHMARK_ID = "travel-v2"
GENERATOR_VERSION = "2.0.0-draft"

#: Columns produced by the covariate stream (A): identical to v1 for the same seed.
COVARIATE_COLUMNS: tuple[str, ...] = (
    "booking_id",
    "customer_id",
    "booking_date",
    "travel_date",
    "destination",
    "supplier",
    "product_category",
    "customer_price_eur",
    "quoted_cost_eur",
    "discount_rate",
    "manager",
    "acquisition_channel",
    "customer_segment",
    "customer_type",
    "party_size",
    "trip_duration_days",
    "booking_lead_days",
    "payment_method",
    "installments",
    "manual_exception",
    "currency",
)
#: Columns produced by the outcome streams (B): NOT reproduced from v1.
OUTCOME_COLUMNS: tuple[str, ...] = (
    "cancellation",
    "refund_amount_eur",
    "refund_date",
    "booking_changes",
    "support_cases",
    "support_cost_eur",
    "additional_cost_eur",
    "gross_profit_eur",
    "contribution_margin_eur",
    "repeat_purchase_180d",
    "last_modified_at",
)

#: Predicate over a row's covariate columns (dataset column names) plus `booking_month`.
Covariates = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TargetDose:
    """Additive effect on the three v1 levers (`loss` EUR, cancellation logit, support rate)."""

    loss_eur: float
    cancel_logit: float
    support_rate: float


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """Hook through which Phase 2b declares a v2 target. `rule` is the ground-truth grammar string
    (e.g. ``"a=x AND b>=3"``); `predicate` MUST implement exactly that rule over `Covariates`
    (`check_target_predicates` verifies the pair on real rows)."""

    target_id: str
    rule: str
    predicate: Callable[[Covariates], bool]
    dose: TargetDose


@dataclass(frozen=True, slots=True)
class V2Config:
    seed: int
    row_count: int = v1.ROW_COUNT

    def v1_config(self) -> v1.BenchmarkConfig:
        return v1.BenchmarkConfig(seed=self.seed, row_count=self.row_count)


@dataclass(slots=True)
class V2Draw:
    config: V2Config
    rows: list[dict[str, object]]
    memberships: dict[str, list[str]] = field(default_factory=lambda: {})


def outcome_rng(seed: int, index: int) -> random.Random:
    """Per-row outcome stream (B): a pure function of `(seed, index)`."""
    digest = hashlib.sha256(f"{BENCHMARK_ID}/outcome/{seed}/{index}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _complexity(cov: Covariates) -> int:
    return (
        int(cov["destination"] in {"Tokyo", "Zanzibar"})
        + int(cov["booking_lead_days"] < 14)
        + int(cov["party_size"] >= 5)
        + int(cov["trip_duration_days"] >= 14)
    )


def _covariates_with_month(v1_row: Mapping[str, object]) -> dict[str, Any]:
    cov: dict[str, Any] = {name: v1_row[name] for name in COVARIATE_COLUMNS}
    cov["booking_month"] = date.fromisoformat(str(v1_row["booking_date"])).month
    return cov


def _outcome_columns(
    index: int, seed: int, cov: Covariates, active: Sequence[TargetSpec]
) -> dict[str, object]:
    """Outcome section of v1's `_generate_row` (same functional forms), driven by stream B with an
    identical, unconditional call sequence for every row."""
    rng = outcome_rng(seed, index)
    complexity = _complexity(cov)
    loss = 0.0
    cancel_logit = -3.05 + 0.34 * complexity
    support_lambda = 0.16 + 0.10 * complexity
    for target in active:
        loss += target.dose.loss_eur
        cancel_logit += target.dose.cancel_logit
        support_lambda += target.dose.support_rate
    u_cancel = rng.random()
    u_support = rng.random()
    support_unit = rng.uniform(38, 92)
    z_additional = rng.gauss(0.0, 1.0)
    refund_unit = rng.uniform(0.82, 1.0)  # drawn for every row, used only if it cancels
    u_repeat = rng.random()
    u_missing = rng.random()
    refund_offset = rng.randint(2, 75)  # drawn for every row, used only if it cancels
    changes_unit = rng.random()
    modified_offset = rng.randint(0, 120)

    price = float(cov["customer_price_eur"])
    discount = float(cov["discount_rate"])
    installments = int(cov["installments"])
    base_cost = float(cov["quoted_cost_eur"])
    cancellation = u_cancel < v1._sigmoid(cancel_logit)
    support_cases = min(6, int(-math.log(1.0 - u_support) * max(support_lambda, 0.01)))
    support_cost = support_cases * support_unit
    payment_fee = price * (0.012 + 0.008 * max(0, installments - 1))
    additional_cost = max(0.0, 42 + loss + (55 + 0.08 * loss) * z_additional)
    net_revenue = price * (1 - discount)
    refund_ratio = refund_unit if cancellation else 0.0
    refund_amount = net_revenue * refund_ratio
    gross_profit = net_revenue - base_cost - refund_amount
    contribution_margin = gross_profit - additional_cost - support_cost - payment_fee
    repeat_probability = v1._sigmoid(
        -0.55 - 0.95 * cancellation - 0.00022 * max(0, -contribution_margin)
    )
    repeat_purchase: bool | None = u_repeat < repeat_probability
    if u_missing < (0.46 if cancellation else 0.07):
        repeat_purchase = None
    booking_date = date.fromisoformat(str(cov["booking_date"]))
    refund_date = booking_date + timedelta(days=refund_offset) if cancellation else None
    booking_changes = min(5, int(-math.log(1.0 - changes_unit) * (0.25 + 0.15 * complexity)))
    return {
        "cancellation": cancellation,
        "refund_amount_eur": v1._money(refund_amount),
        "refund_date": refund_date.isoformat() if refund_date else "",
        "booking_changes": booking_changes,
        "support_cases": support_cases,
        "support_cost_eur": v1._money(support_cost),
        "additional_cost_eur": v1._money(additional_cost),
        "gross_profit_eur": v1._money(gross_profit),
        "contribution_margin_eur": v1._money(contribution_margin),
        "repeat_purchase_180d": repeat_purchase if repeat_purchase is not None else "",
        "last_modified_at": (booking_date + timedelta(days=modified_offset)).isoformat(),
    }


def generate_v2(config: V2Config, targets: Sequence[TargetSpec] = ()) -> V2Draw:
    """Generate one v2 draw. `targets` is the Phase 2b hook (empty here by design)."""
    ids = [t.target_id for t in targets]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate target ids")
    cov_rng = random.Random(config.seed)  # stream A: consumed exactly as v1 consumes it
    v1_config = config.v1_config()
    draw = V2Draw(config=config, rows=[], memberships={tid: [] for tid in ids})
    for index in range(config.row_count):
        v1_row, _ = v1._generate_row(index, cov_rng, v1_config)  # shadow call: advances stream A
        cov = _covariates_with_month(v1_row)
        active = [t for t in targets if t.predicate(cov)]
        row: dict[str, object] = {name: v1_row[name] for name in COVARIATE_COLUMNS}
        row.update(_outcome_columns(index, config.seed, cov, active))
        # Keep v1's column order so feature metadata / dataset builders see the same schema.
        draw.rows.append({name: row[name] for name in v1_row})
        for target in active:
            draw.memberships[target.target_id].append(str(row["booking_id"]))
    return draw


def check_target_predicates(
    draw: V2Draw, targets: Sequence[TargetSpec], parse_rule: Callable[[str], Any]
) -> None:
    """Fail closed if a target's declared `rule` string and its `predicate` disagree on real rows.
    `parse_rule(rule) -> Callable[[Covariates], bool]` is supplied by the caller (Phase 2b)."""
    for target in targets:
        expected = parse_rule(target.rule)
        for row in draw.rows:
            cov = _covariates_with_month(row)
            if bool(expected(cov)) != bool(target.predicate(cov)):
                raise ValueError(f"target {target.target_id}: rule and predicate disagree")


def materialize_analytical(draw: V2Draw, work: Path) -> Path:
    """Write the clean CSV + feature timing and build the analytical dataset; returns its root.
    Same builder v1 uses (`build_analytical_dataset`); no engine involved."""
    v1._write_csv(work / "clean.csv", draw.rows)
    v1._write_json(work / "timing.json", v1._feature_metadata())
    manifest = build_analytical_dataset(work / "clean.csv", work / "timing.json", work / "a")
    return work / "a" / str(manifest["dataset_version"])
