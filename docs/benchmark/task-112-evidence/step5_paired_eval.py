"""TASK-112 Step 5/6 -- paired evaluation on the freshly-authorized 4101-4130 reserve.

Runs the real, unmodified `discover_candidates()` from TWO engine states on identical v2
composite-generator draws, seeds 4101-4130:
  * "baseline": the frozen, pre-TASK-112 engine (`discovery-engine-v0.6.2`, sha256
    fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549) -- imported from a clean,
    read-only COPY of `packages/analytics/src` with only `discovery/engine.py` swapped back to the
    exact pre-TASK-112 content (obtained via `git show be7e829:...` -- `be7e829` is this task's own
    Step 1 commit, the last commit before any code change). This working tree's real `engine.py`
    is never touched or reverted to do this -- see
    `docs/benchmark/task-112-evidence/README-baseline-setup.md` for the exact method.
  * "modified": the real, Step-2-modified engine, imported normally from this repo checkout.

Methodology otherwise byte-identical to `docs/benchmark/task-109-evidence/run_blind_engine.py`
(same v2_common.build_draw call, same DiscoveryConfig(seed=seed) defaults, same
benchmark_v2_scoring.score() call, same FINAL_CORE/CORE_FAIL/D01 scope) -- reused by import where
possible, duplicated only for the parts that must differ (frozen-state verification per engine
variant, and running twice per seed with two different sys.path orderings).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parents[3]
BASELINE_PKG = Path(
    "<scratch>"
    "f82f6987-cd7b-429c-b576-4ad2d17b9dba/scratchpad/task112-baseline/packages/analytics/src"
)
SCHEMAS_SRC = REPO / "packages/schemas/src"
SCRIPTS = REPO / "scripts"
T107_EVIDENCE = REPO / "docs/benchmark/task-107-evidence"

SEEDS = list(range(4101, 4131))
FINAL_CORE: tuple[str, ...] = ("C02", "C04", "C06", "C07", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
CORE_FAIL: tuple[str, ...] = ("C01", "C10", "C13")
D01_ID = "D01"

BASELINE_ENGINE_SHA256 = "fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549"
BASELINE_METHOD_VERSION = "discovery-engine-v0.6.2"
MODIFIED_METHOD_VERSION = "discovery-engine-v0.6.3"


def _fresh_import(variant: str):
    """Reload every `policy_analytics.*` module from scratch with sys.path pointed at the right
    engine variant, so "baseline" and "modified" runs in the same process never share stale
    bytecode/module-cache state."""
    for name in list(sys.modules):
        if name.startswith("policy_analytics") or name in ("v2_common",):
            del sys.modules[name]
    analytics_src = str(BASELINE_PKG) if variant == "baseline" else str(REPO / "packages/analytics/src")
    sys.path[:] = [p for p in sys.path if "policy_analytics" not in p and "analytics/src" not in p]
    sys.path[:0] = [analytics_src, str(SCHEMAS_SRC), str(SCRIPTS), str(T107_EVIDENCE)]
    engine = importlib.import_module("policy_analytics.discovery.engine")
    engine_path = (
        BASELINE_PKG / "policy_analytics/discovery/engine.py"
        if variant == "baseline"
        else REPO / "packages/analytics/src/policy_analytics/discovery/engine.py"
    )
    digest = hashlib.sha256(engine_path.read_bytes()).hexdigest()
    expected_version = BASELINE_METHOD_VERSION if variant == "baseline" else MODIFIED_METHOD_VERSION
    expected_sha = BASELINE_ENGINE_SHA256 if variant == "baseline" else None
    if engine.DISCOVERY_METHOD_VERSION != expected_version:
        raise SystemExit(
            f"{variant}: methodology_version mismatch: got {engine.DISCOVERY_METHOD_VERSION!r}, "
            f"expected {expected_version!r}"
        )
    if expected_sha is not None and digest != expected_sha:
        raise SystemExit(f"{variant}: engine.py sha256 mismatch: got {digest}, expected {expected_sha}")
    vc = importlib.import_module("v2_common")
    tg = importlib.import_module("policy_analytics.synthetic_benchmark_v2_targets")
    outcomes_mod = importlib.import_module("policy_analytics.outcomes")
    scoring = vc.scoring
    return {
        "engine": engine,
        "vc": vc,
        "tg": tg,
        "primary_outcome": outcomes_mod.primary_outcome,
        "scoring": scoring,
        "engine_sha256": digest,
    }


def targets_for_draw(mods, draw) -> list[Any]:
    tg = mods["tg"]
    scoring = mods["scoring"]
    design_index = tg.design_index()
    out: list[Any] = []
    for tid in (*FINAL_CORE, *CORE_FAIL, D01_ID):
        d = design_index[tid]
        out.append(
            scoring.Target(
                target_id=tid,
                stratum="declared_overlap" if tid == D01_ID else "core",
                conditions=d.conditions,
                affected=draw.masks[tid],
                canonical_in_language=d.conditions,
                assessed=tid not in CORE_FAIL,
            )
        )
    return out


def traps_list(mods) -> list[Any]:
    vc = mods["vc"]
    scoring = mods["scoring"]
    return [scoring.Trap(name, lit) for name, lit in vc.TRAP_LITERALS.items()]


def run_seed(variant: str, seed: int, out: Path) -> None:
    mods = _fresh_import(variant)
    engine = mods["engine"]
    vc = mods["vc"]
    tg = mods["tg"]
    scoring = mods["scoring"]
    primary_outcome = mods["primary_outcome"]

    with tempfile.TemporaryDirectory(prefix=f"task112-{variant}-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        outcome = primary_outcome()
        config = engine.DiscoveryConfig(seed=seed)
        print(f"[{variant}] seed {seed}: running discover_candidates()", flush=True)
        doc = engine.discover_candidates(draw.frame, draw.features, outcome, config)
        candidate_count = int(doc["candidate_count"])
        raw_candidates = cast(list[dict[str, Any]], doc["candidates"])

        # Validation step: reused via run_validation, which does not depend on which engine
        # variant produced the candidates -- always imported from THIS repo checkout (validation/
        # contract code is explicitly out of scope and untouched by TASK-112 in either variant).
        validation_mod = importlib.import_module("policy_analytics.validation.apply")
        diagnose_mod = importlib.import_module("diagnose_validation_power")
        outcome_definition_from_manifest = mods["primary_outcome"].__self__ if False else None
        from policy_analytics.outcomes import outcome_definition_from_manifest as _odfm

        document = {**doc, "status": "PERSISTED", "run_id": f"task112-{variant}-seed{seed}"}
        cpath = Path(tmp) / "candidates.json"
        cpath.write_text(json.dumps(document, sort_keys=True, default=str), encoding="utf-8")

        validation_outcome, outcome_version = _odfm(draw.manifest, draw.root)
        print(f"[{variant}] seed {seed}: validating {candidate_count} candidates", flush=True)
        validations, summary = validation_mod.run_validation(
            dataset_root=draw.root,
            candidates_path=cpath,
            outcome=validation_outcome,
            dataset_version=str(draw.manifest["dataset_version"]),
            outcome_definition_version=outcome_version,
            analysis_run_id=f"task112-{variant}-seed{seed}",
        )
        if int(summary["family_size"]) != int(cast(dict[str, Any], doc["search"])["evaluated_hypotheses"]):
            raise SystemExit(f"seed {seed} ({variant}): family size mismatch")

        cand_val: dict[str, dict[str, Any]] = {}
        for raw, validation in zip(raw_candidates, validations, strict=True):
            cid = str(raw["candidate_id"])
            report = validation.report
            gates = diagnose_mod._gate_map(report.gate_results)
            failed = sorted(g for g, info in gates.items() if info["outcome"] == "fail")
            cand_val[cid] = {
                "verdict": validation.verdict,
                "evidence_level": (
                    None if report.evidence_level is None else str(report.evidence_level)
                ),
                "policy_readiness": str(report.policy_readiness),
                "failed_gates": failed,
            }

        candidates_for_scoring: list[Any] = []
        for raw in raw_candidates:
            cid = str(raw["candidate_id"])
            conds = tuple(
                scoring.CondSpec(str(c["feature"]), str(c["operator"]), c["value"])
                for c in cast(list[dict[str, Any]], raw["conditions"])
            )
            val = cand_val[cid]
            candidates_for_scoring.append(
                scoring.Candidate(
                    candidate_id=cid,
                    conditions=conds,
                    evidence_level=val["evidence_level"],
                    policy_readiness=val["policy_readiness"],
                )
            )
        print(f"[{variant}] seed {seed}: scoring", flush=True)
        score_result = scoring.score(
            draw.space, targets_for_draw(mods, draw), traps_list(mods), candidates_for_scoring
        )
        result: dict[str, Any] = {
            "variant": variant,
            "seed": seed,
            "engine_sha256": mods["engine_sha256"],
            "methodology_version": doc["methodology_version"],
            "dataset_identity_sha256": draw.manifest["dataset_identity_sha256"],
            "engine": {
                "candidate_count": candidate_count,
                "evaluated_hypotheses": int(cast(dict[str, Any], doc["search"])["evaluated_hypotheses"]),
                "candidates": raw_candidates,
            },
            "validation": cand_val,
            "score": score_result,
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"[{variant}] seed {seed}: wrote {out}", flush=True)


def _tkey(theta: float) -> str:
    return f"{theta:.2f}"


def compute_rates(directory: Path, variant: str) -> dict[str, Any]:
    files = sorted(directory.glob(f"{variant}-seed-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
    data = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    theta_key = None
    per_seed = []
    per_target: dict[str, dict[str, int]] = {tid: {"coverage": 0, "specific": 0, "exact": 0} for tid in FINAL_CORE}
    any_trap_promoted_count = 0
    for d in data:
        core = d["score"]["strata"].get("core", {})
        if theta_key is None:
            # discover the theta key from the data itself (CONSTANTS.theta_j is fixed, 0.75 here)
            spec = core.get("specific_targets", {})
            theta_key = next(iter(spec), None)
        cov = set(core.get("coverage_targets", []))
        spec_set = set(core.get("specific_targets", {}).get(theta_key, [])) if theta_key else set()
        exact_set = set(core.get("exact_targets", []))
        for tid in FINAL_CORE:
            if tid in cov:
                per_target[tid]["coverage"] += 1
            if tid in spec_set:
                per_target[tid]["specific"] += 1
            if tid in exact_set:
                per_target[tid]["exact"] += 1
        if d["score"]["safety"]["any_trap_promoted"]:
            any_trap_promoted_count += 1
        per_seed.append(
            {
                "seed": d["seed"],
                "candidate_count": d["engine"]["candidate_count"],
                "coverage": sorted(cov),
                "specific": sorted(spec_set),
                "exact": sorted(exact_set),
                "any_trap_promoted": d["score"]["safety"]["any_trap_promoted"],
            }
        )
    return {
        "variant": variant,
        "n_seeds": len(data),
        "per_target_k_of_30": per_target,
        "per_seed": per_seed,
        "n_seeds_any_trap_promoted": any_trap_promoted_count,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--variant", choices=["baseline", "modified"], required=True)
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--dir", type=Path, required=True)
    b = sub.add_parser("batch")
    b.add_argument("--variant", choices=["baseline", "modified"], required=True)
    b.add_argument("--seeds", type=int, nargs=2, required=True)
    b.add_argument("--dir", type=Path, required=True)
    r = sub.add_parser("rates")
    r.add_argument("--variant", choices=["baseline", "modified"], required=True)
    r.add_argument("--dir", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "seed":
        run_seed(a.variant, a.seed, a.dir / f"{a.variant}-seed-{a.seed}.json")
    elif a.cmd == "batch":
        for seed_ in range(a.seeds[0], a.seeds[1] + 1):
            out_path = a.dir / f"{a.variant}-seed-{seed_}.json"
            if out_path.exists():
                continue
            run_seed(a.variant, seed_, out_path)
    else:
        rates = compute_rates(a.dir, a.variant)
        a.out.write_text(json.dumps(rates, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
