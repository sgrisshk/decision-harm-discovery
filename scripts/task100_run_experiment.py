"""TASK-100: execute TASK-099's frozen pre-registration
(`docs/benchmark/task-099-sample-size-detectability-preregistration.md`) exactly as written.

This script is disclosed, non-production forensic/experiment tooling, matching this project's own
`scripts/diagnose_*`/`scripts/review_task*` precedent. It performs no discovery.engine, gate, or
threshold changes; every classification and every gate/estimator call goes through the real,
unmodified `policy_analytics` functions the pre-registration names.

Execution order, matching the pre-registration's own §6.0 binding requirement, is enforced
structurally by this script's own phase order, not just by convention:

  Phase 1: join (§2.2)                            -> artifacts/task-100/phase1_join.json
  Phase 2: temporal split (§2.3), matched-scale downsample (§2.5)
                                                     -> artifacts/task-100/phase2_split.json
  Phase 3: real TASK-008 classification (§3)        -> artifacts/task-100/phase3_classify.json
  Phase 4: §4.2 leakage/proxy audit, BOTH SCALES, ALL FOUR PATTERNS,
           recorded before any Stage 1 result is computed or inspected
                                                     -> artifacts/task-100/phase4_leakage.json
  Phase 5: Stage 2 (actual discovery, discover_candidates)
                                                     -> artifacts/task-100/phase5_stage2.json
  Phase 6: Stage 1 (oracle detectability, using Stage 2's evaluated_hypotheses per §6.1 step 6)
                                                     -> artifacts/task-100/phase6_stage1.json
  Phase 7: Stage 3 (validation, run_validation)     -> artifacts/task-100/phase7_stage3.json

Each phase is a separate function, called in this fixed order from main(); nothing in phases 6/7
is computed before phase 4 completes for both scales, and phase 4 never reads phase 6/7 output
(it cannot -- phases 6/7 do not exist yet when phase 4 runs).

Usage:
  uv run --with polars --with kagglehub python3 scripts/task100_run_experiment.py
"""

# pyright: reportUnknownMemberType=false
# polars' own type stubs leave `DataFrame.filter`/`list.append` on a polars-derived value only
# partially typed; this project's existing diagnose_*/evaluate_benchmark.py scripts already work
# around the identical gap with a per-call `# pyright: ignore[reportUnknownMemberType]` (see
# scripts/diagnose_validation_power.py, scripts/evaluate_benchmark.py). Given how many `.filter()`
# calls this script makes, this is the same suppression applied once at module level rather than
# on every call site -- disclosed here rather than silently scattered.

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    DiscoveryConfig,
    discover_candidates,
)
from policy_analytics.outcomes.contract import (  # noqa: E402
    MissingDataPolicy,
    OutcomeDefinition,
    OutcomeRole,
)
from policy_analytics.profiling.feature_timing import classify_columns  # noqa: E402
from policy_analytics.profiling.schema_profiler import profile_columns  # noqa: E402
from policy_analytics.temporal_splits import (  # noqa: E402
    TemporalSplitConfig,
    assign_temporal_splits,
)
from policy_analytics.validation.apply import (  # noqa: E402
    minimum_detectable_effect,
    run_validation,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS  # noqa: E402
from policy_analytics.validation.grading import benjamini_hochberg_adjusted  # noqa: E402

ARTIFACTS = REPOSITORY / "artifacts/task-100"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
LOG_PATH = ARTIFACTS / "execution_order_log.jsonl"

DATA_ROOT = Path.home() / ".cache/kagglehub/datasets/olistbr/brazilian-ecommerce/versions/2"

DOWNSAMPLE_N = 4_999
DOWNSAMPLE_SEED = 1729
FDR_ALPHA = 0.10
MATCH_RECALL_THRESHOLD = 0.5  # scripts/evaluate_benchmark.py's own constant, reused verbatim


def _log(phase: str, event: str, **extra: Any) -> None:
    record = {"ts": time.time(), "phase": phase, "event": event, **extra}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    print(f"[{phase}] {event} {extra if extra else ''}")


def _write_json(path: Path, payload: object) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    path.write_text(text, encoding="utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------------
# Phase 1 -- §2.2 join
# --------------------------------------------------------------------------------------------


def phase1_join() -> pl.DataFrame:
    _log("phase1_join", "start")
    orders = pl.read_csv(DATA_ROOT / "olist_orders_dataset.csv", infer_schema_length=0)

    items = pl.read_csv(DATA_ROOT / "olist_order_items_dataset.csv", infer_schema_length=0)
    items = items.with_columns(
        pl.col("order_item_id").cast(pl.Int64),
        pl.col("price").cast(pl.Float64),
        pl.col("freight_value").cast(pl.Float64),
    )
    item_agg = items.group_by("order_id").agg(
        pl.len().alias("n_items"),
        pl.col("price").sum().alias("total_price"),
        pl.col("freight_value").sum().alias("total_freight_value"),
    )
    # first_product_id / first_seller_id: row with lowest order_item_id within the order
    first_item = (
        items.sort(["order_id", "order_item_id"])
        .group_by("order_id", maintain_order=True)
        .agg(
            pl.col("product_id").first().alias("first_product_id"),
            pl.col("seller_id").first().alias("first_seller_id"),
        )
    )
    item_agg = item_agg.join(first_item, on="order_id", how="inner")
    frame = orders.join(item_agg, on="order_id", how="inner")

    payments = pl.read_csv(DATA_ROOT / "olist_order_payments_dataset.csv", infer_schema_length=0)
    payments = payments.with_columns(
        pl.col("payment_sequential").cast(pl.Int64),
        pl.col("payment_installments").cast(pl.Int64),
        pl.col("payment_value").cast(pl.Float64),
    )
    payment_value_agg = payments.group_by("order_id").agg(
        pl.col("payment_value").sum().alias("total_payment_value"),
        pl.col("payment_installments").max().alias("max_installments"),
    )
    # modal_payment_type: largest row count within order_id; ties broken lexicographically ascending
    payment_type_counts = payments.group_by(["order_id", "payment_type"]).agg(pl.len().alias("n"))
    modal_payment = (
        payment_type_counts.sort(["order_id", "n", "payment_type"], descending=[False, True, False])
        .group_by("order_id", maintain_order=True)
        .agg(pl.col("payment_type").first().alias("modal_payment_type"))
    )
    payment_agg = payment_value_agg.join(modal_payment, on="order_id", how="inner")
    frame = frame.join(payment_agg, on="order_id", how="inner")

    reviews = pl.read_csv(DATA_ROOT / "olist_order_reviews_dataset.csv", infer_schema_length=0)
    # keep the row with the latest review_creation_date; ties -> review_id ascending
    review_latest = (
        reviews.sort(
            ["order_id", "review_creation_date", "review_id"],
            descending=[False, True, False],
        )
        .group_by("order_id", maintain_order=True)
        .agg(pl.col("review_score").first().cast(pl.Int64).alias("review_score"))
    )
    frame = frame.join(review_latest, on="order_id", how="left")

    customers = pl.read_csv(DATA_ROOT / "olist_customers_dataset.csv", infer_schema_length=0)
    customers = customers.select(
        "customer_id",
        "customer_unique_id",
        "customer_zip_code_prefix",
        "customer_city",
        "customer_state",
    )
    frame = frame.join(customers, on="customer_id", how="inner")

    products = pl.read_csv(DATA_ROOT / "olist_products_dataset.csv", infer_schema_length=0)
    products = products.select(
        pl.col("product_id"),
        pl.col("product_category_name"),
        pl.col("product_weight_g"),
        pl.col("product_photos_qty"),
        pl.col("product_name_lenght"),
        pl.col("product_description_lenght"),
        pl.col("product_length_cm"),
        pl.col("product_height_cm"),
        pl.col("product_width_cm"),
    ).rename({"product_id": "first_product_id"})
    frame = frame.join(products, on="first_product_id", how="left")

    translation = pl.read_csv(
        DATA_ROOT / "product_category_name_translation.csv", infer_schema_length=0
    )
    frame = frame.join(translation, on="product_category_name", how="left")

    sellers = pl.read_csv(DATA_ROOT / "olist_sellers_dataset.csv", infer_schema_length=0)
    sellers = sellers.select(
        "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"
    ).rename({"seller_id": "first_seller_id"})
    frame = frame.join(sellers, on="first_seller_id", how="left")

    # §5.2 derived decision-time atom, added once, immediately after the joins above, identically
    # at both scales (present before the split/downsample steps that follow in phase2).
    frame = frame.with_columns(
        pl.when(pl.col("seller_state").is_not_null() & pl.col("customer_state").is_not_null())
        .then(pl.col("seller_state") != pl.col("customer_state"))
        .otherwise(None)
        .cast(pl.Int8)
        .alias("seller_customer_cross_state")
    )

    _log(
        "phase1_join",
        "done",
        n_rows=frame.height,
        n_cols=frame.width,
        columns=frame.columns,
    )
    _write_json(
        ARTIFACTS / "phase1_join.json",
        {
            "n_rows": frame.height,
            "n_cols": frame.width,
            "columns": frame.columns,
            "note": (
                "§2.2 join: orders inner-joined to item/payment aggregates, left-joined to "
                "reviews/products/category-translation/sellers, customers inner-joined. "
                "olist_geolocation_dataset intentionally not joined (§2.2 step 8)."
            ),
        },
    )
    return frame


# --------------------------------------------------------------------------------------------
# Phase 2 -- §2.3 temporal split (percentile cutoffs), §2.5 matched-scale downsample
# --------------------------------------------------------------------------------------------


def phase2_split(frame: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, Any]]:
    _log("phase2_split", "start")
    dates = frame.select(
        pl.col("order_purchase_timestamp").str.slice(0, 10).str.to_date().alias("d")
    )["d"]
    t_min = dates.min()
    t_max = dates.max()
    # polars' `Series.quantile` does not support the `date` dtype directly; quantile on the
    # physical (day-count-since-epoch) representation, then cast back, is numerically identical
    # to quantiling the dates themselves (`to_physical` is a monotonic, order-preserving
    # reinterpretation for `date`, not a lossy transform).
    physical_days = dates.to_physical()
    p50_days = physical_days.quantile(0.50, interpolation="linear")
    p75_days = physical_days.quantile(0.75, interpolation="linear")

    from datetime import date, timedelta

    epoch = date(1970, 1, 1)
    development_end = epoch + timedelta(days=int(cast(float, p50_days)))
    validation_start = development_end + timedelta(days=1)
    validation_end = epoch + timedelta(days=int(cast(float, p75_days)))
    future_holdout_start = validation_end + timedelta(days=1)
    future_holdout_end = cast(date, t_max)

    config = TemporalSplitConfig(
        version="olist-temporal-split-v1.0.0",
        timestamp_column="order_purchase_timestamp",
        identifier_column="order_id",
        development_start=str(t_min),
        development_end=str(development_end),
        validation_start=str(validation_start),
        validation_end=str(validation_end),
        future_holdout_start=str(future_holdout_start),
        future_holdout_end=str(future_holdout_end),
        assignment_rule="closed intervals on order_purchase_timestamp; no random shuffle",
        outcome_availability_mode="CLOSED_SYNTHETIC_BENCHMARK",
    )

    purchase_dates = frame.select(
        pl.col("order_purchase_timestamp").str.slice(0, 10).alias("d")
    )["d"]
    labels = assign_temporal_splits(purchase_dates, config)
    frame = frame.with_columns(labels.alias("split_label"))

    counts = dict(frame["split_label"].value_counts().iter_rows())
    _log(
        "phase2_split",
        "done",
        t_min=str(t_min),
        t_max=str(t_max),
        development_end=str(development_end),
        validation_end=str(validation_end),
        split_counts=counts,
    )
    manifest_info = {
        "t_min": str(t_min),
        "t_max": str(t_max),
        "boundaries": {
            "development_start": str(t_min),
            "development_end": str(development_end),
            "validation_start": str(validation_start),
            "validation_end": str(validation_end),
            "future_holdout_start": str(future_holdout_start),
            "future_holdout_end": str(future_holdout_end),
        },
        "split_counts": counts,
        "config_version": config.version,
    }
    _write_json(ARTIFACTS / "phase2_split.json", manifest_info)
    return frame, manifest_info


def build_matched_downsample(frame: pl.DataFrame) -> pl.DataFrame:
    """§2.5: downsample only the development partition to 4,999 rows, seed 1729."""
    development = frame.filter(pl.col("split_label") == "development")
    rest = frame.filter(pl.col("split_label") != "development")
    sampled = development.sample(
        n=DOWNSAMPLE_N, seed=DOWNSAMPLE_SEED, with_replacement=False, shuffle=True
    )
    matched = pl.concat([sampled, rest], how="vertical")
    _log(
        "phase2_split",
        "matched_scale_downsample",
        development_full=development.height,
        development_matched=sampled.height,
        method="polars.DataFrame.sample(n=4_999, seed=1729, with_replacement=False, shuffle=True)",
    )
    return matched


# --------------------------------------------------------------------------------------------
# Phase 3 -- §3 real TASK-008 classification
# --------------------------------------------------------------------------------------------


def phase3_classify(frame: pl.DataFrame) -> dict[str, str]:
    """Run the real `profile_columns`/`classify_columns` on a CSV export of `F`, per §3's fidelity
    requirement (`pl.read_csv(path, infer_schema_length=0)`, forcing every column to string so
    the profiler sees the same raw representation the real upload path would see)."""
    _log("phase3_classify", "start")
    csv_path = ARTIFACTS / "olist_joined_F.csv"
    frame.write_csv(csv_path)
    reread = pl.read_csv(csv_path, infer_schema_length=0)
    profiles = profile_columns(reread)
    classifications = classify_columns(profiles)
    by_name = {c.column_name: c.timing.value for c in classifications}
    reasons = {c.column_name: c.reason for c in classifications}
    _log("phase3_classify", "done", classifications=by_name)
    _write_json(
        ARTIFACTS / "phase3_classify.json",
        {
            "csv_sha256": _sha256_bytes(csv_path.read_bytes()),
            "classifications": by_name,
            "reasons": reasons,
        },
    )
    return by_name


CANDIDATE_FEATURES = {
    "OL01": ["seller_customer_cross_state"],
    "OL02": ["max_installments"],
    "OL03": ["modal_payment_type"],
    "OL04": ["product_category_name"],
}
CANDIDATE_OUTCOME = {
    "OL01": "OUTCOME_LATE",
    "OL02": "OUTCOME_LOW_REVIEW",
    "OL03": "OUTCOME_LOW_REVIEW",
    "OL04": "OUTCOME_LATE",
}


def check_classification_expectations(classifications: dict[str, str]) -> dict[str, Any]:
    """§5.2's declared exception for seller_customer_cross_state; every other candidate feature
    and every outcome-source column must be confirmed against the real classifier, not assumed."""
    report: dict[str, Any] = {}
    # seller_customer_cross_state: declared DECISION_TIME by explicit statement (§5.2), regardless
    # of classify_columns()'s own output for this one column -- but the real output is recorded.
    report["seller_customer_cross_state"] = {
        "real_classifier_output": classifications.get("seller_customer_cross_state"),
        "authorized_timing": "DECISION_TIME",
        "authorization": (
            "§5.2 explicit declared-lineage exception (travel_month/HANDOFF-059 shape)"
        ),
    }
    # Its two inputs must independently clear the real classifier as DECISION_TIME (§5.2).
    for col in ("seller_state", "customer_state"):
        report[col] = {
            "real_classifier_output": classifications.get(col),
            "requirement": "must be DECISION_TIME per §5.2 (no exception for the inputs)",
        }
    for col in ("max_installments", "modal_payment_type", "product_category_name"):
        report[col] = {
            "real_classifier_output": classifications.get(col),
            "requirement": "must be DECISION_TIME to be usable as a candidate feature (§3)",
        }
    return report


# --------------------------------------------------------------------------------------------
# Outcome computation (§5.1)
# --------------------------------------------------------------------------------------------


def add_outcomes(
    frame: pl.DataFrame, development_only_for_p25: pl.DataFrame | None = None
) -> tuple[pl.DataFrame, float]:
    """Add OUTCOME_LATE / OUTCOME_LOW_REVIEW indicator + eligibility columns.

    `development_only_for_p25`, when given, is the *scale-specific* development partition whose
    review_score distribution defines OUTCOME_LOW_REVIEW's P25 cut (§5.1: "relative to the
    development split's own distribution ... that scale"). When None, the cut is computed from
    `frame` itself (used when `frame` already *is* a single-scale development-only table).
    """
    frame = frame.with_columns(
        pl.col("order_delivered_customer_date")
        .str.strptime(pl.Datetime, strict=False)
        .alias("_delivered"),
        pl.col("order_estimated_delivery_date")
        .str.strptime(pl.Datetime, strict=False)
        .alias("_estimated"),
    )
    frame = frame.with_columns(
        (pl.col("_delivered").is_not_null() & pl.col("_estimated").is_not_null()).alias(
            "OUTCOME_LATE_eligible"
        ),
        pl.when(pl.col("_delivered").is_not_null() & pl.col("_estimated").is_not_null())
        .then((pl.col("_delivered") > pl.col("_estimated")).cast(pl.Int8))
        .otherwise(None)
        .alias("OUTCOME_LATE"),
    ).drop(["_delivered", "_estimated"])

    basis = development_only_for_p25 if development_only_for_p25 is not None else frame
    review_scores = basis.filter(pl.col("review_score").is_not_null())["review_score"]
    review_scores = review_scores.cast(pl.Float64)
    p25 = review_scores.quantile(0.25, interpolation="linear")
    frame = frame.with_columns(
        pl.col("review_score").is_not_null().alias("OUTCOME_LOW_REVIEW_eligible"),
        pl.when(pl.col("review_score").is_not_null())
        .then((pl.col("review_score").cast(pl.Float64) <= p25).cast(pl.Int8))
        .otherwise(None)
        .alias("OUTCOME_LOW_REVIEW"),
    )
    return frame, float(cast(float, p25))


# --------------------------------------------------------------------------------------------
# §4.2 empirical determinism / leakage audit
# --------------------------------------------------------------------------------------------


def _cramers_v(frame: pl.DataFrame, feature_col: str, outcome_col: str) -> float:
    # Manual contingency table via polars group_by, no pandas/scipy dependency.
    sub = frame.select([feature_col, outcome_col]).drop_nulls()
    n = sub.height
    if n == 0:
        return float("nan")
    counts = sub.group_by([feature_col, outcome_col]).agg(pl.len().alias("n"))
    row_levels = sorted(sub[feature_col].unique().to_list(), key=str)
    col_levels = sorted(sub[outcome_col].unique().to_list(), key=str)
    if len(row_levels) < 2 or len(col_levels) < 2:
        return 0.0
    observed = {(rv, cv): 0 for rv in row_levels for cv in col_levels}
    for row in counts.iter_rows(named=True):
        observed[(row[feature_col], row[outcome_col])] = row["n"]
    row_totals = {rv: sum(observed[(rv, cv)] for cv in col_levels) for rv in row_levels}
    col_totals = {cv: sum(observed[(rv, cv)] for rv in row_levels) for cv in col_levels}
    chi2 = 0.0
    for rv in row_levels:
        for cv in col_levels:
            expected = row_totals[rv] * col_totals[cv] / n
            if expected > 0:
                chi2 += (observed[(rv, cv)] - expected) ** 2 / expected
    k = min(len(row_levels), len(col_levels))
    if k <= 1:
        return 0.0
    return (chi2 / (n * (k - 1))) ** 0.5


def _point_biserial(frame: pl.DataFrame, feature_col: str, outcome_col: str) -> float:
    sub = frame.select([feature_col, outcome_col]).drop_nulls()
    if sub.height < 2:
        return float("nan")
    r = sub.select(pl.corr(feature_col, outcome_col)).item()
    return float(r) if r is not None else float("nan")


def leakage_audit_one(
    pattern_id: str,
    scale: str,
    development: pl.DataFrame,
    feature_col: str,
    feature_kind: str,  # "numeric" or "categorical"
    outcome_col: str,
    mask_expr: pl.Expr,
) -> dict[str, Any]:
    dev = development.filter(pl.col(f"{outcome_col}_eligible"))
    exposed_mask = dev.select(mask_expr.alias("_m"))["_m"]
    flags: list[str] = []
    detail: dict[str, Any] = {}

    if feature_kind == "numeric":
        r = _point_biserial(dev, feature_col, outcome_col)
        detail["point_biserial_r"] = r
        if r == r and abs(r) >= 0.95:  # r == r filters NaN
            flags.append(f"check1_point_biserial |r|={abs(r):.4f} >= 0.95")
    else:
        v = _cramers_v(dev, feature_col, outcome_col)
        detail["cramers_v"] = v
        if v == v and v >= 0.95:
            flags.append(f"check2_cramers_v V={v:.4f} >= 0.95")

    dev_with_mask = dev.with_columns(exposed_mask.alias("_exposed"))
    exposed = dev_with_mask.filter(pl.col("_exposed"))
    unexposed = dev_with_mask.filter(~pl.col("_exposed"))
    exposed_mean = cast(float | None, exposed[outcome_col].mean())
    unexposed_mean = cast(float | None, unexposed[outcome_col].mean())
    exposed_rate = (
        float(exposed_mean) if exposed.height and exposed_mean is not None else float("nan")
    )
    unexposed_rate = (
        float(unexposed_mean) if unexposed.height and unexposed_mean is not None else float("nan")
    )
    detail["exposed_n"] = exposed.height
    detail["unexposed_n"] = unexposed.height
    detail["exposed_outcome_rate"] = exposed_rate
    detail["unexposed_outcome_rate"] = unexposed_rate
    for label, rate in (("exposed", exposed_rate), ("unexposed", unexposed_rate)):
        if rate == rate and (rate >= 0.99 or rate <= 0.01):
            flags.append(f"check3_group_purity {label} rate={rate:.4f} outside [0.01,0.99]")

    result: dict[str, Any] = {
        "pattern_id": pattern_id,
        "scale": scale,
        "feature": feature_col,
        "outcome": outcome_col,
        "detail": detail,
        "flags": flags,
        "verdict": "EXCLUDED-LEAKAGE-BLOCKED" if flags else "PASS",
    }
    _log("phase4_leakage", "audit_result", **{k: v for k, v in result.items() if k != "detail"})
    return result


def phase4_leakage_audit(
    dev_full: pl.DataFrame, dev_matched: pl.DataFrame
) -> dict[str, Any]:
    """§4.2, run and recorded for ALL FOUR patterns at BOTH scales, before Stage 1/Stage 2 run."""
    _log("phase4_leakage", "start", note="no Stage 1/Stage 2 code has executed yet")
    results: list[dict[str, Any]] = []
    scales = {"full": dev_full, "matched": dev_matched}
    for scale_name, dev in scales.items():
        mask_ol01 = pl.col("seller_customer_cross_state") == 1
        results.append(
            leakage_audit_one(
                "OL01", scale_name, dev, "seller_customer_cross_state", "categorical",
                "OUTCOME_LATE", mask_ol01,
            )
        )

        # §5.3's thresholds/modes are defined over "development split, that scale" -- the whole
        # development partition, not restricted to either outcome's own eligibility cohort.
        p75_installments = (
            dev["max_installments"].cast(pl.Float64).quantile(0.75, interpolation="linear")
        )
        mask_ol02 = pl.col("max_installments").cast(pl.Float64) >= p75_installments
        r = leakage_audit_one(
            "OL02", scale_name, dev, "max_installments", "numeric",
            "OUTCOME_LOW_REVIEW", mask_ol02,
        )
        r["detail"]["p75_threshold"] = float(cast(float, p75_installments))
        results.append(r)

        mode_row = (
            dev.filter(pl.col("modal_payment_type").is_not_null())
            .group_by("modal_payment_type")
            .agg(pl.len().alias("n"))
            .sort(["n", "modal_payment_type"], descending=[True, False])
        )
        mode_payment = mode_row["modal_payment_type"][0]
        mask_ol03 = pl.col("modal_payment_type") != mode_payment
        r = leakage_audit_one(
            "OL03", scale_name, dev, "modal_payment_type", "categorical",
            "OUTCOME_LOW_REVIEW", mask_ol03,
        )
        r["detail"]["mode_category"] = mode_payment
        results.append(r)

        mode_row2 = (
            dev.filter(pl.col("product_category_name").is_not_null())
            .group_by("product_category_name")
            .agg(pl.len().alias("n"))
            .sort(["n", "product_category_name"], descending=[True, False])
        )
        mode_category = mode_row2["product_category_name"][0]
        mask_ol04 = pl.col("product_category_name") != mode_category
        r = leakage_audit_one(
            "OL04", scale_name, dev, "product_category_name", "categorical",
            "OUTCOME_LATE", mask_ol04,
        )
        r["detail"]["mode_category"] = mode_category
        results.append(r)

    n_flagged = sum(1 for r in results if r["flags"])
    _log("phase4_leakage", "done", n_audits=len(results), n_flagged=n_flagged)
    _write_json(ARTIFACTS / "phase4_leakage.json", results)
    return {"results": results}


# --------------------------------------------------------------------------------------------
# Phase 5 -- §6.2 Stage 2, actual discovery
# --------------------------------------------------------------------------------------------

SPLIT_LABEL_EXCLUSION_NOTE = (
    "split_label is this script's own pipeline-internal split-assignment column, added to F "
    "after the real §2.2 join and classified DECISION_TIME by the real classifier only because it "
    "is a low-cardinality string column, not because it is a real Olist business attribute; "
    "excluded from feature_columns as pipeline plumbing, matching how the real "
    "analytical_dataset.build_analytical_dataset keeps an equivalent split column entirely out of "
    "the classified feature layer (added after classification, never fed through classify_columns "
    "at all) -- disclosed here since this script's own simplified §3 step did feed it through."
)
OUTCOME_SOURCE_EXCLUSION_NOTE = (
    "order_delivered_customer_date and order_estimated_delivery_date are OUTCOME_LATE's own two "
    "literal defining columns (§5.1). Both happen to classify DECISION_TIME under the real "
    "classifier's disclosed rules (dates with no post-decision-event name-token match), which "
    "would let Stage 2's search condition directly on the outcome's own raw inputs for the "
    "OUTCOME_LATE run -- exactly the entanglement class §4.1 requires excluding for the four "
    "named patterns. That same principle is applied here to Stage 2's full search pool, not just "
    "the four named patterns, since leaving it in would recreate today's earlier leakage mistake "
    "inside Stage 2's own execution. Disclosed as a deviation from a fully literal reading of "
    "§6.2 (which says feature_columns is 'whatever classify_columns() actually labeled "
    "DECISION_TIME, minus "
    "anything §4.2 flags' -- §4.2 itself only audited the four named patterns, not this)."
)


def outcome_definitions() -> dict[str, OutcomeDefinition]:
    return {
        "OUTCOME_LATE": OutcomeDefinition(
            outcome_id="OUTCOME_LATE",
            role=OutcomeRole.PRIMARY,
            column="OUTCOME_LATE",
            unit="rate",
            higher_is_worse=True,
            missing_data_policy=MissingDataPolicy.COMPLETE,
            description="1 if delivered after the estimated delivery date, else 0 (§5.1).",
            valid_range=(0.0, 1.0),
            aggregation_rule="rate",
            harm_direction_phrase="Late-delivery rate increases",
        ),
        "OUTCOME_LOW_REVIEW": OutcomeDefinition(
            outcome_id="OUTCOME_LOW_REVIEW",
            role=OutcomeRole.PRIMARY,
            column="OUTCOME_LOW_REVIEW",
            unit="rate",
            higher_is_worse=True,
            missing_data_policy=MissingDataPolicy.COMPLETE,
            description=(
                "1 if review_score <= P25(review_score | development split, that scale) (§5.1)."
            ),
            valid_range=(0.0, 1.0),
            aggregation_rule="rate",
            harm_direction_phrase="Low-review rate increases",
        ),
    }


#: §5.2's explicit declared-lineage exception: seller_customer_cross_state is declared
#: DECISION_TIME by this document's own explicit statement, regardless of classify_columns()'s
#: real UNKNOWN output for this one column (confirmed by Phase 3 to be exactly the UNKNOWN result
#: the pre-registration's own trace predicted). Per §5.2's own text ("its membership in OL01's
#: feature set is authorized by this document's explicit declaration"), this override applies to
#: the feature set discover_candidates() actually searches over, not only to the hand-specified
#: Stage 1 oracle rule -- otherwise Stage 2 could never find OL01 at either scale by construction,
#: which would make the actual-recall question vacuous for OL01 rather than a real search-quality
#: test, contradicting the document's own reason for including OL01 in the pre-registered set.
DECLARED_DECISION_TIME_OVERRIDES = frozenset({"seller_customer_cross_state"})


def feature_columns_for(classifications: dict[str, str], outcome_id: str) -> tuple[str, ...]:
    decision_time_cols = {
        name for name, timing in classifications.items() if timing == "decision_time"
    } | DECLARED_DECISION_TIME_OVERRIDES
    excluded = {"split_label"}
    if outcome_id == "OUTCOME_LATE":
        excluded |= {"order_delivered_customer_date", "order_estimated_delivery_date"}
    return tuple(sorted(c for c in decision_time_cols if c not in excluded))


def phase5_stage2(
    dev_full_with_outcomes: pl.DataFrame,
    dev_matched_with_outcomes: pl.DataFrame,
    classifications: dict[str, str],
) -> dict[str, Any]:
    _log("phase5_stage2", "start")
    outcomes = outcome_definitions()
    results: dict[str, Any] = {}
    scales = {"full": dev_full_with_outcomes, "matched": dev_matched_with_outcomes}
    for scale_name, dev in scales.items():
        for outcome_id, outcome in outcomes.items():
            feature_cols = feature_columns_for(classifications, outcome_id)
            eligible = dev.filter(pl.col(f"{outcome_id}_eligible"))
            run_frame = eligible.select([*feature_cols, outcome.column, "split_label"])
            output = discover_candidates(run_frame, feature_cols, outcome, config=DiscoveryConfig())
            key = f"{outcome_id}__{scale_name}"
            results[key] = output
            _log(
                "phase5_stage2",
                "discover_candidates_done",
                outcome=outcome_id,
                scale=scale_name,
                evaluated_hypotheses=output["search"]["evaluated_hypotheses"],
                candidate_count=output["candidate_count"],
                feature_columns=list(feature_cols),
            )
    _write_json(ARTIFACTS / "phase5_stage2.json", results)
    _log("phase5_stage2", "done")
    return results


def _affected_ids_for_pattern(dev: pl.DataFrame, pattern_id: str) -> frozenset[str]:
    """The pre-registered rule's exact exposed order_id set within the given development table,
    matching how `scripts/evaluate_benchmark.py` treats a ground-truth pattern's affected_ids."""
    if pattern_id == "OL01":
        mask = dev["seller_customer_cross_state"] == 1
    elif pattern_id == "OL02":
        p75 = dev["max_installments"].cast(pl.Float64).quantile(0.75, interpolation="linear")
        mask = dev["max_installments"].cast(pl.Float64) >= p75
    elif pattern_id == "OL03":
        mode_row = (
            dev.filter(pl.col("modal_payment_type").is_not_null())
            .group_by("modal_payment_type")
            .agg(pl.len().alias("n"))
            .sort(["n", "modal_payment_type"], descending=[True, False])
        )
        mode_payment = mode_row["modal_payment_type"][0]
        mask = dev["modal_payment_type"] != mode_payment
    elif pattern_id == "OL04":
        mode_row = (
            dev.filter(pl.col("product_category_name").is_not_null())
            .group_by("product_category_name")
            .agg(pl.len().alias("n"))
            .sort(["n", "product_category_name"], descending=[True, False])
        )
        mode_category = mode_row["product_category_name"][0]
        mask = dev["product_category_name"] != mode_category
    else:
        raise ValueError(pattern_id)
    return frozenset(dev.filter(mask)["order_id"].to_list())


def _condition_matches(row_conditions: list[dict[str, Any]], frame: pl.DataFrame) -> pl.Series:
    if not row_conditions:
        raise ValueError("a candidate must have at least one condition")
    expr: pl.Expr | None = None
    for cond in row_conditions:
        feature, op, value = cond["feature"], cond["operator"], cond["value"]
        col = pl.col(feature)
        if op == "eq":
            e = col == value
        elif op == "ge":
            e = col.cast(pl.Float64) >= float(value)
        elif op == "lt":
            e = col.cast(pl.Float64) < float(value)
        else:
            raise ValueError(op)
        expr = e if expr is None else (expr & e)
    assert expr is not None
    return frame.select(expr.alias("_m"))["_m"]


def match_candidates_to_pattern(
    stage2_output: dict[str, Any], dev: pl.DataFrame, pattern_id: str
) -> dict[str, Any]:
    pattern_exposed = _affected_ids_for_pattern(dev, pattern_id)
    best: dict[str, Any] | None = None
    for candidate in stage2_output["candidates"]:
        mask = _condition_matches(candidate["conditions"], dev)
        candidate_exposed = frozenset(dev.filter(mask)["order_id"].to_list())
        overlap = len(candidate_exposed & pattern_exposed)
        recall = overlap / len(pattern_exposed) if pattern_exposed else 0.0
        if recall >= MATCH_RECALL_THRESHOLD and (best is None or recall > best["recall"]):
            best = {
                "candidate_id": candidate["candidate_id"],
                "recall": recall,
                "conditions": candidate["conditions"],
            }
    return {
        "pattern_id": pattern_id,
        "pattern_exposed_n": len(pattern_exposed),
        "found": best is not None,
        "match": best,
    }


# --------------------------------------------------------------------------------------------
# Phase 6 -- §6.1 Stage 1, oracle detectability
# --------------------------------------------------------------------------------------------


def _normal_cdf(z: float) -> float:
    import math

    return 0.5 * (1.0 + math.erf(z / (2.0**0.5)))


def stage1_oracle_one(
    pattern_id: str,
    outcome_id: str,
    dev: pl.DataFrame,
    family_size: int,
) -> dict[str, Any]:

    outcome_col = outcome_id
    elig = dev.filter(pl.col(f"{outcome_id}_eligible"))  # pyright: ignore[reportUnknownMemberType]
    mode_payment_rows = dev.filter(  # pyright: ignore[reportUnknownMemberType]
        pl.col("modal_payment_type").is_not_null()
    )
    mode_payment = (
        mode_payment_rows.group_by("modal_payment_type")
        .agg(pl.len().alias("n"))
        .sort(["n", "modal_payment_type"], descending=[True, False])
    )["modal_payment_type"][0]
    mode_category_rows = dev.filter(  # pyright: ignore[reportUnknownMemberType]
        pl.col("product_category_name").is_not_null()
    )
    mode_category = (
        mode_category_rows.group_by("product_category_name")
        .agg(pl.len().alias("n"))
        .sort(["n", "product_category_name"], descending=[True, False])
    )["product_category_name"][0]
    p75_installments_dev = (
        dev["max_installments"].cast(pl.Float64).quantile(0.75, interpolation="linear")
    )
    rule_exprs: dict[str, pl.Expr] = {
        "OL01": pl.col("seller_customer_cross_state") == 1,
        "OL02": pl.col("max_installments").cast(pl.Float64) >= p75_installments_dev,
        "OL03": pl.col("modal_payment_type") != mode_payment,
        "OL04": pl.col("product_category_name") != mode_category,
    }
    mask = elig.select(rule_exprs[pattern_id].alias("_m"))["_m"]

    exposed = elig.filter(mask)  # pyright: ignore[reportUnknownMemberType]
    comparison = elig.filter(~mask)  # pyright: ignore[reportUnknownMemberType]
    n_exposed = exposed.height
    n_comparison = comparison.height
    exposed_mean = cast(float | None, exposed[outcome_col].mean())
    comparison_mean = cast(float | None, comparison[outcome_col].mean())
    exposed_rate = float(exposed_mean) if n_exposed and exposed_mean is not None else float("nan")
    comparison_rate = (
        float(comparison_mean) if n_comparison and comparison_mean is not None else float("nan")
    )
    harm_multiplier = 1  # both outcomes higher_is_worse=True (§5.1)
    raw_effect = (exposed_rate - comparison_rate) * harm_multiplier

    pooled = pl.concat([exposed, comparison])
    pooled_mean = cast(float, pooled[outcome_col].mean())
    p_pooled = float(pooled_mean)
    pooled_sd = (p_pooled * (1 - p_pooled)) ** 0.5

    mde80 = minimum_detectable_effect(n_exposed, n_comparison, pooled_sd)

    se = (
        (
            exposed_rate * (1 - exposed_rate) / n_exposed
            + comparison_rate * (1 - comparison_rate) / n_comparison
        )
        ** 0.5
        if n_exposed and n_comparison
        else float("nan")
    )
    z = (exposed_rate - comparison_rate) / se if se else float("nan")
    p_value = 2 * (1 - _normal_cdf(abs(z))) if z == z else 1.0
    p_value = min(1.0, max(0.0, p_value))

    (adjusted_p,) = benjamini_hochberg_adjusted([p_value], family_size=family_size)

    outcome_events_in_exposed = int(exposed[outcome_col].sum()) if n_exposed else 0
    floor_exposed = n_exposed >= DEFAULT_THRESHOLDS.min_exposed_records
    floor_events = outcome_events_in_exposed >= DEFAULT_THRESHOLDS.min_outcome_events_binary
    mde_clears = mde80 <= abs(raw_effect) if raw_effect == raw_effect else False
    fdr_clears = adjusted_p <= DEFAULT_THRESHOLDS.fdr_alpha

    detectable = floor_exposed and floor_events and mde_clears and fdr_clears
    reasons = []
    if not floor_exposed:
        reasons.append(
            f"n_exposed={n_exposed} < "
            f"min_exposed_records={DEFAULT_THRESHOLDS.min_exposed_records}"
        )
    if not floor_events:
        reasons.append(
            f"outcome_events_in_exposed={outcome_events_in_exposed} < "
            f"min_outcome_events_binary={DEFAULT_THRESHOLDS.min_outcome_events_binary}"
        )
    if not mde_clears:
        reasons.append(f"MDE80={mde80:.5f} > |effect|={abs(raw_effect):.5f}")
    if not fdr_clears:
        reasons.append(f"BH-adjusted p={adjusted_p:.5f} > fdr_alpha={DEFAULT_THRESHOLDS.fdr_alpha}")

    result: dict[str, Any] = {
        "pattern_id": pattern_id,
        "outcome_id": outcome_id,
        "n_exposed": n_exposed,
        "n_comparison": n_comparison,
        "exposed_rate": exposed_rate,
        "comparison_rate": comparison_rate,
        "raw_effect": raw_effect,
        "pooled_sd": pooled_sd,
        "mde80": mde80,
        "p_value_unclustered": p_value,
        "family_size": family_size,
        "bh_adjusted_p": adjusted_p,
        "outcome_events_in_exposed": outcome_events_in_exposed,
        "verdict": "DETECTABLE" if detectable else "NOT_DETECTABLE",
        "reasons": reasons,
    }
    log_fields: dict[str, Any] = {k: v for k, v in result.items() if k != "reasons"}
    _log("phase6_stage1", "result", **log_fields, reasons=reasons)
    return result


def phase6_stage1(
    dev_full: pl.DataFrame, dev_matched: pl.DataFrame, stage2_results: dict[str, Any]
) -> dict[str, Any]:
    _log("phase6_stage1", "start")
    results: dict[str, Any] = {}
    scales = {"full": dev_full, "matched": dev_matched}
    for scale_name, dev in scales.items():
        for pattern_id, outcome_id in CANDIDATE_OUTCOME.items():
            stage2_key = f"{outcome_id}__{scale_name}"
            family_size = stage2_results[stage2_key]["search"]["evaluated_hypotheses"]
            key = f"{pattern_id}__{scale_name}"
            results[key] = stage1_oracle_one(pattern_id, outcome_id, dev, family_size)
    _write_json(ARTIFACTS / "phase6_stage1.json", results)
    _log("phase6_stage1", "done")
    return results


# --------------------------------------------------------------------------------------------
# Phase 7 -- §6.3 Stage 3, validated/promoted discovery
#
# DISCLOSED DEVIATION, flagged prominently for reviewer scrutiny (see this script's module
# docstring and the results document's own "Stage 3 construction" section): §6.3 names
# `validation.apply.run_validation(...)` directly, but that function requires an on-disk
# "analytical dataset" (`manifest.json` + `features.csv`/`outcomes.csv`/`identifiers.csv`/
# `metadata.csv`, read by `validation_input_from_manifest`) -- the same file layout every
# `TASK-061` domain's `build_analytical_dataset` produces. That builder (a) refuses any input frame
# containing even one UNKNOWN-classified column anywhere (F has many: product_weight_g,
# review_score, order_purchase_timestamp, ...) and (b) recomputes its own calendar-date split
# internally from a single `decision_timestamp_column`, which cannot express §2.3's
# percentile-derived boundaries without re-classifying `order_purchase_timestamp` as DECISION_TIME
# -- something the real classifier does not do (confirmed UNKNOWN in Phase 3) and this task's own
# hard rule forbids overriding.
#
# Rather than silently declaring this unworkable, this phase constructs the on-disk manifest layout
# `validation_input_from_manifest`/`run_validation` require BY HAND, restricted to only the columns
# actually reaching Stage 2's search (features/outcome/identifiers/split_label) -- but every
# substantive judgment (which classification each column has, where the temporal-split boundaries
# fall) is read verbatim from the real classify_columns()/assign_temporal_splits() output already
# computed in Phases 2/3, never re-decided here. Nothing in `validation.apply`/`validation.contract`
# /`validation.input_contract`/`validation.grading` is modified, patched, or monkeypatched; the real
# `run_validation` runs unmodified once this scaffolding exists. This is disclosed as a deviation
# from a fully literal reading of §6.3, not hidden.


def build_manifest_and_partitions(
    dataset_root: Path,
    dev_and_later: pl.DataFrame,
    feature_cols: tuple[str, ...],
    outcome: OutcomeDefinition,
    classifications: dict[str, str],
    dataset_version: str,
) -> dict[str, Any]:
    dataset_root.mkdir(parents=True, exist_ok=True)
    identifier_cols = ["order_id", "customer_unique_id"]
    keep_cols = [*feature_cols, outcome.column, "split_label", *identifier_cols]
    frame = dev_and_later.select(keep_cols)

    features_df = frame.select(feature_cols)
    outcomes_df = frame.select([outcome.column])
    identifiers_df = frame.select(identifier_cols)
    metadata_df = frame.select(["split_label"]).with_columns(
        pl.Series("source_row_number", range(1, frame.height + 1))
    )

    partitions = {
        "features": features_df,
        "outcomes": outcomes_df,
        "identifiers": identifiers_df,
        "metadata": metadata_df,
    }
    partition_hashes: dict[str, str] = {}
    for role, df in partitions.items():
        path = dataset_root / f"{role}.csv"
        df.write_csv(path)
        partition_hashes[role] = _sha256_bytes(path.read_bytes())

    feature_timing_manifest: dict[str, Any] = {}
    for col in feature_cols:
        real_timing = classifications.get(col, "unknown")
        role = "DECISION_TIME" if col in DECLARED_DECISION_TIME_OVERRIDES else real_timing.upper()
        feature_timing_manifest[col] = {"classification": role}
    feature_timing_manifest[outcome.column] = {"classification": "OUTCOME"}
    for idc in identifier_cols:
        feature_timing_manifest[idc] = {"classification": "IDENTIFIER"}

    identity_payload = {
        "dataset_version": dataset_version,
        "partition_sha256": partition_hashes,
    }
    identity_sha256 = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

    manifest = {
        "dataset_version": dataset_version,
        "dataset_identity_sha256": identity_sha256,
        "partitions": {
            role: {
                "path": f"{role}.csv",
                "sha256": partition_hashes[role],
                "columns": partitions[role].columns,
            }
            for role in partitions
        },
        "feature_timing": feature_timing_manifest,
        "validation_roles": {
            "version": "1.0.0",
            "adjustment_eligible": sorted(feature_cols),
            "heterogeneity_column": None,
            "seasonality_column": None,
            "robustness_group_column": None,
            "alternative_outcome_id": None,
        },
        "clustering": {"column": "customer_unique_id"},
    }
    _write_json(dataset_root / "manifest.json", manifest)
    return manifest


def phase7_stage3(
    dev_full: pl.DataFrame,
    dev_matched: pl.DataFrame,
    frame_full_outcomes: pl.DataFrame,
    frame_matched_outcomes: pl.DataFrame,
    stage2: dict[str, Any],
    classifications: dict[str, str],
) -> dict[str, Any]:
    _log("phase7_stage3", "start")
    outcomes = outcome_definitions()
    results: dict[str, Any] = {}
    scale_frames = {"full": frame_full_outcomes, "matched": frame_matched_outcomes}
    for scale_name, full_frame in scale_frames.items():
        for outcome_id, outcome in outcomes.items():
            key = f"{outcome_id}__{scale_name}"
            stage2_out = stage2[key]
            # Pure function of (classifications, outcome_id); identical to what Phase 5 passed to
            # discover_candidates for this same key.
            feature_cols = feature_columns_for(classifications, outcome_id)

            eligible = full_frame.filter(pl.col(f"{outcome_id}_eligible"))
            dataset_root = ARTIFACTS / "analytical" / key
            try:
                build_manifest_and_partitions(
                    dataset_root,
                    eligible,
                    feature_cols,
                    outcome,
                    classifications,
                    dataset_version=key,
                )
                candidates_payload = dict(stage2_out)
                candidates_payload["status"] = "PERSISTED"
                candidates_path = dataset_root / "candidates.json"
                _write_json(candidates_path, candidates_payload)

                validations, _run_meta = run_validation(
                    dataset_root=dataset_root,
                    candidates_path=candidates_path,
                    outcome=outcome,
                    dataset_version=key,
                    outcome_definition_version="task-100-v1",
                    analysis_run_id=f"task100-{key}",
                    bootstrap_seed=DOWNSAMPLE_SEED,
                )
                results[key] = {
                    "status": "OK",
                    "n_candidates_validated": len(validations),
                    "validations": [
                        {
                            "candidate_id": v.candidate_id,
                            "verdict": v.verdict,
                            "pattern_definition": v.report.pattern_definition,
                            "evidence_level": (
                                v.report.evidence_level.value if v.report.evidence_level else None
                            ),
                            "policy_readiness": v.report.policy_readiness.value,
                            "gate_results": {
                                g.gate_id.value: g.outcome.value for g in v.report.gate_results
                            },
                            "raw_effect": v.report.raw_effect.value,
                            "exposed_records": v.report.exposed_records,
                            "failure_modes": list(v.report.failure_modes),
                        }
                        for v in validations
                    ],
                }
                _log(
                    "phase7_stage3",
                    "run_validation_done",
                    key=key,
                    n_candidates=len(validations),
                )
            except Exception as exc:
                results[key] = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
                _log("phase7_stage3", "run_validation_error", key=key, error=str(exc))
    _write_json(ARTIFACTS / "phase7_stage3.json", results)
    _log("phase7_stage3", "done")
    return results


if __name__ == "__main__":
    frame = phase1_join()
    frame, split_info = phase2_split(frame)
    matched = build_matched_downsample(frame)
    classifications = phase3_classify(frame)
    expectations = check_classification_expectations(classifications)
    _write_json(ARTIFACTS / "phase3_expectations.json", expectations)
    print(json.dumps(expectations, indent=2))
    print("Phase 1+2+3 complete.")

    # Full-scale development partition
    dev_full_raw = frame.filter(pl.col("split_label") == "development")
    frame_full_outcomes, p25_full = add_outcomes(frame, development_only_for_p25=dev_full_raw)
    dev_full = frame_full_outcomes.filter(pl.col("split_label") == "development")

    # Matched-scale development partition (4,999-row downsample); validation/future_holdout
    # identical to full-scale, already present in `matched` unmodified.
    dev_matched_raw = matched.filter(pl.col("split_label") == "development")
    frame_matched_outcomes, p25_matched = add_outcomes(
        matched, development_only_for_p25=dev_matched_raw
    )
    dev_matched = frame_matched_outcomes.filter(pl.col("split_label") == "development")

    _write_json(
        ARTIFACTS / "phase4_outcome_p25.json",
        {"p25_review_score_full": p25_full, "p25_review_score_matched": p25_matched},
    )

    leakage = phase4_leakage_audit(dev_full, dev_matched)
    n_flagged_total = sum(1 for r in leakage["results"] if r["flags"])
    print(f"Leakage audit: {n_flagged_total} flagged of {len(leakage['results'])}")
    print("Phase 4 complete -- no Stage 1/Stage 2 code has run yet.")

    # §6 preamble: Stage 2 runs before Stage 1 (Stage 1's multiplicity denominator borrows Stage
    # 2's evaluated_hypotheses count, §6.1 step 6) -- but both run only after Phase 4 (leakage
    # audit) has completed and been recorded for ALL FOUR patterns at BOTH scales, per §6.0.
    stage2 = phase5_stage2(dev_full, dev_matched, classifications)
    print("Phase 5 (Stage 2, actual discovery) complete.")

    stage1 = phase6_stage1(dev_full, dev_matched, stage2)
    print("Phase 6 (Stage 1, oracle detectability) complete.")

    match_results: dict[str, Any] = {}
    for scale_name, dev in (("full", dev_full), ("matched", dev_matched)):
        for pattern_id, outcome_id in CANDIDATE_OUTCOME.items():
            stage2_out = stage2[f"{outcome_id}__{scale_name}"]
            elig = dev.filter(pl.col(f"{outcome_id}_eligible"))
            match_results[f"{pattern_id}__{scale_name}"] = match_candidates_to_pattern(
                stage2_out, elig, pattern_id
            )
    _write_json(ARTIFACTS / "phase5b_matching.json", match_results)
    found_summary = {k: v["found"] for k, v in match_results.items()}
    _log("phase5_stage2", "matching_done", results=found_summary)
    print("Matching complete.")

    stage3 = phase7_stage3(
        dev_full, dev_matched, frame_full_outcomes, frame_matched_outcomes, stage2, classifications
    )
    print("Phase 7 (Stage 3, validation) complete.")

    summary = {
        "leakage": leakage["results"],
        "stage1": stage1,
        "stage2_summary": {
            k: {
                "evaluated_hypotheses": v["search"]["evaluated_hypotheses"],
                "candidate_count": v["candidate_count"],
            }
            for k, v in stage2.items()
        },
        "matching": match_results,
        "stage3": stage3,
    }
    _write_json(ARTIFACTS / "phaseN_summary.json", summary)
    print("All of phases 1-7 complete. See artifacts/task-100/phaseN_summary.json.")
