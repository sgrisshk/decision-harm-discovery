"""TASK-107 Phase 2b oracle run on the COMPOSITE v2 generator (READ-ONLY; no engine search).

Per seed: build the composite draw (`generate_v2` with `synthetic_benchmark_v2_targets.DESIGNS`),
grade every target's TRUE rule (real `Condition`s) with the real, unmodified `run_validation`
(contract 1.3.0) at each multiplicity family (primary 60,000; sensitivity 36,791 and 26,213), grade
the engine-language projection rule at the primary family (L5 diagnostic), and record structural
checks (scoreability, K(T)=T at nu, on-grid, trap Jaccard). Only the atom-grid builder `_atoms` and
`build_projection` (as in Phase 1) touch engine-package code; no discovery search is run.

  seed   --seed S --out F [--families 60000 36791 26213]
  batch  --seeds A B --dir D [--procs N] [--families ...]
  rates  --dir D --out F
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_common as vc  # noqa: E402
from diagnose_oracle_decomposition import (  # noqa: E402
    _frame_mask,
    _rule_expr_local,
    build_projection,
)
from diagnose_task106_fn_autopsy import (  # noqa: E402
    DISCOVERY_METHOD_VERSION,
    LEVEL2_GATES,
    PREDICTIVE_OR_ABOVE,
    _gate_map,
    _render_rule,
    frozen_version_record,
)
from policy_analytics.outcomes import (  # noqa: E402
    outcome_definition_from_manifest,
    primary_outcome,
)
from policy_analytics.validation.apply import run_validation  # noqa: E402
from policy_analytics.discovery.engine import Condition, DiscoveryConfig, _atoms  # noqa: E402

import polars as pl  # noqa: E402

tg = vc.tg
scoring = vc.scoring
PRIMARY_FAMILY = 60000
SENSITIVITY_FAMILIES = (36791, 26213)
RHO_REP = 0.80


def _validate_rules(
    root: Path, rules: list[tuple[str, tuple[Condition, ...]]], family_size: int, label: str
) -> dict[str, Any]:
    """Same call sequence as `diagnose_task106_fn_autopsy._validate_rules` (real, unmodified
    `run_validation`), plus the detail string of every failed level-2 gate."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    validation_outcome, outcome_version = outcome_definition_from_manifest(manifest, root)
    outcome = primary_outcome()
    docs = [
        {
            "candidate_id": cid,
            "conditions": [
                {"feature": c.feature, "operator": c.operator, "value": c.value} for c in rule
            ],
            "outcome": outcome.outcome_id,
            "discovery_method": DISCOVERY_METHOD_VERSION,
            "description": f"POST-HOC DIAGNOSTIC (TASK-107 Phase 2b) {label}: {_render_rule(rule)}",
            "warnings": ["POST-HOC DIAGNOSTIC; not a discovered or selected candidate."],
        }
        for cid, rule in rules
    ]
    document = {
        "schema_version": "1.1.0",
        "run_id": f"task107-{label}",
        "status": "PERSISTED",
        "candidates": docs,
    }
    out: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmp:
        cpath = Path(tmp) / "candidates.json"
        cpath.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        mpath = Path(tmp) / "metrics.json"
        mpath.write_text(json.dumps({"evaluated_hypotheses": family_size}), encoding="utf-8")
        validations, summary = run_validation(
            dataset_root=root,
            candidates_path=cpath,
            outcome=validation_outcome,
            dataset_version=str(manifest["dataset_version"]),
            outcome_definition_version=outcome_version,
            analysis_run_id=f"task107-{label}",
            metrics_path=mpath,
        )
    if int(summary["family_size"]) != family_size:
        raise SystemExit("family size mismatch")
    for (cid, _), validation in zip(rules, validations, strict=True):
        report = validation.report
        gates = _gate_map(report.gate_results)
        failed = sorted(g for g, info in gates.items() if info["outcome"] == "fail")
        level2 = [g for g in failed if g in LEVEL2_GATES]
        out[cid] = {
            "verdict": validation.verdict,
            "evidence_level": str(report.evidence_level),
            "policy_readiness": str(report.policy_readiness),
            "failed_gates": failed,
            "level2_failed_gates": level2,
            "level2_failed_gate_details": {g: gates[g]["detail"] for g in level2},
            "g05_detail": next(
                (info["detail"] for g, info in gates.items() if g.startswith("G05")), None
            ),
            "exposed_records_development": report.exposed_records,
        }
    return out


def _conditions(design: Any) -> tuple[Condition, ...]:
    return tuple(Condition(c.feature, cast(Any, c.operator), c.value) for c in design.conditions)


def run_seed(seed: int, out: Path, families: tuple[int, ...]) -> None:
    frozen_version_record()
    with tempfile.TemporaryDirectory(prefix=f"v2o-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        frame = draw.frame
        timing = {n: str(m["classification"]) for n, m in draw.manifest["feature_timing"].items()}
        dev = frame.filter(pl.col("split_label") == "development")
        atoms = _atoms(dev, draw.features, DiscoveryConfig())
        cols = frozenset(frame.columns)
        grid = {(a.feature, a.operator, float(a.value)) for a in atoms if a.operator in ("ge", "lt")}
        info: dict[str, Any] = {}
        cond_rules: list[tuple[str, tuple[Condition, ...]]] = []
        proj_rules: list[tuple[str, tuple[Condition, ...]]] = []
        for d in tg.DESIGNS:
            mask = draw.masks[d.target_id]
            n_dev = (mask & draw.space.dev_mask).bit_count()
            eff = scoring.effective_rule(draw.space, d.conditions, scoring.CONSTANTS.nu)
            item: dict[str, Any] = {
                "n_affected": mask.bit_count(),
                "n_dev": n_dev,
                "scoreable": mask.bit_count() >= 50 and n_dev >= 40,
                "K_equals_T": not eff.dropped,
                "dropped_vacuous": [c.render() for c in eff.dropped],
                "on_grid": all(
                    (c.feature, c.operator, float(c.value)) in grid
                    for c in d.conditions
                    if c.operator in ("ge", "lt")
                ),
                "trap_j": {
                    name: scoring.jaccard(mask, draw.space.cond_mask(lit))
                    for name, lit in vc.TRAP_LITERALS.items()
                    if any(
                        c.feature == lit.feature
                        and draw.space.cond_mask(c) == draw.space.cond_mask(lit)
                        for c in d.conditions
                    )
                },
            }
            proj = build_projection(
                d.target_id, d.rule, atoms, draw.features, cols, timing, dev, DiscoveryConfig()
            )
            if not proj.over_depth and proj.atoms:
                exposed = _frame_mask(frame, _rule_expr_local(proj.atoms))
                item["projection_jaccard"] = scoring.jaccard(exposed, mask)
                item["projection_rule"] = " AND ".join(
                    f"{c.feature} {c.operator} {c.value}" for c in proj.atoms
                )
                if item["scoreable"]:
                    proj_rules.append((d.target_id, proj.atoms))
            else:
                item["projection_jaccard"] = None
            info[d.target_id] = item
            if item["scoreable"]:
                cond_rules.append((d.target_id, _conditions(d)))
        covered = 0
        for d in tg.DESIGNS:
            covered |= draw.masks[d.target_id]
        result: dict[str, Any] = {
            "seed": seed,
            "info": info,
            "rows_with_any_target": covered.bit_count(),
            "families": {},
        }
        for fam in families:
            fr: dict[str, Any] = {}
            fr["cond"] = _validate_rules(draw.root, cond_rules, fam, f"v2cond-{seed}-{fam}")
            if fam == PRIMARY_FAMILY and proj_rules:
                fr["proj"] = _validate_rules(draw.root, proj_rules, fam, f"v2proj-{seed}-{fam}")
            result["families"][str(fam)] = fr
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n")


def _fam_key(fam: int) -> str:
    return str(fam)


def rates(directory: Path, out: Path) -> dict[str, Any]:
    files = sorted(directory.glob("seed-*.json"))
    data = [json.loads(f.read_text()) for f in files]
    n_seeds = len(data)
    res: dict[str, Any] = {
        "n_seeds": n_seeds,
        "seeds": [d["seed"] for d in data],
        "primary_family": PRIMARY_FAMILY,
        "rows_with_any_target_mean": sum(d["rows_with_any_target"] for d in data) / max(n_seeds, 1),
        "targets": {},
    }
    for d in tg.DESIGNS:
        tid = d.target_id
        entry: dict[str, Any] = {
            "rule": d.rule,
            "dose": d.dose_name,
            "declared_class": d.declared_class,
            "n_conditions": len(d.conditions),
        }
        infos = [x["info"][tid] for x in data]
        entry["n_affected_min"] = min(i["n_affected"] for i in infos)
        entry["n_affected_median"] = sorted(i["n_affected"] for i in infos)[n_seeds // 2]
        entry["n_dev_min"] = min(i["n_dev"] for i in infos)
        entry["seeds_scoreable"] = sum(i["scoreable"] for i in infos)
        entry["all_K_equals_T"] = all(i["K_equals_T"] for i in infos)
        entry["all_on_grid"] = all(i["on_grid"] for i in infos)
        pj = [i["projection_jaccard"] for i in infos]
        entry["projection_jaccard_min"] = None if any(p is None for p in pj) else min(pj)
        entry["L5_projection_ge_rho_rep_all_seeds"] = all(p is not None and p >= RHO_REP for p in pj)
        entry["trap_j_max"] = {
            k: max(i["trap_j"].get(k, 0.0) for i in infos)
            for k in vc.TRAP_LITERALS
            if any(k in i["trap_j"] for i in infos)
        }
        for fam in [PRIMARY_FAMILY, *SENSITIVITY_FAMILIES]:
            for kind in ("cond", "proj"):
                rows = [
                    x["families"][_fam_key(fam)][kind].get(tid)
                    for x in data
                    if _fam_key(fam) in x["families"] and kind in x["families"][_fam_key(fam)]
                ]
                if not rows:
                    continue
                # an unscoreable seed (no validation row) is a failure of the oracle requirement
                passes = [
                    bool(r and r["evidence_level"] in PREDICTIVE_OR_ABOVE) for r in rows
                ]
                k = sum(passes)
                fails: dict[str, int] = {}
                for r in rows:
                    if r:
                        for g in r["level2_failed_gates"]:
                            fails[g] = fails.get(g, 0) + 1
                entry[f"{kind}@{fam}"] = {
                    "k": k,
                    "n": len(rows),
                    "wilson95": vc.wilson(k, len(rows)),
                    "cp_lower_one_sided_95": vc.clopper_pearson_lower(k, len(rows)),
                    "failed_seeds": [
                        data[i]["seed"] for i, ok in enumerate(passes) if not ok
                    ],
                    "gate_failures": dict(sorted(fails.items())),
                }
        res["targets"][tid] = entry
    out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    return res


def _print_rates(res: dict[str, Any]) -> None:
    for tid, e in res["targets"].items():
        p = e.get(f"cond@{PRIMARY_FAMILY}")
        if p is None:
            continue
        print(
            tid,
            e["declared_class"][:4],
            e["dose"],
            f"naff_med {e['n_affected_median']} min_dev {e['n_dev_min']}",
            f"primary {p['k']}/{p['n']} CPlb {p['cp_lower_one_sided_95']}",
            "K=T" if e["all_K_equals_T"] else "DEGEN",
            "grid" if e["all_on_grid"] else "OFFGRID",
            f"projJmin {e['projection_jaccard_min']}",
            p["gate_failures"] or "",
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--families", type=int, nargs="+", default=[PRIMARY_FAMILY, *SENSITIVITY_FAMILIES])
    b = sub.add_parser("batch")
    b.add_argument("--seeds", type=int, nargs=2, required=True)
    b.add_argument("--dir", type=Path, required=True)
    b.add_argument("--procs", type=int, default=10)
    b.add_argument("--families", type=int, nargs="+", default=[PRIMARY_FAMILY, *SENSITIVITY_FAMILIES])
    r = sub.add_parser("rates")
    r.add_argument("--dir", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "seed":
        run_seed(a.seed, a.out, tuple(a.families))
    elif a.cmd == "batch":
        seeds = range(a.seeds[0], a.seeds[1] + 1)
        todo = [
            (s_, a.dir / f"seed-{s_}.json", tuple(a.families))
            for s_ in seeds
            if not (a.dir / f"seed-{s_}.json").exists()
        ]
        with Pool(a.procs) as pool:
            pool.starmap(run_seed, todo)
    else:
        _print_rates(rates(a.dir, a.out))


if __name__ == "__main__":
    main()
