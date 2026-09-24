"""`TASK-105` Phase 1: measure what the REAL benchmark generator implements for `T01`-`T05`.

Everything here is measurement, not assertion: it calls the real, unmodified
`policy_analytics.synthetic_benchmark._generate_row` (the same call `generate_benchmark` makes, with
the same `random.Random(config.seed)` stream), builds an exposure indicator `X` for each trap's
`apparent_feature`, and fits two ordinary-least-squares linear-probability / linear models on
the generator's own output:

* **X-side:** `X ~ 1 + all admissible pool columns` (every `adjustment_eligible` manifest column
  except `X`'s own source column, plus the `booking_month` dummies that the adjustment
  representation does NOT contain). Per column *block* we report the Wald chi-square (equal to
  `df * F` for homoskedastic OLS), the partial R^2 `W / (W + residual_df)`, and the per-block
  coefficient. A confounder is only *implemented as a common cause* when it is significant on BOTH
  sides.
* **Y-side:** `contribution_margin_eur ~ 1 + X + the same pool`.

Reused by `tests/analytics/test_task105_generator_realization.py` (smaller n) and used by
`main()` to write `docs/benchmark/task-105-generator-realization-raw.json` (large n).
No gate, engine, threshold or generator source is modified. Pure stdlib + polars (numpy/scipy are
not project dependencies).

Usage: ``uv run python scripts/measure_task105_generator_realization.py``
"""

from __future__ import annotations

import csv
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from policy_analytics.synthetic_benchmark import (
    BenchmarkConfig,
    _generate_row,  # pyright: ignore[reportPrivateUsage]
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CLEAN_CSV = REPO_ROOT / "synthetic_data/reference/travel_bookings_clean.csv"
ANALYTICAL_MANIFEST = (
    REPO_ROOT / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/manifest.json"
)
FEATURE_TIMING = REPO_ROOT / "synthetic_data/metadata/feature_timing.json"
HIDDEN_TRUTH = REPO_ROOT / "synthetic_data/evaluation/hidden_ground_truth.json"
RAW_OUT = REPO_ROOT / "docs/benchmark/task-105-generator-realization-raw.json"

OUTCOME = "contribution_margin_eur"

#: Wald chi-square critical values at p = 0.001 for df = 1..12 (hard-coded: scipy is not a dep).
CHI2_CRIT_001: dict[int, float] = {
    1: 10.828,
    2: 13.816,
    3: 16.266,
    4: 18.467,
    5: 20.515,
    6: 22.458,
    7: 24.322,
    8: 26.124,
    9: 27.877,
    10: 29.588,
    11: 31.264,
    12: 32.909,
}

#: The five traps' exposure indicator, keyed by trap id: (source column, value used as X=1).
TRAP_EXPOSURE: dict[str, tuple[str, object]] = {
    "T01": ("manager", "Manager 2"),
    "T02": ("supplier", "Atlas"),
    "T03": ("acquisition_channel", "paid_search"),
    "T04": ("payment_method", "bank_transfer"),
    "T05": ("manual_exception", True),
}

DESTINATIONS = ("Lisbon", "Reykjavik", "Rome", "Tokyo", "Zanzibar")
CATEGORICAL_POOL = (
    "destination",
    "supplier",
    "product_category",
    "manager",
    "acquisition_channel",
    "customer_segment",
    "customer_type",
    "payment_method",
)
NUMERIC_POOL = (
    "customer_price_eur",
    "quoted_cost_eur",
    "discount_rate",
    "party_size",
    "trip_duration_days",
    "booking_lead_days",
    "installments",
)
BOOLEAN_POOL = ("manual_exception",)


def generate_rows(n: int, seed: int) -> pl.DataFrame:
    """Rows from the real `_generate_row`, exactly as `generate_benchmark` draws them."""
    config = BenchmarkConfig(seed=seed, row_count=n)
    rng = random.Random(config.seed)
    rows = [_generate_row(index, rng, config)[0] for index in range(n)]
    return _typed(pl.DataFrame(rows))


def load_delivered_clean() -> pl.DataFrame:
    """The committed generator output (`synthetic_data/reference/travel_bookings_clean.csv`)."""
    with CLEAN_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    frame = pl.DataFrame(rows)
    casts: dict[str, Any] = {
        "customer_price_eur": pl.Float64,
        "discount_rate": pl.Float64,
        "quoted_cost_eur": pl.Float64,
        "contribution_margin_eur": pl.Float64,
        "party_size": pl.Int64,
        "trip_duration_days": pl.Int64,
        "booking_lead_days": pl.Int64,
        "installments": pl.Int64,
    }
    frame = frame.with_columns([pl.col(c).cast(t) for c, t in casts.items()])
    frame = frame.with_columns(pl.col("manual_exception").str.to_lowercase() == "true")
    return _typed(frame)


def _typed(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(
        pl.col("booking_date").cast(pl.String).str.slice(5, 2).cast(pl.Int64).alias("booking_month")
    )


def manifest_adjustment_eligible() -> list[str]:
    payload = json.loads(ANALYTICAL_MANIFEST.read_text(encoding="utf-8"))
    return list(payload["validation_roles"]["adjustment_eligible"])


def manifest_feature_roles() -> dict[str, str]:
    payload = json.loads(FEATURE_TIMING.read_text(encoding="utf-8"))
    return {c["name"]: c["classification"] for c in payload["columns"]}


# --------------------------------------------------------------------------------------------
# Design matrix / OLS
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BlockSpec:
    name: str
    columns: tuple[str, ...]


def _design(frame: pl.DataFrame, exclude_source: str) -> tuple[pl.DataFrame, list[BlockSpec]]:
    """Standardized numeric design columns grouped in named blocks (one block per pool column,
    plus `booking_month`). Threshold indicators used by the generator (`lead<14`, `party>=5`,
    `trip>=14`) join the block of their base column so a threshold-shaped driver is captured."""
    exprs: list[pl.Expr] = []
    blocks: list[BlockSpec] = []

    def add(block: str, names_exprs: list[tuple[str, pl.Expr]]) -> None:
        cols: list[str] = []
        for cname, expr in names_exprs:
            exprs.append(expr.cast(pl.Float64).alias(cname))
            cols.append(cname)
        blocks.append(BlockSpec(block, tuple(cols)))

    for column in CATEGORICAL_POOL:
        if column == exclude_source:
            continue
        levels = sorted(frame[column].unique().to_list())
        add(
            column,
            [(f"{column}={lvl}", pl.col(column) == lvl) for lvl in levels[1:]],
        )
    for column in NUMERIC_POOL:
        if column == exclude_source:
            continue
        parts: list[tuple[str, pl.Expr]] = [(column, pl.col(column))]
        if column == "booking_lead_days":
            parts.append(("lead<14", pl.col(column) < 14))
        if column == "party_size":
            parts.append(("party>=5", pl.col(column) >= 5))
        if column == "trip_duration_days":
            parts.append(("trip>=14", pl.col(column) >= 14))
        add(column, parts)
    for column in BOOLEAN_POOL:
        if column == exclude_source:
            continue
        add(column, [(column, pl.col(column))])
    add(
        "booking_month",
        [(f"month={m}", pl.col("booking_month") == m) for m in range(2, 13)],
    )
    design = frame.select(exprs)
    return design, blocks


def _standardize(design: pl.DataFrame) -> pl.DataFrame:
    return design.select(
        [((pl.col(c) - pl.col(c).mean()) / pl.col(c).std()).alias(c) for c in design.columns]
    )


def _solve_inverse(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("singular design matrix")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [v / scale for v in aug[col]]
        for r in range(n):
            if r != col and aug[r][col] != 0.0:
                factor = aug[r][col]
                aug[r] = [a - factor * b for a, b in zip(aug[r], aug[col], strict=True)]
    return [row[n:] for row in aug]


@dataclass(frozen=True, slots=True)
class OlsFit:
    names: tuple[str, ...]
    beta: tuple[float, ...]
    cov: tuple[tuple[float, ...], ...]
    n: int
    rss: float
    tss: float

    def index(self, name: str) -> int:
        return self.names.index(name)


def ols(design: pl.DataFrame, y: pl.Series, *, standardize: bool = True) -> OlsFit:
    """OLS with intercept via normal equations (sums computed in polars)."""
    x = _standardize(design) if standardize else design
    n = x.height
    names = ("intercept", *x.columns)
    frame = x.with_columns(pl.lit(1.0).alias("intercept"), y.cast(pl.Float64).alias("__y"))
    order = ["intercept", *x.columns]
    p = len(order)
    exprs = [
        (pl.col(order[i]) * pl.col(order[j])).sum().alias(f"s_{i}_{j}")
        for i in range(p)
        for j in range(i, p)
    ]
    exprs += [(pl.col(order[i]) * pl.col("__y")).sum().alias(f"xy_{i}") for i in range(p)]
    exprs += [(pl.col("__y") ** 2).sum().alias("yy"), pl.col("__y").sum().alias("ysum")]
    sums = frame.select(exprs).row(0, named=True)
    xtx = [[0.0] * p for _ in range(p)]
    for i in range(p):
        for j in range(i, p):
            xtx[i][j] = xtx[j][i] = float(sums[f"s_{i}_{j}"])
    xty = [float(sums[f"xy_{i}"]) for i in range(p)]
    inv = _solve_inverse(xtx)
    beta = [sum(inv[i][j] * xty[j] for j in range(p)) for i in range(p)]
    rss = float(sums["yy"]) - sum(b * v for b, v in zip(beta, xty, strict=True))
    tss = float(sums["yy"]) - float(sums["ysum"]) ** 2 / n
    sigma2 = rss / (n - p)
    cov = tuple(tuple(sigma2 * v for v in row) for row in inv)
    return OlsFit(names, tuple(beta), cov, n, rss, tss)


def block_wald(fit: OlsFit, columns: tuple[str, ...]) -> dict[str, float]:
    idx = [fit.index(c) for c in columns]
    sub = [[fit.cov[i][j] for j in idx] for i in idx]
    inv = _solve_inverse(sub)
    b = [fit.beta[i] for i in idx]
    wald = sum(b[i] * inv[i][j] * b[j] for i in range(len(idx)) for j in range(len(idx)))
    df = len(idx)
    resid_df = fit.n - len(fit.names)
    crit = CHI2_CRIT_001.get(df, float("inf"))
    return {
        "df": float(df),
        "wald_chi2": wald,
        "chi2_crit_p001": crit,
        "significant_p001": float(wald > crit),
        "partial_r2": wald / (wald + resid_df),
    }


# --------------------------------------------------------------------------------------------
# Per-trap measurement
# --------------------------------------------------------------------------------------------


def catalogue_confounders(trap_id: str) -> list[str]:
    payload = json.loads(HIDDEN_TRUTH.read_text(encoding="utf-8"))
    trap = next(t for t in payload["confounding_traps"] if t["id"] == trap_id)
    return list(trap["confounded_by"])


def exposure_mask(frame: pl.DataFrame, trap_id: str) -> pl.Series:
    column, value = TRAP_EXPOSURE[trap_id]
    return (frame[column] == value).cast(pl.Float64).alias("X")


def measure_trap(frame: pl.DataFrame, trap_id: str) -> dict[str, Any]:
    """Per-block X-side and Y-side dependence for one trap on `frame` (real generator output)."""
    source, _ = TRAP_EXPOSURE[trap_id]
    x = exposure_mask(frame, trap_id)
    design, blocks = _design(frame, source)
    x_fit = ols(design, x)
    y = frame[OUTCOME]
    y_design = design.with_columns(x.alias("X"))
    y_fit = ols(y_design, y)
    result_blocks: dict[str, Any] = {}
    for block in blocks:
        xs = block_wald(x_fit, block.columns)
        ys = block_wald(y_fit, block.columns)
        result_blocks[block.name] = {
            "x_side": xs,
            "y_side": ys,
            "both_sides_significant_p001": bool(xs["significant_p001"] and ys["significant_p001"]),
        }
    raw_diff = float(y.filter(x == 1.0).mean() or 0.0) - float(y.filter(x == 0.0).mean() or 0.0)  # pyright: ignore[reportArgumentType]
    # Adjusted X coefficient in EUR, X left unstandardized: (a) whole admissible pool,
    # (b) only the trap's catalogued `confounded_by` blocks (`booking_month` dummies included as an
    # oracle even though the adjustment representation lacks them).
    x_unstd = _adjusted_x_coefficient(design, x, y)
    catalogued = set(catalogue_confounders(trap_id))
    catalogued_cols = [c for b in blocks if b.name in catalogued for c in b.columns]
    x_catalogued = _adjusted_x_coefficient(design.select(catalogued_cols), x, y)
    return {
        "trap_id": trap_id,
        "n": frame.height,
        "x_rate": float(x.mean() or 0.0),  # pyright: ignore[reportArgumentType]
        "blocks": result_blocks,
        "raw_outcome_diff_eur": raw_diff,
        "pool_adjusted_outcome_diff_eur": x_unstd,
        "catalogued_blocks_adjusted_outcome_diff_eur": x_catalogued,
    }


def _adjusted_x_coefficient(design: pl.DataFrame, x: pl.Series, y: pl.Series) -> float:
    """Coefficient of X in `Y ~ X + standardized pool` (X left unstandardized)."""
    std = _standardize(design).with_columns(x.alias("X"))
    frame = std.with_columns(pl.lit(1.0).alias("intercept"), y.cast(pl.Float64).alias("__y"))
    order = ["intercept", "X", *design.columns]
    p = len(order)
    exprs = [
        (pl.col(order[i]) * pl.col(order[j])).sum().alias(f"s_{i}_{j}")
        for i in range(p)
        for j in range(i, p)
    ]
    exprs += [(pl.col(order[i]) * pl.col("__y")).sum().alias(f"xy_{i}") for i in range(p)]
    sums = frame.select(exprs).row(0, named=True)
    xtx = [[0.0] * p for _ in range(p)]
    for i in range(p):
        for j in range(i, p):
            xtx[i][j] = xtx[j][i] = float(sums[f"s_{i}_{j}"])
    xty = [float(sums[f"xy_{i}"]) for i in range(p)]
    inv = _solve_inverse(xtx)
    return sum(inv[1][j] * xty[j] for j in range(p))


def indicator_rates(frame: pl.DataFrame, trap_id: str) -> dict[str, Any]:
    """Marginal exposure rates by the generator's own driver indicators (context for the table)."""
    x = exposure_mask(frame, trap_id)
    lead = frame["booking_lead_days"]
    dest_hi = frame["destination"].is_in(["Tokyo", "Zanzibar"])
    indicators: dict[str, pl.Series] = {
        "dest_in_Tokyo_Zanzibar": dest_hi,
        "destination=Tokyo": frame["destination"] == "Tokyo",
        "lead_lt_14": lead < 14,
        "party_ge_5": frame["party_size"] >= 5,
        "trip_ge_14": frame["trip_duration_days"] >= 14,
        "booking_month_in_summer_6_7_8": frame["booking_month"].is_in([6, 7, 8]),
        "booking_month_in_winter_1_2_12": frame["booking_month"].is_in([1, 2, 12]),
    }
    out: dict[str, Any] = {}
    for name, mask in indicators.items():
        r1 = float(x.filter(mask).mean() or 0.0)  # pyright: ignore[reportArgumentType]
        r0 = float(x.filter(~mask).mean() or 0.0)  # pyright: ignore[reportArgumentType]
        y = frame[OUTCOME]
        y1 = float(y.filter(mask).mean() or 0.0)  # pyright: ignore[reportArgumentType]
        y0 = float(y.filter(~mask).mean() or 0.0)  # pyright: ignore[reportArgumentType]
        out[name] = {
            "rate_if_true": r1,
            "rate_if_false": r0,
            "rate_diff": r1 - r0,
            "outcome_mean_diff_eur": y1 - y0,
        }
    return out


def generator_matches_delivered() -> dict[str, Any]:
    """Regenerate with the default config (the committed dataset's seed/row_count) and compare it
    to `travel_bookings_clean.csv`: proves the measured generator IS the one that made the data."""
    config = BenchmarkConfig()
    regenerated = generate_rows(config.row_count, config.seed)
    delivered = load_delivered_clean()
    columns = [
        "booking_id",
        "destination",
        "supplier",
        "manager",
        "manual_exception",
        "payment_method",
        "acquisition_channel",
        "party_size",
        "trip_duration_days",
        "booking_lead_days",
        "contribution_margin_eur",
    ]
    mismatches = {c: int((regenerated[c] != delivered[c]).sum()) for c in columns}
    return {"rows": delivered.height, "mismatching_rows_by_column": mismatches}


def generator_score_rates(frame: pl.DataFrame, trap_id: str) -> dict[str, dict[str, float]]:
    """Measured P(X=1) (or the named downstream rate) in the strata that the generator's own code
    defines for this trap. Keys are stable strata names used by the manifests' `expected_rates`."""
    x = exposure_mask(frame, trap_id)
    dest_hi = frame["destination"].is_in(["Tokyo", "Zanzibar"])
    lead_lt14 = frame["booking_lead_days"] < 14
    party_ge5 = frame["party_size"] >= 5
    trip_ge14 = frame["trip_duration_days"] >= 14
    strata: dict[str, pl.Series] = {}
    if trap_id == "T01":
        strata = {
            "neither(dest_not_TZ,lead>=14)": ~dest_hi & ~lead_lt14,
            "either(dest_TZ or lead<14)": dest_hi | lead_lt14,
            "party_ge5_given_neither": ~dest_hi & ~lead_lt14 & party_ge5,
            "party_lt5_given_neither": ~dest_hi & ~lead_lt14 & ~party_ge5,
            "trip_ge14_given_neither": ~dest_hi & ~lead_lt14 & trip_ge14,
            "trip_lt14_given_neither": ~dest_hi & ~lead_lt14 & ~trip_ge14,
        }
    elif trap_id == "T02":
        tokyo = frame["destination"] == "Tokyo"
        summer = frame["booking_month"].is_in([6, 7, 8])
        winter = frame["booking_month"].is_in([1, 2, 12])
        strata = {
            "trip<14,not_Tokyo": ~trip_ge14 & ~tokyo,
            "trip>=14,not_Tokyo": trip_ge14 & ~tokyo,
            "trip<14,Tokyo": ~trip_ge14 & tokyo,
            "trip>=14,Tokyo": trip_ge14 & tokyo,
            "month_winter_given_trip<14,not_Tokyo": winter & ~trip_ge14 & ~tokyo,
            "month_summer_given_trip<14,not_Tokyo": summer & ~trip_ge14 & ~tokyo,
            "month_other_given_trip<14,not_Tokyo": ~winter & ~summer & ~trip_ge14 & ~tokyo,
        }
    elif trap_id == "T03":
        newc = frame["customer_type"] == "new"
        strata = {
            "customer_type=new": newc,
            "customer_type=returning": ~newc,
            "installments>=3": frame["installments"] >= 3,
            "installments<3": frame["installments"] < 3,
        }
    elif trap_id == "T04":
        strata = {
            "lead<14": lead_lt14,
            "lead>=14": ~lead_lt14,
            "dest_TZ_given_lead>=14": dest_hi & ~lead_lt14,
            "dest_not_TZ_given_lead>=14": ~dest_hi & ~lead_lt14,
        }
    elif trap_id == "T05":
        score = (
            dest_hi.cast(pl.Int64)
            + lead_lt14.cast(pl.Int64)
            + party_ge5.cast(pl.Int64)
            + trip_ge14.cast(pl.Int64)
        )
        strata = {f"complexity={k}": score == k for k in range(5)}
    out: dict[str, dict[str, float]] = {}
    for name, mask in strata.items():
        out[name] = {
            "rate": float(x.filter(mask).mean() or 0.0),  # pyright: ignore[reportArgumentType]
            "n": float(mask.sum()),
        }
    if trap_id == "T03":
        disc_hi = frame["discount_rate"] >= 0.12
        out["discount>=0.12_given_paid_search"] = {
            "rate": float(disc_hi.filter(x == 1.0).mean() or 0.0),  # pyright: ignore[reportArgumentType]
            "n": float((x == 1.0).sum()),
        }
        out["discount>=0.12_given_not_paid_search"] = {
            "rate": float(disc_hi.filter(x == 0.0).mean() or 0.0),  # pyright: ignore[reportArgumentType]
            "n": float((x == 0.0).sum()),
        }
    return out


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    large_n, large_seed = 400_000, 20260924
    payload: dict[str, Any] = {
        "task": "TASK-105 Phase 1",
        "note": "Measured from the real _generate_row; see script docstring.",
        "large_sample": {"n": large_n, "seed": large_seed},
        "traps": {},
        "generator_reproduces_delivered_csv_first_rows": None,
    }
    large = generate_rows(large_n, large_seed)
    delivered = load_delivered_clean()
    for trap_id in TRAP_EXPOSURE:
        print("measuring", trap_id)
        payload["traps"][trap_id] = {
            "large_sample": measure_trap(large, trap_id),
            "indicator_rates_large": indicator_rates(large, trap_id),
            "generator_score_rates_large": generator_score_rates(large, trap_id),
            "delivered_10k": measure_trap(delivered, trap_id),
        }
    payload["generator_reproduces_delivered_csv_first_rows"] = generator_matches_delivered()
    HIDDEN = json.loads(HIDDEN_TRUTH.read_text(encoding="utf-8"))
    payload["catalogue"] = {t["id"]: t for t in HIDDEN["confounding_traps"]}
    RAW_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", RAW_OUT)


if __name__ == "__main__":
    main()
