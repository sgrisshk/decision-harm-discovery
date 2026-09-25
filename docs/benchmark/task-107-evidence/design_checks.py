"""TASK-107 Phase 2b design-stage structural checks on the composite (design-check seeds only).

Contract-free and engine-free: real `_atoms` grid builder for the on-grid check, the scorer's
`effective_rule` for non-degeneracy, and a Welch-t power PROXY of `contribution_margin_eur`
(exposed vs rest, development split), anchored on Phase 1 (`power_proxy_anchor.py`). Reports:
  prevalence (n_aff, n_dev), proxy t, engine-language checks L1-L4, on-grid (L5 precondition),
  non-degeneracy K(T)=T at nu, pairwise overlap / nesting, categorical-literal reuse, C3/C4.
Usage: design_checks.py SEED_LO SEED_HI OUT_JSON
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import statistics
import sys
import tempfile
from itertools import combinations
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_common as vc  # noqa: E402
from policy_analytics.discovery.engine import DiscoveryConfig, _atoms  # noqa: E402

import polars as pl  # noqa: E402

tg = vc.tg
scoring = vc.scoring
CATEGORICAL = {
    "destination",
    "supplier",
    "product_category",
    "manager",
    "acquisition_channel",
    "customer_segment",
    "customer_type",
    "payment_method",
    "manual_exception",
}


def welch_t(exposed: list[float], rest: list[float]) -> float:
    if len(exposed) < 3:
        return float("nan")
    va, vb = statistics.variance(exposed), statistics.variance(rest)
    se = (va / len(exposed) + vb / len(rest)) ** 0.5
    return (statistics.fmean(rest) - statistics.fmean(exposed)) / se


def static_checks() -> dict[str, Any]:
    out: dict[str, Any] = {"designs": {}, "literal_reuse": {}, "errors": []}
    seen: dict[str, list[str]] = {}
    trap_lits = {(c.feature, c.value) for c in vc.TRAP_LITERALS.values()}
    for d in tg.DESIGNS:
        conds = d.conditions
        feats = [c.feature for c in conds]
        info: dict[str, Any] = {
            "n_conditions": len(conds),
            "L1_le_max_conditions": len(conds) <= vc.ENGINE_MAX_CONDITIONS,
            "L4_one_condition_per_feature": len(set(feats)) == len(feats),
            "L3_operators_ok": all(
                (c.operator == "eq") == (c.feature in CATEGORICAL) and c.operator != "in"
                for c in conds
            ),
        }
        has_trap = [
            f"{c.feature}={c.value}"
            for c in conds
            if c.operator == "eq" and (c.feature, c.value) in trap_lits
        ]
        info["trap_literals"] = has_trap
        info["C3_literal_disjoint"] = not has_trap
        info["declared_class"] = d.declared_class
        if d.declared_class == "declared_overlap":
            if not has_trap:
                out["errors"].append(f"{d.target_id}: declared_overlap without a trap literal")
        elif has_trap:
            out["errors"].append(f"{d.target_id}: trap literal {has_trap} outside declared_overlap")
        for c in conds:
            if c.operator == "eq":
                seen.setdefault(f"{c.feature}={c.value}", []).append(d.target_id)
        out["designs"][d.target_id] = info
    out["literal_reuse"] = {k: v for k, v in seen.items() if len(v) > 1}
    # structural rule R3: two targets share at most ONE categorical literal
    for a, b in combinations(tg.DESIGNS, 2):
        shared = [
            f"{c.feature}={c.value}"
            for c in a.conditions
            if c.operator == "eq" and c in b.conditions
        ]
        if len(shared) > 1:
            out["errors"].append(f"{a.target_id}|{b.target_id} share >1 categorical literal {shared}")
    return out


def check_seed(seed: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"dc-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        frame = draw.frame
        dev_mask = draw.space.dev_mask
        y = frame["contribution_margin_eur"].cast(pl.Float64).to_list()
        dev_idx = [i for i in range(len(y)) if dev_mask >> i & 1]
        atoms = _atoms(
            frame.filter(pl.col("split_label") == "development"), draw.features, DiscoveryConfig()
        )
        grid = {(a.feature, a.operator, float(a.value)) for a in atoms if a.operator in ("ge", "lt")}
        res: dict[str, Any] = {"seed": seed, "targets": {}, "pairs": {}}
        for d in tg.DESIGNS:
            mask = draw.masks[d.target_id]
            member = [i for i in dev_idx if mask >> i & 1]
            member_set = set(member)
            rest = [y[i] for i in dev_idx if i not in member_set]
            t = welch_t([y[i] for i in member], rest)
            eff = scoring.effective_rule(draw.space, d.conditions, scoring.CONSTANTS.nu)
            on_grid = all(
                (c.feature, c.operator, float(c.value)) in grid
                for c in d.conditions
                if c.operator in ("ge", "lt")
            )
            res["targets"][d.target_id] = {
                "n_aff": mask.bit_count(),
                "n_dev": len(member),
                "t_proxy": t,
                "on_grid": on_grid,
                "K_equals_T": len(eff.dropped) == 0,
                "dropped": [c.render() for c in eff.dropped],
                "scoreable": mask.bit_count() >= 50 and len(member) >= 40,
            }
            for name, lit in vc.TRAP_LITERALS.items():
                lm = draw.space.cond_mask(lit)
                if d.target_id and any(
                    c.feature == lit.feature and draw.space.cond_mask(c) == lm for c in d.conditions
                ):
                    res["targets"][d.target_id].setdefault("trap_j", {})[name] = scoring.jaccard(
                        mask, lm
                    )
        for a, b in combinations(tg.DESIGNS, 2):
            ma, mb = draw.masks[a.target_id], draw.masks[b.target_id]
            inter = (ma & mb).bit_count()
            small = min(ma.bit_count(), mb.bit_count())
            res["pairs"][f"{a.target_id}|{b.target_id}"] = {
                "inter": inter,
                "overlap_coeff": inter / small if small else 0.0,
                "nested": scoring.nested(ma, mb),
            }
        covered = 0
        for d in tg.DESIGNS:
            covered |= draw.masks[d.target_id]
        res["rows_with_any_target"] = covered.bit_count()
        return res


def main() -> None:
    lo, hi, out = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    static = static_checks()
    per_seed = [check_seed(s) for s in range(lo, hi + 1)]
    summary: dict[str, Any] = {"static": static, "seeds": [lo, hi], "targets": {}, "pairs": {}}
    for d in tg.DESIGNS:
        rows = [s["targets"][d.target_id] for s in per_seed]
        ts = [r["t_proxy"] for r in rows]
        summary["targets"][d.target_id] = {
            "rule": d.rule,
            "dose": d.dose_name,
            "class": d.declared_class,
            "n_aff_mean": round(statistics.fmean(r["n_aff"] for r in rows)),
            "n_aff_min": min(r["n_aff"] for r in rows),
            "n_dev_min": min(r["n_dev"] for r in rows),
            "t_mean": round(statistics.fmean(ts), 2),
            "t_min": round(min(ts), 2),
            "all_on_grid": all(r["on_grid"] for r in rows),
            "all_K_equals_T": all(r["K_equals_T"] for r in rows),
            "all_scoreable": all(r["scoreable"] for r in rows),
            "trap_j_max": {
                k: round(max(r.get("trap_j", {}).get(k, 0.0) for r in rows), 3)
                for k in vc.TRAP_LITERALS
                if any(k in r.get("trap_j", {}) for r in rows)
            },
        }
    for key in per_seed[0]["pairs"]:
        oc = [s["pairs"][key]["overlap_coeff"] for s in per_seed]
        summary["pairs"][key] = {
            "overlap_coeff_max": round(max(oc), 3),
            "any_nested": any(s["pairs"][key]["nested"] for s in per_seed),
        }
    summary["rows_with_any_target_mean"] = round(
        statistics.fmean(s["rows_with_any_target"] for s in per_seed)
    )
    out.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print("static errors:", static["errors"])
    print("rows with any target (mean):", summary["rows_with_any_target_mean"])
    for tid, e in summary["targets"].items():
        print(
            tid,
            e["class"][:4],
            e["dose"],
            f"naff {e['n_aff_mean']} (min {e['n_aff_min']}, dev>= {e['n_dev_min']})",
            f"t {e['t_mean']} (min {e['t_min']})",
            "grid" if e["all_on_grid"] else "OFFGRID",
            "K=T" if e["all_K_equals_T"] else "DEGENERATE",
            "" if e["all_scoreable"] else "UNSCOREABLE-some",
            e["trap_j_max"] or "",
            "|",
            e["rule"],
        )
    worst = sorted(summary["pairs"].items(), key=lambda kv: -kv[1]["overlap_coeff_max"])[:6]
    print("largest pairwise overlap coefficients:", [(k, v["overlap_coeff_max"]) for k, v in worst])
    print("nested pairs:", [k for k, v in summary["pairs"].items() if v["any_nested"]])


if __name__ == "__main__":
    main()
