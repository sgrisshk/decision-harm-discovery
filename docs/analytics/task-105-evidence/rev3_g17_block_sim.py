"""TASK-105 Phase 2b-0 Revision 1: read-only scratch simulation of the G17 block rule (Section 3.3 of
docs/analytics/task-105-2b-contract-freeze.md). NOT imported by the repo; touches no engine/gate/contract code.

It is a numpy replica of the rule's arithmetic (matched-crude and stratified-adjusted harm on usable strata,
paired cluster bootstrap with B = 2000 replicates and percentile intervals per apply.py:253-260, one-sided
p_Z from the bootstrap SE, BH with family_size = m, criteria C1-C3 as executed by G06-sign/G04/G03 but here
evaluated on the SIMULATED VALIDATION rows). The point-estimate arithmetic is checked against the real
`_stratified_adjustment` by rev3_validate_estimator.py; the bootstrap/criteria layer is a replica and is NOT
validated against the real code (stated in the document).

Usage: python3 rev3_g17_block_sim.py run OUT.json [D]      (D datasets per cell; default 2000)
       python3 rev3_g17_block_sim.py dump VALIDATION_INPUT.json
"""
import json
import math
import sys
from multiprocessing import Pool

import numpy as np

B = 2000
N_ROWS = 2462
P_EXPOSED = 0.27
NOISE_SD = 250.0
FDR_ALPHA = 0.10
MIN_CELL = 5
MIN_COVERAGE = 0.50
MIN_EXPOSED = 50
MIN_CLUSTERS = 5
Z95 = 1.959964
ZPOW = 0.841621
CONF = 0.95


def gen_null(rng, K, gamma, m, beta):
    n = N_ROWS
    cl = rng.integers(0, K, size=n)
    cl[:K] = np.arange(K)
    x = rng.random(n) < P_EXPOSED
    zs = [rng.integers(0, 3, size=n) for _ in range(m)]
    lvl = np.zeros(n)
    for z in zs:
        lvl = lvl + gamma * (z - 1.0)
    # each Z carries its own prognostic effect; y variance grows with m, keep per-Z gamma scaled
    y = beta * x + lvl + NOISE_SD * rng.standard_normal(n)
    return cl, x, zs, y


def gen_confounded(rng, K, gamma):
    n = N_ROWS
    cl = rng.integers(0, K, size=n)
    cl[:K] = np.arange(K)
    z = rng.integers(0, 3, size=n)
    px = np.array([0.10, 0.27, 0.44])[z]
    x = rng.random(n) < px
    y = gamma * (z - 1.0) + NOISE_SD * rng.standard_normal(n)
    return cl, x, [z], y


def gen_mbias(rng, K, beta):
    n = N_ROWS
    cl = rng.integers(0, K, size=n)
    cl[:K] = np.arange(K)
    u1 = rng.standard_normal(n)
    u2 = rng.standard_normal(n)
    z = (u1 + u2 > 0).astype(int)
    x = rng.random(n) < 1.0 / (1.0 + np.exp(-(1.5 * u1 - 1.0)))
    y = beta * x + 150.0 * u2 + NOISE_SD * rng.standard_normal(n)
    return cl, x, [z], y


def point_estimates(cl, x, z, y):
    """Return dict with usable-strata info and point estimates; mirrors apply.py:337-381 + matched crude."""
    levels = np.unique(z)
    en = {}
    cn = {}
    es = {}
    cs = {}
    for lv in levels:
        s = z == lv
        en[lv] = int((s & x).sum())
        cn[lv] = int((s & ~x).sum())
        es[lv] = float(y[s & x].sum())
        cs[lv] = float(y[s & ~x].sum())
    usable = [lv for lv in levels if en[lv] >= MIN_CELL and cn[lv] >= MIN_CELL]
    tot_e = sum(en.values())
    use_e = sum(en[lv] for lv in usable)
    if not usable or use_e == 0:
        return None
    cov = use_e / tot_e
    h_z = sum((es[lv] / en[lv] - cs[lv] / cn[lv]) * en[lv] for lv in usable) / use_e
    keep = np.isin(z, usable)
    ye = y[keep & x]
    yc = y[keep & ~x]
    h_c = ye.mean() - yc.mean()
    return dict(usable=usable, coverage=cov, h_z=h_z, h_c=h_c, keep=keep)


def boot(cl, x, z, y, pe, rng):
    keep = pe["keep"]
    usable = pe["usable"]
    K = int(cl.max()) + 1
    S = len(usable)
    cm = np.zeros((K, S, 4))
    for si, lv in enumerate(usable):
        s = keep & (z == lv)
        for k_arm, mask in ((0, s & x), (2, s & ~x)):
            np.add.at(cm[:, si, k_arm], cl[mask], y[mask])
            np.add.at(cm[:, si, k_arm + 1], cl[mask], 1.0)
    counts = rng.multinomial(K, np.full(K, 1.0 / K), size=B)
    tot = np.einsum("bk,ksj->bsj", counts.astype(float), cm)
    es, en, cs, cn = tot[:, :, 0], tot[:, :, 1], tot[:, :, 2], tot[:, :, 3]
    ok = (en.sum(1) > 0) & (cn.sum(1) > 0)
    hc = es.sum(1) / np.where(en.sum(1) > 0, en.sum(1), 1) - cs.sum(1) / np.where(cn.sum(1) > 0, cn.sum(1), 1)
    valid = (en > 0) & (cn > 0)
    w = np.where(valid, en, 0.0)
    d = np.where(valid, es / np.where(en > 0, en, 1) - cs / np.where(cn > 0, cn, 1), 0.0)
    wsum = w.sum(1)
    ok &= wsum > 0
    hz = (w * d).sum(1) / np.where(wsum > 0, wsum, 1)
    return hc[ok], hz[ok]


def pct_ci(v, pt):
    o = np.sort(v)
    lo = o[max(0, int(len(o) * (1 - CONF) / 2))]
    hi = o[min(len(o) - 1, int(len(o) * (1 - (1 - CONF) / 2)))]
    lo, hi = min(lo, hi), max(lo, hi)
    return min(lo, pt), max(hi, pt)


def crit_fail(h, lo, hi, ne, nc, kcl, sd):
    f = set()
    if not h > 0:
        f.add("C1")
    if not (lo > 0 or hi < 0):
        f.add("C2")
    mde = (Z95 + ZPOW) * sd * math.sqrt(1.0 / ne + 1.0 / nc)
    if not (ne >= MIN_EXPOSED and kcl >= MIN_CLUSTERS and mde < abs(h)):
        f.add("C3")
    return f


def one_z(cl, x, z, y, rng):
    pe = point_estimates(cl, x, z, y)
    if pe is None or pe["coverage"] < MIN_COVERAGE:
        return None
    hc_b, hz_b = boot(cl, x, z, y, pe, rng)
    if len(hc_b) < 2:
        return None
    th_b = hc_b - hz_b
    se = float(np.std(th_b, ddof=1))
    if not (se > 0 and math.isfinite(se)):
        return None
    theta = pe["h_c"] - pe["h_z"]
    two = math.erfc(abs(theta) / se / math.sqrt(2.0))
    p = two / 2 if theta > 0 else 1 - two / 2
    keep = pe["keep"]
    ye, yc = y[keep & x], y[keep & ~x]
    ne, nc = len(ye), len(yc)
    sd = math.sqrt(((ne - 1) * ye.var(ddof=1) + (nc - 1) * yc.var(ddof=1)) / (ne + nc - 2))
    kcl = len(np.unique(cl[keep]))
    lo_c, hi_c = pct_ci(hc_b, pe["h_c"])
    lo_z, hi_z = pct_ci(hz_b, pe["h_z"])
    fc = crit_fail(pe["h_c"], lo_c, hi_c, ne, nc, kcl, sd)
    fa = crit_fail(pe["h_z"], lo_z, hi_z, ne, nc, kcl, sd)
    return dict(p=p, theta=theta, se=se, hc=pe["h_c"], hz=pe["h_z"], fc=fc, fa=fa)


def bh_reject(ps, m):
    """BH step-up at FDR_ALPHA with family_size m; returns reject flags in input order."""
    n = len(ps)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: ps[i])
    adj = [1.0] * n
    run = 1.0
    for rank, i in reversed(list(enumerate(order, start=1))):
        run = min(run, min(1.0, ps[i] * m / rank))
        adj[i] = run
    return [a <= FDR_ALPHA for a in adj]


def analyse(cl, x, zs, y, rng):
    m = len(zs)
    res = [one_z(cl, x, z, y, rng) for z in zs]
    assessed = [(i, r) for i, r in enumerate(res) if r is not None]
    rej = bh_reject([r["p"] for _, r in assessed], m)
    out = dict(assessed=len(assessed), reject_any=False, block_S=False, block_A=False, flip_S=False,
               flip_A=False, block_S_fc_nonempty=False, theta=None, se=None, hc=None, hz=None)
    for (i, r), rj in zip(assessed, rej):
        s_flag = len(r["fa"] - r["fc"]) > 0
        a_flag = len(r["fc"]) == 0 and len(r["fa"]) > 0
        out["reject_any"] |= rj
        out["flip_S"] |= s_flag
        out["flip_A"] |= a_flag
        if rj and s_flag:
            out["block_S"] = True
            if len(r["fc"]) > 0:
                out["block_S_fc_nonempty"] = True
        if rj and a_flag:
            out["block_A"] = True
    if assessed:
        r0 = assessed[0][1]
        out.update(theta=r0["theta"], se=r0["se"], hc=r0["hc"], hz=r0["hz"])
    return out


def cell_beta_bounds(gamma, m):
    sd = math.sqrt(NOISE_SD ** 2 + m * (2.0 / 3.0) * gamma ** 2)
    ne, nc = N_ROWS * P_EXPOSED, N_ROWS * (1 - P_EXPOSED)
    se = sd * math.sqrt(1 / ne + 1 / nc)
    b2, b3 = Z95 * se, (Z95 + ZPOW) * se
    return dict(b_c2=b2, b_c3=b3, b_mid=(b2 + b3) / 2, b_far=6 * se)


def run_cell(args):
    idx, spec, D = args
    ss = np.random.SeedSequence([20260925, idx])
    rng = np.random.default_rng(ss)
    rows = []
    for _ in range(D):
        if spec["kind"] == "null":
            cl, x, zs, y = gen_null(rng, spec["K"], spec["gamma"], spec["m"], spec["beta"])
        elif spec["kind"] == "confounded":
            cl, x, zs, y = gen_confounded(rng, spec["K"], spec["gamma"])
        else:
            cl, x, zs, y = gen_mbias(rng, spec["K"], spec["beta"])
        rows.append(analyse(cl, x, zs, y, rng))
    def rate(key):
        return sum(1 for r in rows if r[key]) / D
    sblocks = [r for r in rows if r["block_S"]]
    res = dict(spec=spec, D=D, assessed_share=sum(r["assessed"] for r in rows) / (D * spec.get("m", 1)),
               reject_any=rate("reject_any"), block_S=rate("block_S"), block_A=rate("block_A"),
               flip_S=rate("flip_S"), flip_A=rate("flip_A"),
               share_S_blocks_with_fc_nonempty=(sum(1 for r in sblocks if r["block_S_fc_nonempty"]) / len(sblocks)) if sblocks else None,
               mean_theta=float(np.nanmean([r["theta"] for r in rows if r["theta"] is not None])),
               mean_se_theta=float(np.nanmean([r["se"] for r in rows if r["se"] is not None])),
               mean_hc=float(np.nanmean([r["hc"] for r in rows if r["hc"] is not None])),
               mean_hz=float(np.nanmean([r["hz"] for r in rows if r["hz"] is not None])),
               frac_hz_lt_hc=sum(1 for r in rows if r["hc"] is not None and r["hz"] < r["hc"]) / D)
    # structural invariants (deterministic implications)
    res["invariant_S_ge_A"] = all((not r["block_A"]) or r["block_S"] for r in rows)
    res["invariant_block_le_flip"] = all((not r["block_S"]) or r["flip_S"] for r in rows)
    res["invariant_block_le_reject"] = all((not r["block_S"]) or r["reject_any"] for r in rows)
    return res


def build_cells():
    cells = []
    for K in (5, 10, 50):
        for gamma in (0.0, 300.0):
            for m in (1, 3):
                bb = cell_beta_bounds(gamma, m)
                for name in ("b_c2", "b_c3", "b_mid", "b_far"):
                    cells.append(dict(kind="null", K=K, gamma=gamma, m=m, beta_name=name, beta=bb[name]))
    cells.append(dict(kind="confounded", K=50, gamma=300.0, m=1, beta_name="beta0", beta=0.0))
    for beta in (80.0, 120.0):
        cells.append(dict(kind="mbias", K=50, gamma=0.0, m=1, beta_name=f"beta{int(beta)}", beta=beta))
    return cells


def main():
    mode = sys.argv[1]
    if mode == "run":
        D = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
        cells = build_cells()
        with Pool() as p:
            out = p.map(run_cell, [(i, c, D) for i, c in enumerate(cells)])
        json.dump(out, open(sys.argv[2], "w"), indent=1)
        for r in out:
            s = r["spec"]
            print(f"{s['kind']:10s} K={s['K']:3d} gamma={s['gamma']:5.0f} m={s['m']} {s['beta_name']:8s} beta={s['beta']:6.1f} "
                  f"reject_any={r['reject_any']:.4f} block_S={r['block_S']:.4f} block_A={r['block_A']:.4f} "
                  f"flip_S={r['flip_S']:.4f} flip_A={r['flip_A']:.4f} fcNE={r['share_S_blocks_with_fc_nonempty']} "
                  f"SEtheta={r['mean_se_theta']:.2f} hc={r['mean_hc']:.1f} hz={r['mean_hz']:.1f} "
                  f"assessed={r['assessed_share']:.3f} inv={r['invariant_S_ge_A']},{r['invariant_block_le_flip']},{r['invariant_block_le_reject']}")
    elif mode == "dump":
        rng = np.random.default_rng(7)
        outs = []
        for i in range(6):
            cl, x, zs, y = gen_null(rng, 10, 300.0, 1, 30.0) if i < 3 else gen_mbias(rng, 10, 80.0)
            z = zs[0]
            if i == 5:
                z = np.where(rng.random(len(z)) < 0.2, 9, z)  # thin/odd strata
            pe = point_estimates(cl, x, z, y)
            outs.append(dict(x=x.tolist(), z=z.tolist(), y=y.tolist(),
                             h_z=None if pe is None else pe["h_z"], coverage=None if pe is None else pe["coverage"],
                             h_c=None if pe is None else pe["h_c"]))
        json.dump(outs, open(sys.argv[2], "w"))


if __name__ == "__main__":
    main()
