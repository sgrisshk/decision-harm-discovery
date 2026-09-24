"""P14 (SE ratios) and P15 (attribution contamination) on the delivered validation split."""
import json
import math
import random
import statistics
import sys

sys.path.insert(0, "<scratch>")
import polars as pl
from policy_analytics.outcomes import primary_outcome
from policy_analytics.validation.apply import _stratified_adjustment
from rev1_common import *

out = primary_outcome()
mult = out.harm_multiplier
df = load_delivered()
dev = df.filter(pl.col("split_label") == "development")
val = df.filter(pl.col("split_label") == "validation")
print("rows dev/val", dev.height, val.height, "mult", mult)
B = 500
res = []
for trap, ((xcol, xval), pool) in POOLS.items():
    xmask = [v == xval for v in val[xcol].to_list()]
    y = [float(v) for v in val[out.column].to_list()]
    n_e = sum(xmask)
    # pooled sd (existing convention approx): pooled over the two arms
    ye = [a for a, b in zip(y, xmask) if b]
    yc = [a for a, b in zip(y, xmask) if not b]
    ve, vc = statistics.pvariance(ye), statistics.pvariance(yc)
    psd = math.sqrt(((len(ye) - 1) * ve + (len(yc) - 1) * vc) / (len(ye) + len(yc) - 2))
    se_raw_formula = psd * math.sqrt(1 / len(ye) + 1 / len(yc))
    hE = 0.12943 * psd
    for z in pool:
        lab = design_labels(val, dev, z)
        adj, cov, raw_all, raw_u = strat(y, xmask, lab)
        # cross-check with the real function
        w = val.select([pl.Series("z", [str(v) for v in lab]), pl.Series(out.column, y)]).with_columns(pl.Series("_m", xmask))
        r_adj, r_cov = _stratified_adjustment(w.select(["z", out.column]), pl.Series("m", xmask), out, ("z",))
        assert abs(r_adj - adj) < 1e-6 and abs(r_cov - cov) < 1e-9, (trap, z, r_adj, adj, r_cov, cov)
        H_raw, H_raw_u, H_z = raw_all * mult, raw_u * mult, adj * mult
        rng = random.Random(f"{trap}-{z}")
        n = len(y)
        Dr, Hzr, Hrr, Dru = [], [], [], []
        for _ in range(B):
            idx = [rng.randrange(n) for _ in range(n)]
            a, c, ra, ru = strat(y, xmask, lab, idx)
            if c <= 0:
                continue
            Dr.append(a * mult - 0.5 * ru * mult)
            Hzr.append(a * mult)
            Hrr.append(ra * mult)
            Dru.append(a * mult - 0.5 * ra * mult)
        se_D = statistics.stdev(Dr)
        se_Dall = statistics.stdev(Dru)
        se_Hz = statistics.stdev(Hzr)
        se_Hr = statistics.stdev(Hrr)
        rec = dict(trap=trap, z=z, n_exposed=n_e, coverage=round(cov, 3), H_raw=round(H_raw, 1),
                   H_raw_U=round(H_raw_u, 1), H_Z=round(H_z, 1), exclusion_term=round(0.5 * (H_raw - H_raw_u), 1),
                   SE_raw_formula=round(se_raw_formula, 1), SE_raw_boot=round(se_Hr, 1), SE_Hz=round(se_Hz, 1),
                   SE_D=round(se_D, 1), SE_D_allrows=round(se_Dall, 1),
                   rho=round(se_D / se_Hr, 3), rho_allrows=round(se_Dall / se_Hr, 3), rho_Hz=round(se_Hz / se_Hr, 3),
                   hE=round(hE, 1), pooled_sd=round(psd, 1), valid_reps=len(Dr))
        res.append(rec)
        print(rec, flush=True)
json.dump(res, open("<scratch>", "w"), indent=1)
rhos = [r["rho"] for r in res]
print("rho median", statistics.median(rhos), "min", min(rhos), "max", max(rhos),
      "share in [0.55,0.70]", sum(0.55 <= r <= 0.70 for r in rhos) / len(rhos))
rh = [r["rho_Hz"] for r in res]
print("SE(Hz)/SE_raw median", statistics.median(rh), "min", min(rh), "max", max(rh), "share in [0.95,1.30]", sum(0.95 <= r <= 1.30 for r in rh) / len(rh))
ex = [abs(r["exclusion_term"]) for r in res]
print("pairs coverage<1:", sum(r["coverage"] < 1 for r in res), "of", len(res), "; share |excl|<=10:", sum(e <= 10 for e in ex) / len(ex), "max", max(ex))
