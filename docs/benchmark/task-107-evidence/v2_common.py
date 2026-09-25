"""TASK-107 Phase 2b shared helpers (no engine search; only the atom-grid builder and contract
functions, exactly as in Phase 1 / Phase 2a)."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPOSITORY / "packages/analytics/src"),
    str(REPOSITORY / "packages/schemas/src"),
    str(REPOSITORY / "scripts"),
]

import polars as pl  # noqa: E402
from policy_analytics import benchmark_v2_scoring as scoring  # noqa: E402
from policy_analytics import synthetic_benchmark_v2 as sb2  # noqa: E402
from policy_analytics import synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics.validation.apply import load_analytical_frame  # noqa: E402

TRAP_LITERALS: dict[str, scoring.CondSpec] = {
    "T01": scoring.CondSpec("manager", "eq", "Manager 2"),
    "T02": scoring.CondSpec("supplier", "eq", "Atlas"),
    "T03": scoring.CondSpec("acquisition_channel", "eq", "paid_search"),
    "T04": scoring.CondSpec("payment_method", "eq", "bank_transfer"),
    "T05": scoring.CondSpec("manual_exception", "eq", True),
}
ENGINE_MAX_CONDITIONS = 3


@dataclass
class Draw:
    seed: int
    root: Path
    frame: pl.DataFrame
    manifest: dict[str, Any]
    features: tuple[str, ...]
    space: scoring.RowSpace
    masks: dict[str, int]  # target id -> affected-row bitmask (dataset row order)
    members: dict[str, list[str]]


def build_draw(seed: int, work: Path, designs: tuple[tg.TargetDesign, ...]) -> Draw:
    specs = tg.target_specs(designs)
    v2 = sb2.generate_v2(sb2.V2Config(seed=seed), specs)
    root = sb2.materialize_analytical(v2, work)
    manifest = json.loads((root / "manifest.json").read_text())
    frame = load_analytical_frame(root)
    timing = {n: str(m["classification"]) for n, m in manifest["feature_timing"].items()}
    features = tuple(
        n
        for n in frame.columns
        if timing.get(n) == "DECISION_TIME" and n not in {"booking_date", "travel_date"}
    )
    cols: dict[str, list[Any]] = {
        c: frame[c].to_list() for c in frame.columns if c not in ("booking_date", "travel_date")
    }
    cols["booking_month"] = [date.fromisoformat(str(d)).month for d in frame["booking_date"]]
    dev = 0
    for i, label in enumerate(frame["split_label"].to_list()):
        if label == "development":
            dev |= 1 << i
    space = scoring.RowSpace(cols, dev)
    index_of = {b: i for i, b in enumerate(frame["booking_id"].to_list())}
    masks = {tid: space.ids_to_mask(index_of, ids) for tid, ids in v2.memberships.items()}
    return Draw(seed, root, frame, manifest, features, space, masks, v2.memberships)


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def clopper_pearson_lower(k: int, n: int, alpha: float = 0.05) -> float:
    """One-sided (1 - alpha) Clopper-Pearson lower bound: p with P(X >= k | p, n) = alpha."""
    if k == 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        tail = sum(math.comb(n, i) * mid**i * (1 - mid) ** (n - i) for i in range(k, n + 1))
        if tail > alpha:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2, 4)
