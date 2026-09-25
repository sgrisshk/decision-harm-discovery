"""TASK-107 Phase 2a - C5 (FC1): literal-plus-confounder composite check for T01-T05 (READ-ONLY).

Definition and predictions were fixed in `c5-predictions.md` (committed before this file existed).
No engine, no discovery search: only the real atom-grid builder `_atoms` and the real, unmodified
`run_validation` (contract 1.3.0) on hand-built rules, as in TASK-106/TASK-107 Phase 1.

  seed --seed S --draw {v2clean,v1} --out F   one draw: enumerate composites, rank, validate
  batch --seeds A B --draw D --dir DIR --procs N
  rates --dir DIR --out F                     aggregate with Wilson 95% intervals
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import tempfile
from itertools import combinations
from multiprocessing import Pool
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

import polars as pl  # noqa: E402
from diagnose_oracle_decomposition import _rule_expr_local  # noqa: E402
from diagnose_task106_fn_autopsy import (  # noqa: E402
    PREDICTIVE_OR_ABOVE,
    _validate_rules,
    frozen_version_record,
)
from policy_analytics import synthetic_benchmark as sb  # noqa: E402
from policy_analytics import synthetic_benchmark_v2 as sb2  # noqa: E402
from policy_analytics.analytical_dataset import build_analytical_dataset  # noqa: E402
from policy_analytics.discovery.engine import Condition, DiscoveryConfig, _atoms  # noqa: E402
from policy_analytics.validation.apply import load_analytical_frame  # noqa: E402

FAMILY = 60000  # ADR-107 D8
TOP_K = 15
MIN_DEV_N = 40
MAX_SUPPORT = 0.40
OUTCOME = "contribution_margin_eur"  # primary outcome; lower is worse
PROMOTED = ("shadow_policy", "high_confidence")
GT = json.loads(
    (REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json").read_text(encoding="utf-8")
)
TRAPS: dict[str, tuple[Condition, tuple[str, ...]]] = {}
for _t in GT["confounding_traps"]:
    _f, _, _v = str(_t["apparent_feature"]).partition("=")
    _val: object = True if _v == "true" else False if _v == "false" else _v
    TRAPS[str(_t["id"])] = (
        Condition(_f, "eq", cast(Any, _val)),
        tuple(x for x in _t["confounded_by"] if x != "booking_month"),
    )


def _build(seed: int, draw: str, work: Path) -> Path:
    if draw == "v2clean":
        return sb2.materialize_analytical(sb2.generate_v2(sb2.V2Config(seed=seed), ()), work)
    cfg = sb.BenchmarkConfig(seed=seed)
    rng = random.Random(seed)
    rows = [sb._generate_row(i, rng, cfg)[0] for i in range(cfg.row_count)]
    sb._write_csv(work / "clean.csv", rows)
    sb._write_json(work / "timing.json", sb._feature_metadata())
    manifest = build_analytical_dataset(work / "clean.csv", work / "timing.json", work / "a")
    return work / "a" / str(manifest["dataset_version"])


def _tstat_harm(y: pl.Series, mask: pl.Series) -> float:
    a, b = y.filter(mask), y.filter(~mask)
    if len(a) < 2 or len(b) < 2:
        return float("-inf")
    se = math.sqrt(cast(float, a.var()) / len(a) + cast(float, b.var()) / len(b))
    return (cast(float, b.mean()) - cast(float, a.mean())) / se if se > 0 else float("-inf")


def run_seed(seed: int, draw: str, out: Path) -> None:
    frozen_version_record()
    with tempfile.TemporaryDirectory(prefix=f"c5-{draw}-{seed}-") as tmp:
        root = _build(seed, draw, Path(tmp))
        manifest = json.loads((root / "manifest.json").read_text())
        frame = load_analytical_frame(root)
        timing = {n: str(m["classification"]) for n, m in manifest["feature_timing"].items()}
        feats = tuple(
            n
            for n in frame.columns
            if timing.get(n) == "DECISION_TIME" and n not in {"booking_date", "travel_date"}
        )
        dev_mask = frame["split_label"] == "development"
        y_dev = frame.filter(dev_mask)[OUTCOME].cast(pl.Float64)
        atoms = _atoms(frame.filter(pl.col("split_label") == "development"), feats, DiscoveryConfig())
        n = frame.height
        cache: dict[Condition, pl.Series] = {}

        def m(c: Condition) -> pl.Series:
            if c not in cache:
                cache[c] = frame.select(_rule_expr_local((c,)).alias("m"))["m"].fill_null(False)
            return cache[c]

        result: dict[str, Any] = {"seed": seed, "draw": draw, "family": FAMILY, "traps": {}}
        for tid, (lit, conf) in TRAPS.items():
            conf_atoms = [a for a in atoms if a.feature in conf and a.feature != lit.feature]
            combos: list[tuple[Condition, ...]] = [(a,) for a in conf_atoms]
            for a, b in combinations(conf_atoms, 2):
                if a.feature != b.feature:
                    combos.append((a, b))
            scored: list[tuple[float, tuple[Condition, ...]]] = []
            for extra in combos:
                rule = (lit, *extra)
                mask = m(lit)
                for c in extra:
                    mask = mask & m(c)
                dev_n = int((mask & dev_mask).sum())
                if dev_n < MIN_DEV_N or int(mask.sum()) > MAX_SUPPORT * n:
                    continue
                scored.append((_tstat_harm(y_dev, mask.filter(dev_mask)), rule))
            scored.sort(key=lambda x: (-x[0], str(x[1])))
            top = scored[:TOP_K]
            rules = [(f"{tid}-bare", (lit,))] + [(f"{tid}-c{i:02d}", r) for i, (_, r) in enumerate(top)]
            val = _validate_rules(root, rules, FAMILY, f"c5-{draw}-{seed}-{tid}")
            entries = []
            for (cid, rule), (t, _) in zip(rules[1:], top, strict=True):
                v = val[cid]
                entries.append(
                    {
                        "id": cid,
                        "rule": " AND ".join(f"{c.feature} {c.operator} {c.value}" for c in rule),
                        "dev_t_harm": t,
                        "evidence_level": v["evidence_level"],
                        "policy_readiness": v["policy_readiness"],
                        "level2_failed_gates": v["level2_failed_gates"],
                        "failed_gates": v["failed_gates"],
                    }
                )
            result["traps"][tid] = {
                "n_eligible_composites": len(scored),
                "bare": val[f"{tid}-bare"],
                "composites": entries,
            }
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
    data = [json.loads(f.read_text()) for f in sorted(d.glob("seed-*.json"))]
    res: dict[str, Any] = {"n_seeds": len(data), "family": FAMILY, "top_k": TOP_K, "traps": {}}
    for tid in TRAPS:
        rows = [x["traps"][tid] for x in data]
        n = len(rows)
        bare_k = sum(r["bare"]["evidence_level"] in PREDICTIVE_OR_ABOVE for r in rows)
        comp_k = sum(any(c["evidence_level"] in PREDICTIVE_OR_ABOVE for c in r["composites"]) for r in rows)
        promo_k = sum(any(c["policy_readiness"] in PROMOTED for c in r["composites"]) for r in rows)
        bare_promo = [str(x["seed"]) for x, r in zip(data, rows, strict=True)
                      if r["bare"]["policy_readiness"] in PROMOTED]
        bare_levels: dict[str, int] = {}
        for r in rows:
            bare_levels[r["bare"]["evidence_level"]] = bare_levels.get(r["bare"]["evidence_level"], 0) + 1
        no_comp = sum(len(r["composites"]) == 0 for r in rows)
        gates: dict[str, int] = {}
        for r in rows:
            if r["composites"]:
                for g in r["composites"][0]["level2_failed_gates"]:
                    gates[g] = gates.get(g, 0) + 1
        res["traps"][tid] = {
            "n": n,
            "seeds_without_eligible_composite": no_comp,
            "bare_predictive": {"k": bare_k, "wilson95": _wilson(bare_k, n)},
            "bare_promoted_shadow_or_above": {
                "k": len(bare_promo), "wilson95": _wilson(len(bare_promo), n), "seeds": bare_promo,
            },
            "bare_evidence_levels": dict(sorted(bare_levels.items())),
            "composite_predictive": {"k": comp_k, "wilson95": _wilson(comp_k, n)},
            "composite_promoted_shadow_or_above": {"k": promo_k, "wilson95": _wilson(promo_k, n)},
            "top_ranked_composite_level2_gate_failures": dict(sorted(gates.items())),
            "levels_seen": sorted({c["evidence_level"] for r in rows for c in r["composites"]}),
        }
    out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    for tid, e in res["traps"].items():
        print(tid, {k: (f"{v['k']}/{e['n']}" if isinstance(v, dict) and "k" in v else v) for k, v in e.items()})


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--draw", choices=("v2clean", "v1"), required=True)
    s.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("batch")
    b.add_argument("--seeds", type=int, nargs=2, required=True)
    b.add_argument("--draw", choices=("v2clean", "v1"), required=True)
    b.add_argument("--dir", type=Path, required=True)
    b.add_argument("--procs", type=int, default=10)
    r = sub.add_parser("rates")
    r.add_argument("--dir", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "seed":
        run_seed(a.seed, a.draw, a.out)
    elif a.cmd == "batch":
        seeds = range(a.seeds[0], a.seeds[1] + 1)
        with Pool(a.procs) as pool:
            pool.starmap(run_seed, [(s_, a.draw, a.dir / f"seed-{s_}.json") for s_ in seeds])
    else:
        rates(a.dir, a.out)


if __name__ == "__main__":
    main()
