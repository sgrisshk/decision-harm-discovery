"""TASK-105 Phase 2b-0 Revision 1: checks the point-estimate arithmetic (adjusted harm, coverage) of
rev3_g17_block_sim.py against the REAL, unchanged `_stratified_adjustment` (apply.py:337-381). Read-only.

Usage (repo venv python, which has polars): python rev3_validate_estimator.py VALIDATION_INPUT.json WORKTREE_ROOT
The input is produced by `python3 rev3_g17_block_sim.py dump VALIDATION_INPUT.json`.
"""
import json
import sys

import polars as pl

sys.path.insert(0, sys.argv[2] + "/packages/analytics/src")
sys.path.insert(0, sys.argv[2] + "/packages/schemas/src")
from policy_analytics.validation.apply import _stratified_adjustment  # noqa: E402


class _Outcome:
    column = "y"
    harm_multiplier = 1.0


for i, d in enumerate(json.load(open(sys.argv[1]))):
    frame = pl.DataFrame({"z": d["z"], "y": d["y"]})
    mask = pl.Series("m", d["x"])
    diff, cov = _stratified_adjustment(frame, mask, _Outcome(), ("z",))
    print(i, "real", round(diff, 9), round(cov, 9), "replica", d["h_z"], d["coverage"],
          "OK" if abs(diff - d["h_z"]) < 1e-6 and abs(cov - d["coverage"]) < 1e-9 else "MISMATCH")
