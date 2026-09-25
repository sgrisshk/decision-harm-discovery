"""TASK-107 Phase 2b design-time power proxy, ANCHORED on Phase 1 (spent seeds 1001-1005 only).

A cheap, contract-free statistic (Welch t of `contribution_margin_eur`, exposed vs rest, development
split) used to size prevalence/dose of new designs *before* any Phase 2b calibration draw. Phase 1
oracle pass rates (`oracle-rates.json`, family 36,791, cond oracle) are the anchor: the proxy is
only trusted as an ordering aid, never as a replacement for the oracle. No engine, no discovery.
Usage: power_proxy_anchor.py SEED_LO SEED_HI
"""

from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPOSITORY / "packages/analytics/src"),
    str(REPOSITORY / "packages/schemas/src"),
]

from policy_analytics import synthetic_benchmark_v2 as sb2  # noqa: E402

H = sb2.TargetDose(410, 1.05, 0.75)
M = sb2.TargetDose(300, 0.75, 0.5)
L = sb2.TargetDose(240, 0.5, 0.3)


def spec(tid: str, dose: sb2.TargetDose, pred) -> sb2.TargetSpec:  # type: ignore[no-untyped-def]
    return sb2.TargetSpec(tid, tid, pred, dose)


PHASE1 = [
    spec(
        "N01", H,
        lambda c: c["customer_segment"] == "corporate" and c["destination"] == "Reykjavik" and c["booking_lead_days"] < 23,
    ),
    spec(
        "N02", M,
        lambda c: c["product_category"] == "premium" and c["acquisition_channel"] == "partner" and c["discount_rate"] >= 0.08,
    ),
    spec(
        "N03", H,
        lambda c: c["supplier"] == "Cedar" and c["customer_segment"] == "family" and c["trip_duration_days"] >= 10,
    ),
    spec(
        "N04", M,
        lambda c: c["manager"] == "Manager 6" and c["destination"] == "Rome" and c["installments"] >= 2,
    ),
    spec("N05", M, lambda c: c["customer_segment"] == "corporate" and c["payment_method"] == "wallet"),
    spec("N06", M, lambda c: c["destination"] == "Lisbon" and c["acquisition_channel"] == "referral"),
    spec(
        "N07", H,
        lambda c: c["manager"] == "Manager 7" and c["acquisition_channel"] == "direct" and c["trip_duration_days"] >= 8,
    ),
    spec(
        "N08", L,
        lambda c: c["payment_method"] == "card" and c["customer_segment"] == "family" and c["installments"] >= 3,
    ),
]


def welch(a: list[float], b: list[float]) -> float:
    va, vb = statistics.variance(a), statistics.variance(b)
    return (statistics.fmean(b) - statistics.fmean(a)) / math.sqrt(va / len(a) + vb / len(b))


def proxy(targets: list[sb2.TargetSpec], seed: int) -> dict[str, tuple[int, int, float]]:
    draw = sb2.generate_v2(sb2.V2Config(seed=seed), targets)
    out: dict[str, tuple[int, int, float]] = {}
    ids = [r["booking_id"] for r in draw.rows]
    # development split = first-half-by-date rule is inside the dataset builder; approximate with the
    # earlier half of booking dates (proxy only)
    order = sorted(range(len(draw.rows)), key=lambda i: str(draw.rows[i]["booking_date"]))
    dev = set(order[: len(order) // 2])
    idx = {b: i for i, b in enumerate(ids)}
    y = [float(r["contribution_margin_eur"]) for r in draw.rows]
    for t in targets:
        members = {idx[b] for b in draw.memberships[t.target_id]}
        a = [y[i] for i in members if i in dev]
        b = [y[i] for i in range(len(y)) if i in dev and i not in members]
        out[t.target_id] = (len(members), len(a), welch(a, b) if len(a) > 2 else float("nan"))
    return out


if __name__ == "__main__":
    lo, hi = int(sys.argv[1]), int(sys.argv[2])
    acc: dict[str, list[tuple[int, int, float]]] = {}
    for s in range(lo, hi + 1):
        for k, v in proxy(PHASE1, s).items():
            acc.setdefault(k, []).append(v)
    for k, rows in acc.items():
        print(
            k,
            "n_aff",
            round(statistics.fmean(r[0] for r in rows)),
            "n_dev",
            round(statistics.fmean(r[1] for r in rows)),
            "t_mean",
            round(statistics.fmean(r[2] for r in rows), 2),
            "t_min",
            round(min(r[2] for r in rows), 2),
        )
