"""Print sha256 of every frozen file (engine, discovery, validation contract/gates, v1 generator,
scorer and ground truth). Run before and after Phase 2b; the outputs must be identical."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "packages/analytics/src/policy_analytics"
FILES = [
    *sorted((PKG / "discovery").glob("*.py")),
    *sorted((PKG / "validation").glob("*.py")),
    PKG / "synthetic_benchmark.py",
    ROOT / "scripts/evaluate_benchmark.py",
    ROOT / "synthetic_data/evaluation/hidden_ground_truth.json",
    ROOT / "synthetic_data/evaluation/checksums.json",
]
for f in FILES:
    print(hashlib.sha256(f.read_bytes()).hexdigest(), f.relative_to(ROOT))
