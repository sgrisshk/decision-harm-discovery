"""P17: outcome-side single-Z attenuation shares from the real generator (400k rows), real _stratified_adjustment."""
import json
import sys
import time

sys.path.insert(0, "<scratch>")
sys.path.insert(0, "<repo>/worktrees/agent-a06af37328e75b709")
import polars as pl
from policy_analytics.outcomes import primary_outcome
from policy_analytics.validation.apply import _stratified_adjustment
from rev1_common import TIER0, TIER1, design_labels
from scripts import measure_task105_generator_realization as m

out = primary_outcome()
mult = out.harm_multiplier
N = int(sys.argv[1]) if len(sys.argv) > 1 else 400_000
SEED = 105_101
t0 = time.time()
frame = m.generate_rows(N, SEED)
print("generated", frame.height, "rows in", round(time.time() - t0), "s; columns:", frame.columns, flush=True)
half = frame.with_row_index("_i")
dev = half.filter(pl.col("_i") % 2 == 0)
exposures = {
    "T01": ("manager", lambda v: v == "Manager 2", TIER0),
    "T02": ("supplier", lambda v: v == "Atlas", TIER0),
    "T04": ("payment_method", lambda v: v == "bank_transfer", TIER0 + TIER1),
    "T05": ("manual_exception", lambda v: bool(v), TIER0 + TIER1),
}
y = frame[out.column]
results = {}
for trap, (col, pred, pool) in exposures.items():
    mask = pl.Series("m", [pred(v) for v in frame[col].to_list()])
    raw, _ = _stratified_adjustment(frame.select([out.column]), mask, out, ())
    H_raw = raw * mult
    rows = {}
    for z in pool:
        lab = design_labels(half, dev, z)
        w = pl.DataFrame({"z": [str(v) for v in lab], out.column: y})
        adj, cov = _stratified_adjustment(w, mask, out, ("z",))
        H_z = adj * mult
        rows[z] = dict(H_Z=round(H_z, 2), attenuation=round(1 - H_z / H_raw, 3), coverage=round(cov, 3))
    results[trap] = dict(exposed=int(mask.sum()), H_raw=round(H_raw, 2), per_z=rows)
    print(trap, "exposed", int(mask.sum()), "H_raw", round(H_raw, 2), flush=True)
    for z, r in rows.items():
        print("   ", z, r, flush=True)
json.dump(results, open("<scratch>", "w"), indent=1)
