"""CLI: baseline descriptive statistics on the analytical dataset, before discovery (TASK-014).

**Scope, deliberately narrow.** This is a data-understanding/sanity-check pass, not discovery and
not validation: overall feature distributions, outcome missingness/prevalence, and univariate
trends across four dimensions the task names explicitly — time, segment, supplier, manager. It
reports one column (or one column against `contribution_margin_eur`) at a time. It never searches
a conjunction of conditions, never reports an uncertainty interval or p-value, and never claims a
finding — that is `TASK-015`'s (candidate generation) and `TASK-018`/`TASK-019`'s (validation) job,
respectively. Every number here is `descriptive_observation`, the lowest evidence level
(`docs/analytics/validation-contract.md` `LANGUAGE_RULES`); nothing here is "a pattern."

Does not open `hidden_ground_truth.json` — there is no legitimate reason for a baseline profiling
pass to ever touch it, and it does not.

Reuses, rather than re-implements: `load_analytical_frame`/manifest feature roles/`SPLITS`
(`validation.apply`) and `summarize_group`/`mnar_bounds`/`OUTCOME_DEFINITIONS`
(`outcomes.aggregation`/`outcomes.contract`) — the same primitives `TASK-013`/`TASK-018` already
use and already have test coverage, so this script adds no new outcome-handling logic, only new
grouping/summary glue.

Full methodology and interpretation limits: `docs/analytics/baseline-statistics-v1.md`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402
from policy_analytics.outcomes import (  # noqa: E402
    OUTCOME_CONTRACT_VERSION,
    OUTCOME_DEFINITIONS,
    OutcomeDefinition,
    mnar_bounds,
    summarize_group,
)
from policy_analytics.outcomes.contract import MissingDataPolicy  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    SPLITS,
    load_analytical_frame,
)
from policy_analytics.validation.input_contract import validation_input_from_manifest  # noqa: E402

DEFAULT_DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
DEFAULT_OUTPUT_PATH = REPOSITORY / "artifacts/baseline/task-014-baseline-statistics.json"
DECISION_TIME_FEATURES = validation_input_from_manifest(DEFAULT_DATASET_ROOT).decision_time_features

#: booking_date/travel_date are DECISION_TIME features but calendar dates, not a distribution to
#: bucket by value — reported as a min/max range instead of a (huge-cardinality) value-count table.
DATE_COLUMNS: frozenset[str] = frozenset({"booking_date", "travel_date"})

#: The four trend dimensions the task names explicitly. Each is reported against the primary
#: outcome only (`contribution_margin_eur`) — a deliberate scope choice, not an oversight: full
#: per-outcome trend tables for every secondary outcome would multiply this report sevenfold for
#: little sanity-check value; `outcome_prevalence` already covers every outcome once, in full.
SEGMENT_TREND_COLUMNS: tuple[str, ...] = ("customer_segment", "customer_type")


def _percentile(ordered: Sequence[float], q: float) -> float:
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(len(ordered) * q)))
    return ordered[index]


def numeric_summary(values: Sequence[float]) -> dict[str, float | int]:
    """Five-number summary plus mean/std. Pure, deterministic, no I/O."""
    if not values:
        return {
            "n": 0,
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "p25": 0.0,
            "median": 0.0,
            "p75": 0.0,
            "max": 0.0,
        }
    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    mean = sum(ordered) / n
    variance = sum((v - mean) ** 2 for v in ordered) / n
    return {
        "n": n,
        "mean": mean,
        "std": math.sqrt(variance),
        "min": ordered[0],
        "p25": _percentile(ordered, 0.25),
        "median": _percentile(ordered, 0.5),
        "p75": _percentile(ordered, 0.75),
        "max": ordered[-1],
    }


def categorical_summary(values: Sequence[object]) -> dict[str, Any]:
    """Value counts and shares, ordered by descending frequency (ties broken alphabetically)."""
    n = len(values)
    counts = Counter(str(v) for v in values)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "n": n,
        "distinct": len(counts),
        "value_counts": dict(ordered),
        "share": {key: count / n for key, count in ordered} if n else {},
    }


def _split_frame(frame: pl.DataFrame, split: str) -> pl.DataFrame:
    return frame.filter(pl.col("split_label") == split)  # pyright: ignore[reportUnknownMemberType]


def _rename_mean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rename `outcome_breakdown_by`'s generic `mean` key to `primary_outcome_mean` in place.

    Deliberately two statements (pop, then assign), not `{**row, "k": row.pop("mean")}`: a dict
    display evaluates `**row` before the trailing key/value, so that one-liner unpacks `mean`
    *before* the pop mutates `row`, silently leaving both keys in the result.
    """
    for row in rows:
        row["primary_outcome_mean"] = row.pop("mean")
    return rows


def outcome_breakdown_by(
    frame: pl.DataFrame, group_column: str, outcome: OutcomeDefinition
) -> list[dict[str, Any]]:
    """Per-distinct-value N/missingness/mean for one outcome — one `summarize_group` call per
    value, the same primitive `TASK-018`'s per-split grading already uses, applied here to an
    arbitrary categorical column instead of a fixed split label.
    """
    results: list[dict[str, Any]] = []
    for value in sorted(frame[group_column].unique().to_list(), key=str):
        subset = frame.filter(pl.col(group_column) == value)  # pyright: ignore[reportUnknownMemberType]
        summary = summarize_group(subset[outcome.column].to_list(), outcome)
        results.append(
            {
                "value": value,
                "n_total": summary.n_total,
                "n_present": summary.n_present,
                "missing_rate": summary.missing_rate,
                "mean": summary.mean,
            }
        )
    return results


def build_report(frame: pl.DataFrame) -> dict[str, Any]:
    from policy_analytics.outcomes import primary_outcome

    primary = primary_outcome()

    # --- Cohort overview -------------------------------------------------------------------------
    split_counts = {split: _split_frame(frame, split).height for split in SPLITS}
    split_date_ranges = {
        split: {
            "min": _split_frame(frame, split)["booking_date"].min(),
            "max": _split_frame(frame, split)["booking_date"].max(),
        }
        for split in SPLITS
    }
    cohort = {
        "n_total": frame.height,
        "booking_date_min": frame["booking_date"].min(),
        "booking_date_max": frame["booking_date"].max(),
        "split_counts": split_counts,
        "split_date_ranges": split_date_ranges,
    }

    # --- Overall distributions (DECISION_TIME features only — never an OUTCOME/POST_DECISION
    # column, matching the same explanatory-variable boundary TASK-015/TASK-018 already enforce) --
    overall_distributions: dict[str, Any] = {}
    for column in sorted(DECISION_TIME_FEATURES):
        if column in DATE_COLUMNS:
            overall_distributions[column] = {
                "type": "date",
                "min": frame[column].min(),
                "max": frame[column].max(),
            }
        elif frame.schema[column].is_numeric():
            overall_distributions[column] = {
                "type": "numeric",
                **numeric_summary(frame[column].to_list()),
            }
        else:
            overall_distributions[column] = {
                "type": "categorical",
                **categorical_summary(frame[column].to_list()),
            }

    # --- Outcome prevalence (every outcome, primary and secondary) -------------------------------
    outcome_prevalence: dict[str, Any] = {}
    for outcome in OUTCOME_DEFINITIONS:
        if "/" in outcome.column:
            # contribution_margin_rate is a computed ratio, not a stored column — out of scope for
            # a raw-column prevalence pass; TASK-018's adjustment layer computes it when needed.
            continue
        summary = summarize_group(frame[outcome.column].to_list(), outcome)
        entry: dict[str, Any] = {
            "role": outcome.role.value,
            "missing_data_policy": outcome.missing_data_policy.value,
            "n_total": summary.n_total,
            "n_present": summary.n_present,
            "missing_count": summary.missing_count,
            "missing_rate": summary.missing_rate,
            "mean": summary.mean,
            "std": math.sqrt(summary.variance) if summary.variance is not None else None,
        }
        if outcome.missing_data_policy is MissingDataPolicy.MNAR_BOUNDED:
            bounds = mnar_bounds(frame[outcome.column].to_list(), outcome)
            entry["mnar_bounds"] = {
                "observed_only_mean": bounds.observed_only_mean,
                "pessimistic_mean": bounds.pessimistic_mean,
                "optimistic_mean": bounds.optimistic_mean,
            }
        outcome_prevalence[outcome.outcome_id] = entry

    # --- Time trend: by split, and by calendar year-month across the full window -----------------
    by_split: list[dict[str, Any]] = []
    for split in SPLITS:
        split_values = _split_frame(frame, split)[primary.column].to_list()
        split_summary = summarize_group(split_values, primary)
        by_split.append(
            {
                "split": split,
                "n_total": split_summary.n_total,
                "n_present": split_summary.n_present,
                "missing_rate": split_summary.missing_rate,
                "primary_outcome_mean": split_summary.mean,
            }
        )
    frame_with_ym = frame.with_columns(
        pl.col("booking_date").str.slice(0, 7).alias("_booking_year_month")
    )
    year_month_rows = outcome_breakdown_by(frame_with_ym, "_booking_year_month", primary)
    by_year_month = _rename_mean(year_month_rows)
    for row in by_year_month:
        row["year_month"] = row.pop("value")

    # --- Segment / supplier / manager trend, all against the primary outcome ---------------------
    segment_trend = {
        column: _rename_mean(outcome_breakdown_by(frame, column, primary))
        for column in SEGMENT_TREND_COLUMNS
    }
    supplier_trend = _rename_mean(outcome_breakdown_by(frame, "supplier", primary))
    manager_trend = _rename_mean(outcome_breakdown_by(frame, "manager", primary))

    return {
        "cohort": cohort,
        "overall_distributions": overall_distributions,
        "outcome_prevalence": outcome_prevalence,
        "time_trend": {"by_split": by_split, "by_year_month": by_year_month},
        "segment_trend": segment_trend,
        "supplier_trend": supplier_trend,
        "manager_trend": manager_trend,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--force", action="store_true", help="allow overwriting an existing output file"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.output.exists() and not args.force:
        print(
            f"{args.output} already exists and is a frozen result (status=FROZEN). Refusing to "
            "overwrite it. Point --output at a new file, or pass --force with a clear reason "
            "recorded in TASKS.md/HANDOFFS.md.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    manifest = json.loads((args.dataset_root / "manifest.json").read_text(encoding="utf-8"))
    frame = load_analytical_frame(args.dataset_root)
    report = build_report(frame)

    payload = {
        "status": "FROZEN",
        "frozen_at": datetime.now(UTC).isoformat(),
        "task": "TASK-014",
        "dataset_version": manifest["dataset_version"],
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "outcome_contract_version": OUTCOME_CONTRACT_VERSION,
        "hidden_ground_truth_opened": False,
        "scope_note": (
            "Purely descriptive_observation-level baseline profiling (docs/analytics/"
            "baseline-statistics-v1.md). Not a discovery run, not a validated finding, no "
            "uncertainty interval or significance test attached to any number here."
        ),
        **report,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    n_total = report["cohort"]["n_total"]
    split_counts = report["cohort"]["split_counts"]
    print(f"Cohort: {n_total} bookings, splits: {split_counts}")
    for outcome_id, entry in report["outcome_prevalence"].items():
        print(f"  {outcome_id}: missing_rate={entry['missing_rate']:.1%} mean={entry['mean']}")


if __name__ == "__main__":
    main()
