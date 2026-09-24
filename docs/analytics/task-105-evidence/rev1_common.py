"""Scratch helpers for TASK-105 Revision 1 measurements (read-only; nothing here is imported by the repo)."""
import bisect
import math
import random
from pathlib import Path

import polars as pl

REPO = Path("<repo>/worktrees/agent-a06af37328e75b709")
DATASET = REPO / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"

TIER0 = ["acquisition_channel", "customer_segment", "customer_type", "destination", "party_size",
         "trip_duration_days", "booking_lead_days"]
TIER1 = ["manager", "supplier", "product_category"]
POOLS = {
    "T01": (("manager", "Manager 2"), TIER0),
    "T02": (("supplier", "Atlas"), TIER0),
    "T04": (("payment_method", "bank_transfer"), TIER0 + TIER1),
    "T05": (("manual_exception", True), TIER0 + TIER1),
}


def load_delivered() -> pl.DataFrame:
    f = pl.read_csv(DATASET / "features.csv", infer_schema_length=10000)
    o = pl.read_csv(DATASET / "outcomes.csv", infer_schema_length=10000)
    m = pl.read_csv(DATASET / "metadata.csv", infer_schema_length=10000)
    i = pl.read_csv(DATASET / "identifiers.csv", infer_schema_length=10000)
    return pl.concat([f, o, m.select(["split_label"]), i.select(["customer_id"])], how="horizontal")


def quantile_breakpoints(values, bins):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return []
    return [ordered[min(n - 1, max(0, int(n * i / bins)))] for i in range(1, bins)]


def design_labels(frame: pl.DataFrame, dev_frame: pl.DataFrame, col: str) -> list:
    """Design 2.3 stratification: raw levels (categorical/bool, or numeric with <=12 dev distinct values);
    else development-split deciles; edges from development only."""
    vals = frame[col].to_list()
    if not dev_frame.schema[col].is_numeric():
        return vals
    dev_vals = [v for v in dev_frame[col].to_list() if v is not None]
    if len({round(float(v), 9) for v in dev_vals}) <= 12:
        return vals
    bp = quantile_breakpoints(dev_vals, 10)
    return [None if v is None else f"d{bisect.bisect_right(bp, float(v))}" for v in vals]


def strat(y, x, z, idx=None):
    """(adjusted_diff, coverage, raw_diff_all, raw_diff_usable): replica of _stratified_adjustment (+ usable raw)."""
    cells = {}
    rng_iter = range(len(y)) if idx is None else idx
    for i in rng_iter:
        c = cells.get(z[i])
        if c is None:
            c = [0.0, 0, 0.0, 0]
            cells[z[i]] = c
        if x[i]:
            c[0] += y[i]
            c[1] += 1
        else:
            c[2] += y[i]
            c[3] += 1
    tot_e = sum(c[1] for c in cells.values())
    tot_c = sum(c[3] for c in cells.values())
    sum_e = sum(c[0] for c in cells.values())
    sum_c = sum(c[2] for c in cells.values())
    raw_all = (sum_e / tot_e - sum_c / tot_c) if tot_e and tot_c else 0.0
    usable = [c for c in cells.values() if c[1] >= 5 and c[3] >= 5]
    ue = sum(c[1] for c in usable)
    if not usable or ue == 0:
        return 0.0, 0.0, raw_all, 0.0
    adj = sum((c[0] / c[1] - c[2] / c[3]) * c[1] for c in usable) / ue
    cov = ue / tot_e if tot_e else 0.0
    uc = sum(c[3] for c in usable)
    raw_u = sum(c[0] for c in usable) / ue - sum(c[2] for c in usable) / uc
    return adj, cov, raw_all, raw_u
