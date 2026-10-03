"""TASK-109: first blind frozen-engine run on frozen benchmark v2 (measurement only, `ADR-110`).

Per seed (composite v2 draw, ALL 20 `TargetDesign` records dosed together, exactly as `TASK-107`
built it): run the real, unmodified `discover_candidates()` (frozen engine
`discovery-engine-v0.6.2`, default `DiscoveryConfig` except `seed`, which the engine's own search
never reads), validate the real candidates with the real, unmodified `run_validation()` (contract
1.3.0) using the family size the engine itself reports, and score with the real, unmodified
`benchmark_v2_scoring.score()` against the 11 final Core targets, the 3 permanently-excluded
Core-FAIL targets (`assessed=False`, never credited, per `ADR-108` Decision 3's existing
mechanism), `D01`, and traps `T01-T05`. See `docs/benchmark/task-109-preregistration.md` for the
full, binding pre-registration (seeds, schema, scope) committed before this script was ever run.

No engine/benchmark/scorer/threshold code is imported here except by reference (reused
unmodified); this file performs I/O and aggregation only.

  seed   --seed S --out F
  batch  --seeds A B --dir D [--procs N]
  rates  --dir D --out F
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPOSITORY / "packages/analytics/src"),
    str(REPOSITORY / "packages/schemas/src"),
    str(REPOSITORY / "scripts"),
    str(REPOSITORY / "docs/benchmark/task-107-evidence"),
]

import v2_common as vc  # noqa: E402
from diagnose_validation_power import _gate_map  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    DISCOVERY_METHOD_VERSION,
    DiscoveryConfig,
    discover_candidates,
)
from policy_analytics.outcomes import outcome_definition_from_manifest, primary_outcome  # noqa: E402
from policy_analytics.validation.apply import run_validation  # noqa: E402
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS, GateId  # noqa: E402

tg = vc.tg
scoring = vc.scoring

# ---------------------------------------------------------------------- frozen-state verification
FROZEN_METHOD_VERSION = "discovery-engine-v0.6.2"
FROZEN_CONTRACT = "1.3.0"
FROZEN_FILES: dict[str, str] = {
    "packages/analytics/src/policy_analytics/discovery/engine.py": (
        "fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549"
    ),
    "packages/analytics/src/policy_analytics/validation/contract.py": (
        "a55fdc94c7e520cc4e287c6627d345e5a2335bfc1bd684db584218790b7403cd"
    ),
    "packages/analytics/src/policy_analytics/benchmark_v2_scoring.py": (
        "0878811a737ad3608f2ee14568f10a67fc92fd052d866c261d44c9650a8ada1b"
    ),
    "packages/analytics/src/policy_analytics/synthetic_benchmark_v2.py": (
        "2d6231001ec5ba4e526263e2ad7e67b84d651408be2183fcc024b927fc1627da"
    ),
    "packages/analytics/src/policy_analytics/synthetic_benchmark_v2_targets.py": (
        "4a9e75a8d27284dbaa20ba0467d43871d0df20db6e16268ca01af208eb9d2059"
    ),
}


def verify_frozen_state() -> dict[str, Any]:
    """Re-derive every frozen-file hash and compare to the freeze manifest's recorded values
    (`docs/benchmark/task-107-freeze-manifest.md`). Raises `SystemExit` on any mismatch -- this
    task's step 1/step 7 requirement, never softened to a warning."""
    actual: dict[str, str] = {}
    for rel, expected in FROZEN_FILES.items():
        digest = hashlib.sha256((REPOSITORY / rel).read_bytes()).hexdigest()
        actual[rel] = digest
        if digest != expected:
            raise SystemExit(f"FROZEN-STATE MISMATCH in {rel}: expected {expected}, got {digest}")
    if DISCOVERY_METHOD_VERSION != FROZEN_METHOD_VERSION:
        raise SystemExit(f"engine method version drifted: {DISCOVERY_METHOD_VERSION!r}")
    if DEFAULT_THRESHOLDS.version != FROZEN_CONTRACT:
        raise SystemExit(f"validation contract version drifted: {DEFAULT_THRESHOLDS.version!r}")
    g17_present = any("G17" in gate.value for gate in GateId)
    if g17_present:
        raise SystemExit("G17 present: frozen-state violated")
    return {
        "hashes": actual,
        "discovery_method_version": DISCOVERY_METHOD_VERSION,
        "validation_contract_version": DEFAULT_THRESHOLDS.version,
        "g17_present": g17_present,
    }


# --------------------------------------------------------------------------------- target scope --
#: `TASK-109` / `ADR-110` binding scope: 11 Core + D01. The 3 Core-FAIL targets are included only
#: so they appear (as `unscoreable`, `assessed=False`) for transparency; they are never credited
#: and never grant a trap exemption (`ADR-108` Decision 3 -- an existing mechanism, not a new one).
#: Challenge-only designs and D02 are out of scope and are not constructed as targets at all
#: (disclosed in `docs/benchmark/task-109-preregistration.md` section 3).
FINAL_CORE: tuple[str, ...] = ("C02", "C04", "C06", "C07", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
CORE_FAIL: tuple[str, ...] = ("C01", "C10", "C13")
D01_ID = "D01"


def targets_for_draw(draw: vc.Draw) -> list[Any]:
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


def traps_list() -> list[Any]:
    return [scoring.Trap(name, lit) for name, lit in vc.TRAP_LITERALS.items()]


# ------------------------------------------------------------------------------------- one seed --
def run_seed(seed: int, out: Path) -> None:
    frozen = verify_frozen_state()
    with tempfile.TemporaryDirectory(prefix=f"task109-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        outcome = primary_outcome()
        config = DiscoveryConfig(seed=seed)
        print(f"seed {seed}: running real discover_candidates()", flush=True)
        doc = discover_candidates(draw.frame, draw.features, outcome, config)
        family_size = int(cast(dict[str, Any], doc["search"])["evaluated_hypotheses"])
        candidate_count = int(doc["candidate_count"])
        raw_candidates = cast(list[dict[str, Any]], doc["candidates"])

        document = {**doc, "status": "PERSISTED", "run_id": f"task109-seed{seed}"}
        cpath = Path(tmp) / "candidates.json"
        cpath.write_text(json.dumps(document, sort_keys=True, default=str), encoding="utf-8")

        validation_outcome, outcome_version = outcome_definition_from_manifest(
            draw.manifest, draw.root
        )
        print(f"seed {seed}: validating {candidate_count} real engine candidates", flush=True)
        validations, summary = run_validation(
            dataset_root=draw.root,
            candidates_path=cpath,
            outcome=validation_outcome,
            dataset_version=str(draw.manifest["dataset_version"]),
            outcome_definition_version=outcome_version,
            analysis_run_id=f"task109-seed{seed}",
        )
        if int(summary["family_size"]) != family_size:
            raise SystemExit(
                f"seed {seed}: family size mismatch -- engine reported {family_size}, "
                f"run_validation used {summary['family_size']}"
            )

        cand_val: dict[str, dict[str, Any]] = {}
        for raw, validation in zip(raw_candidates, validations, strict=True):
            cid = str(raw["candidate_id"])
            report = validation.report
            gates = _gate_map(report.gate_results)
            failed = sorted(g for g, info in gates.items() if info["outcome"] == "fail")
            cand_val[cid] = {
                "verdict": validation.verdict,
                "evidence_level": (
                    None if report.evidence_level is None else str(report.evidence_level)
                ),
                "policy_readiness": str(report.policy_readiness),
                "failed_gates": failed,
                "exposed_records_development": report.exposed_records,
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
        print(f"seed {seed}: scoring with benchmark_v2_scoring.score()", flush=True)
        score_result = scoring.score(
            draw.space, targets_for_draw(draw), traps_list(), candidates_for_scoring
        )
        result: dict[str, Any] = {
            "seed": seed,
            "frozen_state": frozen,
            "dataset_identity_sha256": draw.manifest["dataset_identity_sha256"],
            "dataset_version": draw.manifest["dataset_version"],
            "engine": {
                "candidate_count": candidate_count,
                "evaluated_hypotheses": family_size,
                "methodology_version": doc["methodology_version"],
                "search_config": doc["search"],
                "candidates": raw_candidates,
            },
            "validation": cand_val,
            "score": score_result,
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"seed {seed}: wrote {out}", flush=True)


# ------------------------------------------------------------------------------------ aggregation
def _tkey(theta: float) -> str:
    return f"{theta:.2f}"


def _stratum_block(data: list[dict[str, Any]], stratum: str, target_ids: tuple[str, ...]) -> dict[str, Any]:
    theta_key = _tkey(scoring.CONSTANTS.theta_j)
    n_seeds = len(data)
    per_target: dict[str, Any] = {}
    for tid in target_ids:
        cov_k = sum(
            1
            for d in data
            if tid in d["score"]["strata"].get(stratum, {}).get("coverage_targets", [])
        )
        spec_k = sum(
            1
            for d in data
            if tid
            in d["score"]["strata"].get(stratum, {}).get("specific_targets", {}).get(theta_key, [])
        )
        exact_k = sum(
            1 for d in data if tid in d["score"]["strata"].get(stratum, {}).get("exact_targets", [])
        )
        per_target[tid] = {
            "coverage_k_of_n": cov_k,
            "specific_k_of_n": spec_k,
            "exact_k_of_n": exact_k,
            "n_seeds": n_seeds,
        }
    n = len(target_ids)
    coverage_any = sum(1 for tid in target_ids if per_target[tid]["coverage_k_of_n"] >= 1)
    specific_any = sum(1 for tid in target_ids if per_target[tid]["specific_k_of_n"] >= 1)
    exact_any = sum(1 for tid in target_ids if per_target[tid]["exact_k_of_n"] >= 1)
    return {
        "target_ids": list(target_ids),
        "per_target_k_of_30": per_target,
        "coverage_recall_any_of_30": f"{coverage_any}/{n}",
        "specific_recall_any_of_30": f"{specific_any}/{n}",
        "exact_recall_any_of_30": f"{exact_any}/{n}",
    }


def compute_rates(directory: Path) -> dict[str, Any]:
    files = sorted(directory.glob("seed-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    data = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    per_seed = []
    for d in data:
        core = d["score"]["strata"].get("core", {})
        declared = d["score"]["strata"].get("declared_overlap", {})
        theta_key = _tkey(scoring.CONSTANTS.theta_j)
        per_seed.append(
            {
                "seed": d["seed"],
                "generated_candidate_count": d["engine"]["candidate_count"],
                "evaluated_hypotheses": d["engine"]["evaluated_hypotheses"],
                "core_coverage_targets": core.get("coverage_targets", []),
                "core_specific_targets": core.get("specific_targets", {}).get(theta_key, []),
                "core_exact_targets": core.get("exact_targets", []),
                "d01_coverage": declared.get("coverage_targets", []),
                "d01_specific": declared.get("specific_targets", {}).get(theta_key, []),
                "d01_exact": declared.get("exact_targets", []),
                "any_trap_promoted": d["score"]["safety"]["any_trap_promoted"],
            }
        )
    return {
        "n_seeds": len(data),
        "seeds": [d["seed"] for d in data],
        "theta_j": scoring.CONSTANTS.theta_j,
        "theta_p": scoring.CONSTANTS.theta_p,
        "core": _stratum_block(data, "core", FINAL_CORE),
        "declared_overlap": _stratum_block(data, "declared_overlap", (D01_ID,)),
        "per_seed": per_seed,
    }


# ------------------------------------------------------------------------------------------- CLI --
def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("batch")
    b.add_argument("--seeds", type=int, nargs=2, required=True)
    b.add_argument("--dir", type=Path, required=True)
    b.add_argument("--procs", type=int, default=1)
    r = sub.add_parser("rates")
    r.add_argument("--dir", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "seed":
        run_seed(a.seed, a.out)
    elif a.cmd == "batch":
        seeds = range(a.seeds[0], a.seeds[1] + 1)
        todo = [
            (s_, a.dir / f"seed-{s_}.json")
            for s_ in seeds
            if not (a.dir / f"seed-{s_}.json").exists()
        ]
        if a.procs > 1:
            with Pool(a.procs) as pool:
                pool.starmap(run_seed, todo)
        else:
            for seed_, out_path in todo:
                run_seed(seed_, out_path)
    else:
        rates = compute_rates(a.dir)
        a.out.write_text(json.dumps(rates, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
