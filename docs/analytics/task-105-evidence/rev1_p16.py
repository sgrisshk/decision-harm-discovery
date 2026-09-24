"""P16 (resolution factors) and the fixture b(s) curve / replica-level P3r, P5r checks. Real _stratified_adjustment for
the point estimates; replica bootstrap for the block decision on Z* only (NOT the real gate)."""
import json
import math
import random
import statistics
import sys
from statistics import NormalDist

sys.path.insert(0, "<scratch>")
import polars as pl
from policy_analytics.outcomes import primary_outcome
from policy_analytics.validation.apply import _stratified_adjustment
from rev1_common import load_delivered, design_labels, strat

out = primary_outcome()
mult = out.harm_multiplier
ND = NormalDist()
df = load_delivered()
dev = df.filter(pl.col("split_label") == "development")
n_all = df.height

HIGH_DEST = {"Tokyo", "Reykjavik"}          # TASK-104 fixture definition
GEN_DEST = {"Tokyo", "Zanzibar"}            # generator definition


def median_ind(col):
    vals = df[col].to_list()
    thr = sorted(vals)[len(vals) // 2]
    return [int(v >= thr) for v in vals], thr


def indicators():
    d = {}
    d["lead<14 (generator cut)"] = ("booking_lead_days", [int(v < 14) for v in df["booking_lead_days"].to_list()])
    d["duration>=14 (generator cut)"] = ("trip_duration_days", [int(v >= 14) for v in df["trip_duration_days"].to_list()])
    d["party>=5 (generator cut)"] = ("party_size", [int(v >= 5) for v in df["party_size"].to_list()])
    d["destination in {Tokyo,Zanzibar} (generator)"] = ("destination", [int(v in GEN_DEST) for v in df["destination"].to_list()])
    ml, t1 = median_ind("booking_lead_days")
    md, t2 = median_ind("trip_duration_days")
    d[f"lead>=median({t1}) (fixture)"] = ("booking_lead_days", ml)
    d[f"duration>=median({t2}) (fixture)"] = ("trip_duration_days", md)
    return d


def resolution(col, ind, n=200_000, seed=7):
    """Noise-free population attenuation of a fully confounding indicator, Z stratified by design bins."""
    rng = random.Random(seed)
    lab_all = design_labels(df, dev, col)
    idx = [rng.randrange(n_all) for _ in range(n)]
    I = [ind[i] for i in idx]
    z = [str(lab_all[i]) for i in idx]
    x = [rng.random() < 0.03 + 0.62 * v for v in I]
    y = [400.0 - 400.0 * v for v in I]      # harm positive direction: margin lower when I=1 (X more likely)
    adj, cov, raw, raw_u = strat(y, x, z)
    return 1 - adj / raw if raw else float("nan"), cov, raw * mult


res16 = {}
for name, (col, ind) in indicators().items():
    r, cov, raw = resolution(col, ind)
    res16[name] = dict(r=round(r, 3), coverage=round(cov, 3), raw_harm=round(raw, 1),
                       prevalence=round(sum(ind) / n_all, 3))
    print("P16", name, res16[name], flush=True)

# ---- fixture curve b(s) with Z* = destination (TASK-104 recipe copied into scratch) ----
CONF = ("destination", "party_size", "trip_duration_days", "booking_lead_days")
ind_fix = {
    "destination": [int(v in HIGH_DEST) for v in df["destination"].to_list()],
    "party_size": median_ind("party_size")[0],
    "trip_duration_days": median_ind("trip_duration_days")[0],
    "booking_lead_days": median_ind("booking_lead_days")[0],
}
split = df["split_label"].to_list()
val_idx = [i for i, s in enumerate(split) if s == "validation"]
dev_idx = [i for i, s in enumerate(split) if s == "development"]
lab_dest = design_labels(df, dev, "destination")
lab_lead = design_labels(df, dev, "booking_lead_days")
lab_dur = design_labels(df, dev, "trip_duration_days")
lab_party = design_labels(df, dev, "party_size")

Z_NULLS = 9  # m = 10 total in the T05 pool


def replica_block(y, x, lab, idx_rows, m=10, B=200, seed=0):
    yy = [y[i] for i in idx_rows]
    xx = [x[i] for i in idx_rows]
    zz = [lab[i] for i in idx_rows]
    adj, cov, raw_all, raw_u = strat(yy, xx, zz)
    Hz, Hr = adj * mult, raw_u * mult
    rng = random.Random(seed)
    n = len(yy)
    Dr, Hzr = [], []
    for _ in range(B):
        ii = [rng.randrange(n) for _ in range(n)]
        a, c, ra, ru = strat(yy, xx, zz, ii)
        Dr.append(a * mult - 0.5 * ru * mult)
        Hzr.append(a * mult)
    seD, seHz = statistics.stdev(Dr), statistics.stdev(Hzr)
    D = Hz - 0.5 * Hr
    p_att = ND.cdf(D / seD)
    ne = [v for v, b in zip(yy, xx) if b]
    nc = [v for v, b in zip(yy, xx) if not b]
    psd = math.sqrt(((len(ne) - 1) * statistics.pvariance(ne) + (len(nc) - 1) * statistics.pvariance(nc)) / (len(ne) + len(nc) - 2))
    hE = math.log(1.125) / 0.91 * psd
    raw_E_ok = Hr >= hE
    p_E = ND.cdf((Hz - hE) / seHz) if raw_E_ok else 1.0
    pz = min(1.0, 2 * min(p_att, p_E))
    return dict(a=1 - Hz / Hr if Hr else float("nan"), Hz=Hz, Hr=Hr, seD=seD, block=pz <= 0.10 / m, pz=pz, cov=cov, raw_E_ok=raw_E_ok, hE=hE)


def fixture(weights, seed, noise=250.0, target=400.0, base=400.0):
    total = sum(weights.values())
    score = [0.0] * n_all
    for c, w in weights.items():
        for i, f in enumerate(ind_fix[c]):
            score[i] += (w / total) * f
    rng = random.Random(seed)
    x = [rng.random() < 0.03 + 0.62 * s for s in score]
    e = [s for s, xx, d in zip(score, x, split) if d == "development" and xx]
    c_ = [s for s, xx, d in zip(score, x, split) if d == "development" and not xx]
    gap = sum(e) / len(e) - sum(c_) / len(c_)
    A = target / gap
    nr = random.Random(seed + 1)
    y = [base - A * s + nr.gauss(0, noise) for s in score]
    return x, y


rows = {}
for s in (1.0, 0.8, 0.6, 0.5, 0.4, 0.25):
    w = {"destination": s, **{c: (1 - s) / 3 for c in CONF if c != "destination"}} if s != 0.25 else {c: 1.0 for c in CONF}
    per = []
    for seed in range(101, 107):
        x, y = fixture(w, seed)
        r = replica_block(y, x, lab_dest, val_idx, seed=seed)
        per.append(r)
    blocks = sum(p["block"] for p in per)
    rows[s] = dict(mean_a=round(statistics.mean(p["a"] for p in per), 3), min_a=round(min(p["a"] for p in per), 3),
                   max_a=round(max(p["a"] for p in per), 3), mean_seD=round(statistics.mean(p["seD"] for p in per), 1),
                   replica_blocks_on_Zstar=blocks, of=6, mean_Hr=round(statistics.mean(p["Hr"] for p in per), 1))
    print("FIX destination-weight s=", s, rows[s], flush=True)

# P5r-b replica: generator-cut numeric indicators as the sole driver (weights: indicator only), fixture noise/harm
def single_ind_fixture(ind, seed, noise=250.0, target=400.0, base=400.0):
    score = [float(v) for v in ind]
    rng = random.Random(seed)
    x = [rng.random() < 0.03 + 0.62 * s for s in score]
    e = [s for s, xx, d in zip(score, x, split) if d == "development" and xx]
    c_ = [s for s, xx, d in zip(score, x, split) if d == "development" and not xx]
    gap = sum(e) / len(e) - sum(c_) / len(c_)
    A = target / gap
    nr = random.Random(seed + 1)
    return x, [base - A * s + nr.gauss(0, noise) for s in score]


rows5 = {}
for name, (col, ind) in indicators().items():
    if "generator cut" not in name and "median" not in name:
        continue
    lab = {"booking_lead_days": lab_lead, "trip_duration_days": lab_dur, "party_size": lab_party}.get(col, lab_dest)
    per = []
    for seed in range(101, 107):
        x, y = single_ind_fixture(ind, seed)
        per.append(replica_block(y, x, lab, val_idx, seed=seed))
    rows5[name] = dict(mean_a=round(statistics.mean(p["a"] for p in per), 3), min_a=round(min(p["a"] for p in per), 3),
                       replica_blocks_on_Zstar=sum(p["block"] for p in per), of=6, mean_seD=round(statistics.mean(p["seD"] for p in per), 1))
    print("SINGLE-IND", name, rows5[name], flush=True)

json.dump(dict(P16=res16, fixture_curve=rows, single_indicator=rows5),
          open("<scratch>", "w"), indent=1, default=str)
