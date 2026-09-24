"""P8r: boundary-size simulation of the designed statistic (numpy replica; NOT the real gate).
Chain of validation: numpy `stat_point` == pure-python `strat` (identical to the copy that matched the real
_stratified_adjustment on all 34 delivered-data pairs) checked below on random datasets."""
import json
import math
import sys
from multiprocessing import Pool
from statistics import NormalDist

import numpy as np

ND = NormalDist()
N = 2462
SD = 776.0
HE_RATIO = math.log(1.125) / 0.91          # 0.12943
B = 200
ALPHA = 0.10
Phi = np.vectorize(ND.cdf)


def strat_py(y, x, z):
    cells = {}
    for i in range(len(y)):
        c = cells.setdefault(z[i], [0.0, 0, 0.0, 0])
        if x[i]:
            c[0] += y[i]; c[1] += 1
        else:
            c[2] += y[i]; c[3] += 1
    tot_e = sum(c[1] for c in cells.values())
    usable = [c for c in cells.values() if c[1] >= 5 and c[3] >= 5]
    ue = sum(c[1] for c in usable)
    if not usable or ue == 0:
        return 0.0, 0.0, 0.0
    adj = sum((c[0] / c[1] - c[2] / c[3]) * c[1] for c in usable) / ue
    uc = sum(c[3] for c in usable)
    raw_u = sum(c[0] for c in usable) / ue - sum(c[2] for c in usable) / uc
    return adj, ue / tot_e, raw_u


def stat_np(yb, xb, zb):
    """Vectorised over leading axis (replicates). yb,xb,zb: (R, n) arrays; zb in {0,1}. Returns adj, cov, raw_u (R,)."""
    es = np.zeros(yb.shape[0]); num = np.zeros(yb.shape[0]); ue = np.zeros(yb.shape[0]); tot_e = xb.sum(1).astype(float)
    sum_e_u = np.zeros(yb.shape[0]); sum_c_u = np.zeros(yb.shape[0]); uc = np.zeros(yb.shape[0])
    for zv in (0, 1):
        m = (zb == zv)
        en = (m & xb).sum(1).astype(float)
        cn = (m & ~xb).sum(1).astype(float)
        esum = np.where(m & xb, yb, 0.0).sum(1)
        csum = np.where(m & ~xb, yb, 0.0).sum(1)
        ok = (en >= 5) & (cn >= 5)
        with np.errstate(divide="ignore", invalid="ignore"):
            diff = np.where(ok, esum / np.where(en > 0, en, 1) - csum / np.where(cn > 0, cn, 1), 0.0)
        num += diff * en * ok
        ue += en * ok
        sum_e_u += esum * ok
        sum_c_u += csum * ok
        uc += cn * ok
    with np.errstate(divide="ignore", invalid="ignore"):
        adj = np.where(ue > 0, num / np.where(ue > 0, ue, 1), 0.0)
        raw_u = np.where(ue > 0, sum_e_u / np.where(ue > 0, ue, 1) - sum_c_u / np.where(uc > 0, uc, 1), 0.0)
        cov = np.where(tot_e > 0, ue / np.where(tot_e > 0, tot_e, 1), 0.0)
    return adj, cov, raw_u


def population_attenuation(w1, A, p=0.4):
    """Exact population single-Z1 attenuation: score = w1*Z1 + (1-w1)*U, X~Bern(0.03+0.62 score), Y=-A score."""
    cells = []
    for z in (0, 1):
        for u in (0, 1):
            pr = (p if z else 1 - p) * (p if u else 1 - p)
            sc = w1 * z + (1 - w1) * u
            px = 0.03 + 0.62 * sc
            cells.append((z, u, pr, px, -A * sc))
    pe = sum(pr * px for _, _, pr, px, _ in cells); pc = sum(pr * (1 - px) for _, _, pr, px, _ in cells)
    raw = sum(pr * px * y for _, _, pr, px, y in cells) / pe - sum(pr * (1 - px) * y for _, _, pr, px, y in cells) / pc
    num = 0.0; den = 0.0
    for z in (0, 1):
        cz = [c for c in cells if c[0] == z]
        pez = sum(c[2] * c[3] for c in cz); pcz = sum(c[2] * (1 - c[3]) for c in cz)
        d = sum(c[2] * c[3] * c[4] for c in cz) / pez - sum(c[2] * (1 - c[3]) * c[4] for c in cz) / pcz
        num += d * pez; den += pez
    adj = num / den
    return 1 - adj / raw, -raw  # attenuation, harm per unit A (harm = -raw... raw diff negative => harm positive)


def calibrate_att(target_att=0.5):
    lo, hi = 0.5, 0.99
    for _ in range(80):
        mid = (lo + hi) / 2
        a, _ = population_attenuation(mid, 1.0)
        if a < target_att:
            lo = mid
        else:
            hi = mid
    w1 = (lo + hi) / 2
    a, harm_per_A = population_attenuation(w1, 1.0)
    return w1, a, harm_per_A


def make_data(kind, m, H, rng):
    Z = (rng.random((N, m)) < 0.4)
    noise = rng.normal(0, SD, N)
    if kind == "att":
        U = rng.random(N) < 0.4
        w1, _, hpa = CAL["att"]
        score = w1 * Z[:, 0] + (1 - w1) * U
        x = rng.random(N) < 0.03 + 0.62 * score
        A = H / hpa
        y = 400.0 - A * score + noise
    elif kind == "E":            # H_Z = h_E exactly; raw H
        delta = HE_RATIO * SD
        score = Z[:, 0].astype(float)
        x = rng.random(N) < 0.03 + 0.62 * score
        c = CE["c"]
        y = 400.0 - delta * x - c * score + noise
    elif kind == "E2":           # no confounding; H_raw = H_Z = h_E
        delta = HE_RATIO * SD
        x = rng.random(N) < 0.27
        y = 400.0 - delta * x + noise
    elif kind == "null":         # genuine effect H, no confounding
        x = rng.random(N) < 0.27
        y = 400.0 - H * x + noise
    return y, x, Z


def calibrate_E(target_raw=150.0):
    # raw harm = delta + c * imbalance(Z1 | X) ; Z1 ~ Bern(.4), X ~ Bern(.03+.62 Z1); solve c for raw=target
    delta = HE_RATIO * SD
    p = 0.4
    pe = p * 0.65 + (1 - p) * 0.03; pc = 1 - pe
    ez = p * 0.65 / pe; cz = p * 0.35 / pc
    imb = ez - cz
    c = (target_raw - delta) / imb
    return dict(c=c, imb=imb, delta=delta)


CAL = {"att": calibrate_att(0.5)}
CE = calibrate_E(150.0)


def one_dataset(args):
    kind, m, H, seed = args
    rng = np.random.default_rng(seed)
    y, x, Z = make_data(kind, m, H, rng)
    zi = Z.astype(np.int8)
    idx = rng.integers(0, N, size=(B, N))
    yb = y[idx]; xb = x[idx]
    out = []
    ne = y[x]; nc = y[~x]
    psd = math.sqrt(((len(ne) - 1) * ne.var(ddof=0) + (len(nc) - 1) * nc.var(ddof=0)) / (len(ne) + len(nc) - 2))
    hE = HE_RATIO * psd
    pzs = []
    detail0 = None
    for j in range(m):
        adj, cov, ru = stat_np(y[None, :], x[None, :], zi[None, :, j])
        Hz = -adj[0]; Hr = -ru[0]
        a_b, c_b, ru_b = stat_np(yb, xb, zi[:, j][idx])
        Dz = -a_b - 0.5 * (-ru_b)
        seD = Dz.std(ddof=1); seHz = (-a_b).std(ddof=1)
        D = Hz - 0.5 * Hr
        p_att = ND.cdf(D / seD) if seD > 0 else 1.0
        E_ok = Hr >= hE
        p_E = ND.cdf((Hz - hE) / seHz) if (E_ok and seHz > 0) else 1.0
        pz = min(1.0, 2 * min(p_att, p_E))
        assessed = cov[0] >= 0.5
        pzs.append(pz if assessed else 1.0)
        if j == 0:
            detail0 = (p_att, p_E, E_ok, Hz, Hr, seD)
    block = min(pzs) <= ALPHA / m
    return block, detail0


def selfcheck():
    rng = np.random.default_rng(1)
    for _ in range(5):
        y, x, Z = make_data("att", 3, 200.0, rng)
        a, c, r = stat_np(y[None, :], x[None, :], Z[None, :, 0].astype(np.int8))
        pa, pc, pr = strat_py(list(y), list(x), list(Z[:, 0].astype(int)))
        assert abs(a[0] - pa) < 1e-6 and abs(c[0] - pc) < 1e-9 and abs(r[0] - pr) < 1e-6, (a, pa, r, pr)
    print("selfcheck numpy replica == pure-python strat (== real _stratified_adjustment on delivered pairs): OK", flush=True)


if __name__ == "__main__":
    selfcheck()
    w1, a_true, hpa = CAL["att"]
    print("calibration att: w1=%.4f true attenuation=%.6f harm per A=%.4f" % (w1, a_true, hpa), "E:", CE, flush=True)
    NDS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    cells = []
    for m in (3, 7, 10):
        for H in (100.0, 200.0, 400.0):
            cells.append(("att", m, H))
    for m in (3, 10):
        cells.append(("E", m, 150.0))
    for m in (3, 10):
        cells.append(("E2", m, 0.0))
    for m in (3, 10):
        cells.append(("null", m, 200.0))
    results = {}
    with Pool(11) as pool:
        for kind, m, H in cells:
            args = [(kind, m, H, 10_000 * (hash((kind, m, int(H))) % 1000) + s) for s in range(NDS)]
            r = pool.map(one_dataset, args, chunksize=20)
            blocks = np.array([b for b, _ in r])
            d0 = [d for _, d in r]
            p_att = np.array([d[0] for d in d0]); p_E = np.array([d[1] for d in d0]); E_ok = np.array([d[2] for d in d0])
            rec = dict(kind=kind, m=m, H=H, n=NDS, block_rate=float(blocks.mean()), blocks=int(blocks.sum()),
                       z1_p_att_le_005=float((p_att <= 0.05).mean()), z1_p_att_le_001=float((p_att <= 0.01).mean()),
                       z1_p_att_le_0005=float((p_att <= 0.005).mean()),
                       z1_E_applicable=float(E_ok.mean()), z1_p_E_le_005_given_applicable=float((p_E[E_ok] <= 0.05).mean()) if E_ok.any() else None,
                       z1_p_E_le_001_given_applicable=float((p_E[E_ok] <= 0.01).mean()) if E_ok.any() else None,
                       z1_mean_Hz=float(np.mean([d[3] for d in d0])), z1_mean_Hraw=float(np.mean([d[4] for d in d0])),
                       z1_mean_seD=float(np.mean([d[5] for d in d0])))
            results[f"{kind}|m={m}|H={int(H)}"] = rec
            print(json.dumps(rec), flush=True)
    json.dump(results, open("<scratch>", "w"), indent=1)
