"""TASK-107 Phase 1 - oracle-detectability feasibility on a PROTOTYPE v2 generator (READ-ONLY).

The prototype is NOT the frozen v2 generator: it is the real, unmodified `_generate_row` source
with one hook inserted (text substitution at import time, nothing written to the repository)
that adds the v2 candidate targets' effects. It consumes exactly the same RNG draws as v1, so
covariates are identical to v1 for equal seeds. Fidelity is checked by `fidelity` (no targets =>
byte-identical rows). Real contract functions (`run_validation`) grade the oracles. No engine run.

Usage:
  fidelity                 -> asserts prototype (no targets) == real generator for a seed
  seed --seed S --out F    -> one calibration draw, three families
  rates --dir D --out F    -> aggregate rates with Wilson intervals
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import inspect
import json
import math
import random
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

import polars as pl  # noqa: E402
from diagnose_oracle_decomposition import build_projection, parse_true_rule  # noqa: E402
from diagnose_task106_fn_autopsy import (  # noqa: E402
    PREDICTIVE_OR_ABOVE,
    _augment_with_exact_columns,
    _validate_rules,
    frozen_version_record,
)
from evaluate_benchmark import _scoreable_pattern_ids  # noqa: E402
from policy_analytics import synthetic_benchmark as sb  # noqa: E402
from policy_analytics.analytical_dataset import build_analytical_dataset  # noqa: E402
from policy_analytics.discovery.engine import Condition, DiscoveryConfig, _atoms  # noqa: E402
from policy_analytics.validation.apply import load_analytical_frame  # noqa: E402

DOSE = {"H": (410, 1.05, 0.75), "M": (300, 0.75, 0.5), "L": (240, 0.5, 0.3)}

#: id, dose, rule string (ground-truth grammar), predicate over covariates, kind
V2_SPEC: list[dict[str, Any]] = [
    {"id": "N01", "dose": "H", "rule": "customer_segment=corporate AND destination=Reykjavik AND booking_lead_days<23",
     "pred": lambda c: c["segment"] == "corporate" and c["destination"] == "Reykjavik" and c["lead_time"] < 23},
    {"id": "N02", "dose": "M", "rule": "product_category=premium AND acquisition_channel=partner AND discount_rate>=0.08",
     "pred": lambda c: c["category"] == "premium" and c["channel"] == "partner" and c["discount"] >= 0.08},
    {"id": "N03", "dose": "H", "rule": "supplier=Cedar AND customer_segment=family AND trip_duration_days>=10",
     "pred": lambda c: c["supplier"] == "Cedar" and c["segment"] == "family" and c["trip_duration"] >= 10},
    {"id": "N04", "dose": "M", "rule": "manager=Manager 6 AND destination=Rome AND installments>=2",
     "pred": lambda c: c["manager"] == "Manager 6" and c["destination"] == "Rome" and c["installments"] >= 2},
    {"id": "N05", "dose": "M", "rule": "customer_segment=corporate AND payment_method=wallet",
     "pred": lambda c: c["segment"] == "corporate" and c["payment_method"] == "wallet"},
    {"id": "N06", "dose": "M", "rule": "destination=Lisbon AND acquisition_channel=referral",
     "pred": lambda c: c["destination"] == "Lisbon" and c["channel"] == "referral"},
    {"id": "N07", "dose": "H", "rule": "manager=Manager 7 AND acquisition_channel=direct AND trip_duration_days>=8",
     "pred": lambda c: c["manager"] == "Manager 7" and c["channel"] == "direct" and c["trip_duration"] >= 8},
    {"id": "N08", "dose": "L", "rule": "payment_method=card AND customer_segment=family AND installments>=3",
     "pred": lambda c: c["payment_method"] == "card" and c["segment"] == "family" and c["installments"] >= 3},
    {"id": "O1", "dose": "H", "rule": "destination=Rome AND customer_segment=family AND party_size>=5 AND product_category=premium",
     "pred": lambda c: c["destination"] == "Rome" and c["segment"] == "family" and c["party_size"] >= 5 and c["category"] == "premium"},
    {"id": "O2", "dose": "H", "rule": "manager=Manager 8 AND customer_segment=leisure AND booking_month IN [1,2,12]",
     "pred": lambda c: c["manager"] == "Manager 8" and c["segment"] == "leisure" and c["month"] in (1, 2, 12)},
]
V2_TARGETS: list[dict[str, Any]] = []  # populated below (dose resolved)

_ANCHOR = "    cancellation = rng.random() < _sigmoid(cancel_logit)"
_HOOK = '''    _cv = dict(month=month, segment=segment, customer_type=customer_type, destination=destination,
               lead_time=lead_time, party_size=party_size, trip_duration=trip_duration,
               category=category, channel=channel, manager=manager, supplier=supplier,
               discount=discount, payment_method=payment_method, installments=installments)
    for _t in V2_TARGETS:
        if _t["pred"](_cv):
            patterns.append(_t["id"])
            if disabled_pattern_id != _t["id"]:
                loss += _t["dose"][0] * effect
                cancel_logit += _t["dose"][1] * effect
                support_lambda += _t["dose"][2] * effect
'''


def _build_prototype() -> Any:
    src = inspect.getsource(sb._generate_row)
    assert src.count(_ANCHOR) == 1
    src = src.replace(_ANCHOR, _HOOK + _ANCHOR)
    ns: dict[str, Any] = dict(sb.__dict__)
    ns["V2_TARGETS"] = V2_TARGETS
    exec(compile(src, "<v2-prototype>", "exec"), ns)  # noqa: S102
    return ns["_generate_row"]


gen_proto = _build_prototype()
FAMILIES = (36791, 26213, 60000)
V1_IDS = [f"P{n:02d}" for n in range(1, 10)]
TRAP_BARE = {
    "T01": ("manager", "Manager 2"), "T02": ("supplier", "Atlas"),
    "T03": ("acquisition_channel", "paid_search"), "T04": ("payment_method", "bank_transfer"),
    "T05": ("manual_exception", True),
}
V1_RULES = {p["id"]: p["rule"] for p in json.loads(
    (REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json").read_text())["patterns"]}


def fidelity(seed: int = 20260813) -> None:
    saved = list(V2_TARGETS)
    V2_TARGETS.clear()
    cfg = sb.BenchmarkConfig(seed=seed)
    r1, r2 = random.Random(seed), random.Random(seed)
    bad = 0
    for i in range(cfg.row_count):
        a = sb._generate_row(i, r1, cfg)
        b = gen_proto(i, r2, cfg)
        bad += int(a != b)
    V2_TARGETS.extend(saved)
    print(f"fidelity seed {seed}: rows differing = {bad} of {cfg.row_count}")
    if bad:
        raise SystemExit(1)


def _generate(seed: int, work: Path) -> tuple[Path, dict[str, list[str]]]:
    cfg = sb.BenchmarkConfig(seed=seed)
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    members: dict[str, list[str]] = {}
    for i in range(cfg.row_count):
        row, pats = gen_proto(i, rng, cfg)
        rows.append(row)
        for p in pats:
            members.setdefault(p, []).append(str(row["booking_id"]))
    sb._write_csv(work / "clean.csv", rows)
    sb._write_json(work / "timing.json", sb._feature_metadata())
    manifest = build_analytical_dataset(work / "clean.csv", work / "timing.json", work / "a")
    return work / "a" / str(manifest["dataset_version"]), members


def run_seed(seed: int, out: Path) -> None:
    frozen_version_record()
    with tempfile.TemporaryDirectory(prefix=f"t107-{seed}-") as tmp:
        work = Path(tmp)
        root, members = _generate(seed, work)
        manifest = json.loads((root / "manifest.json").read_text())
        frame = load_analytical_frame(root)
        timing = {n: str(m["classification"]) for n, m in manifest["feature_timing"].items()}
        feats = tuple(n for n in frame.columns if timing.get(n) == "DECISION_TIME" and n not in {"booking_date", "travel_date"})
        dev = frame.filter(pl.col("split_label") == "development")
        dev_ids = frozenset(cast("list[str]", dev["booking_id"].to_list()))
        ids = cast("list[str]", frame["booking_id"].to_list())
        index_of = {b: i for i, b in enumerate(ids)}
        gt_like = {"patterns": [{"id": k, "affected_booking_ids": v} for k, v in members.items()]}
        scoreable = list(_scoreable_pattern_ids(gt_like, dev_ids))
        rules_str = {**V1_RULES, **{t["id"]: t["rule"] for t in V2_SPEC}}
        masks: dict[str, int] = {}
        for pid, bl in members.items():
            m = 0
            for b in bl:
                m |= 1 << index_of[b]
            masks[pid] = m
        atoms = _atoms(dev, feats, DiscoveryConfig())
        cols = frozenset(frame.columns)
        cond_rules: list[tuple[str, tuple[Condition, ...]]] = []
        proj_rules: list[tuple[str, tuple[Condition, ...]]] = []
        info: dict[str, Any] = {}
        for pid in scoreable:
            tcs = parse_true_rule(rules_str[pid])
            n_dev = len(dev_ids & set(members[pid]))
            info[pid] = {"n_affected": len(members[pid]), "n_dev": n_dev, "rule": rules_str[pid]}
            ops = {">=": "ge", "<": "lt", "=": "eq"}
            if all(tc.feature in cols and tc.operator in ops for tc in tcs):
                cond_rules.append((pid, tuple(Condition(tc.feature, cast(Any, ops[tc.operator]), tc.value) for tc in tcs)))  # type: ignore[arg-type]
            proj = build_projection(pid, rules_str[pid], atoms, feats, cols, timing, dev, DiscoveryConfig())
            if not proj.over_depth and proj.atoms:
                proj_rules.append((pid, proj.atoms))
                a = masks[pid]
                e = 0
                from diagnose_oracle_decomposition import _frame_mask, _rule_expr_local
                e = _frame_mask(frame, _rule_expr_local(proj.atoms))
                info[pid]["projection_jaccard"] = (e & a).bit_count() / (e | a).bit_count()
                info[pid]["projection_rule"] = " AND ".join(f"{c.feature} {c.operator} {c.value}" for c in proj.atoms)
        atom_root = _augment_with_exact_columns(root, work, frame, masks, scoreable)
        atom_rules = [(pid, (Condition(f"oracle_exact_{pid}", "eq", True),)) for pid in scoreable]
        trap_rules = [(tid, (Condition(f, "eq", v),)) for tid, (f, v) in TRAP_BARE.items()]
        result: dict[str, Any] = {"seed": seed, "scoreable": scoreable, "info": info, "families": {}}
        for fam in FAMILIES:
            fr: dict[str, Any] = {}
            fr["atom"] = _validate_rules(atom_root, atom_rules, fam, f"atom-{seed}-{fam}")
            fr["cond"] = _validate_rules(root, cond_rules, fam, f"cond-{seed}-{fam}") if cond_rules else {}
            fr["proj"] = _validate_rules(root, proj_rules, fam, f"proj-{seed}-{fam}") if proj_rules else {}
            fr["trap"] = _validate_rules(root, trap_rules, fam, f"trap-{seed}-{fam}")
            result["families"][str(fam)] = fr
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n")


def _wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rates(d: Path, out: Path) -> None:
    files = sorted(d.glob("seed-*.json"))
    data = [json.loads(f.read_text()) for f in files]
    res: dict[str, Any] = {"n_seeds": len(data)}
    ids = V1_IDS + [t["id"] for t in V2_SPEC] + list(TRAP_BARE)
    for pid in ids:
        entry: dict[str, Any] = {}
        for fam in FAMILIES:
            for kind in ("atom", "cond", "proj", "trap"):
                rows = [x["families"][str(fam)][kind][pid] for x in data
                        if pid in x["families"][str(fam)][kind] and (pid in x["scoreable"] or kind == "trap")]
                if not rows:
                    continue
                k = sum(r["evidence_level"] in PREDICTIVE_OR_ABOVE for r in rows)
                fails: dict[str, int] = {}
                for r in rows:
                    for g in r["level2_failed_gates"]:
                        fails[g] = fails.get(g, 0) + 1
                entry[f"{kind}@{fam}"] = {"k": k, "n": len(rows), "rate": k / len(rows), "wilson95": _wilson(k, len(rows)), "gate_failures": dict(sorted(fails.items()))}
        sc = [x for x in data if pid in x["info"]]
        if sc:
            entry["n_affected_median"] = sorted(x["info"][pid]["n_affected"] for x in sc)[len(sc) // 2]
            entry["n_dev_median"] = sorted(x["info"][pid]["n_dev"] for x in sc)[len(sc) // 2]
            entry["seeds_scoreable"] = len(sc)
            pj = [x["info"][pid]["projection_jaccard"] for x in sc if "projection_jaccard" in x["info"][pid]]
            if pj:
                entry["projection_jaccard_median"] = sorted(pj)[len(pj) // 2]
        res[pid] = entry
    out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    for pid in ids:
        e = res[pid]
        print(pid, e.get("n_affected_median"), e.get("n_dev_median"),
              {k: f"{v['k']}/{v['n']}" for k, v in e.items() if k.endswith("@36791")})


for _t in V2_SPEC:  # module level: multiprocessing 'spawn' workers re-import this module
    V2_TARGETS.append({"id": _t["id"], "pred": _t["pred"], "dose": DOSE[_t["dose"]]})


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fidelity")
    s = sub.add_parser("seed")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("batch")
    b.add_argument("--seeds", type=int, nargs=2, required=True)
    b.add_argument("--dir", type=Path, required=True)
    b.add_argument("--procs", type=int, default=10)
    r = sub.add_parser("rates")
    r.add_argument("--dir", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "fidelity":
        fidelity()
    elif a.cmd == "seed":
        run_seed(a.seed, a.out)
    elif a.cmd == "batch":
        seeds = list(range(a.seeds[0], a.seeds[1] + 1))
        with Pool(a.procs) as pool:
            pool.starmap(run_seed, [(s_, a.dir / f"seed-{s_}.json") for s_ in seeds])
    else:
        rates(a.dir, a.out)


if __name__ == "__main__":
    main()
