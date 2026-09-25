"""TASK-107 Phase 2b design-time structural exploration (covariates only; no oracle, no engine).

Prints the engine's atom grid (real `_atoms` builder, default `DiscoveryConfig()`) on one no-target
v2 draw and, for candidate rules, their prevalence. Used only on the design-check seed range
declared in `rev4-preregistration.md` (never on calibration/acceptance/final seeds).
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPOSITORY / "packages/analytics/src"),
    str(REPOSITORY / "packages/schemas/src"),
    str(REPOSITORY / "scripts"),
]

import polars as pl  # noqa: E402
from policy_analytics import synthetic_benchmark_v2 as sb2  # noqa: E402
from policy_analytics.discovery.engine import DiscoveryConfig, _atoms  # noqa: E402
from policy_analytics.validation.apply import load_analytical_frame  # noqa: E402


def grid(seed: int) -> dict[str, list[tuple[str, object]]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = sb2.materialize_analytical(sb2.generate_v2(sb2.V2Config(seed=seed), ()), Path(tmp))
        manifest = json.loads((root / "manifest.json").read_text())
        frame = load_analytical_frame(root)
        timing = {n: str(m["classification"]) for n, m in manifest["feature_timing"].items()}
        feats = tuple(
            n
            for n in frame.columns
            if timing.get(n) == "DECISION_TIME" and n not in {"booking_date", "travel_date"}
        )
        dev = frame.filter(pl.col("split_label") == "development")
        out: dict[str, list[tuple[str, object]]] = defaultdict(list)
        for a in _atoms(dev, feats, DiscoveryConfig()):
            out[a.feature].append((a.operator, a.value))
        print("features:", feats)
        print("rows:", frame.height, "dev:", dev.height)
        return dict(out)


if __name__ == "__main__":
    for feature, atoms in grid(int(sys.argv[1])).items():
        print(feature, atoms)
