"""TASK-115 Step 3 -- run the modified (refinement-augmented, discovery-engine-v0.6.4) engine on
the development seeds `4001-4030`/`4101-4130` (both already development-only, freely usable per
`ADR-116` Decision 3). Baseline results for these exact seeds already exist, committed, from prior
tasks (`docs/benchmark/task-109-evidence/engine-raw/seed-*.json` for 4001-4030,
`docs/benchmark/task-112-evidence/step5-paired-4101-4130/baseline-seed-*.json` for 4101-4130) --
not re-run here.

Methodology mirrors `docs/benchmark/task-112-evidence/step5_paired_eval.py`'s own `run_seed`
(same `v2_common.build_draw`, same `DiscoveryConfig(seed=seed)` defaults, same
`benchmark_v2_scoring.score()` call, same `FINAL_CORE`/`CORE_FAIL`/`D01` scope), with one addition:
`discover_candidates()` is called with `refine_with_validation` wired to the real, frozen
`run_validation` (contract 1.3.0) via `v2_common115.make_refinement_validator` -- the one
permitted mechanism, nothing else. The final candidates list (base shortlist + any refinement
additions) is validated and scored exactly as every prior task's own pipeline already does.
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
ANALYTICS_SRC = REPO / "packages/analytics/src"
SCHEMAS_SRC = REPO / "packages/schemas/src"
SCRIPTS = REPO / "scripts"
T107_EVIDENCE = REPO / "docs/benchmark/task-107-evidence"
THIS_DIR = Path(__file__).resolve().parent

sys.path[:0] = [str(ANALYTICS_SRC), str(SCHEMAS_SRC), str(SCRIPTS), str(T107_EVIDENCE), str(THIS_DIR)]

EXPECTED_METHOD_VERSION = "discovery-engine-v0.6.4"

import v2_common as vc  # noqa: E402
import v2_common115 as vc115  # noqa: E402
import policy_analytics.discovery.engine as engine  # noqa: E402
import policy_analytics.synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics import benchmark_v2_scoring as scoring  # noqa: E402
from policy_analytics.outcomes import outcome_definition_from_manifest, primary_outcome  # noqa: E402

if engine.DISCOVERY_METHOD_VERSION != EXPECTED_METHOD_VERSION:
    raise SystemExit(
        f"unexpected engine version: {engine.DISCOVERY_METHOD_VERSION!r}, expected "
        f"{EXPECTED_METHOD_VERSION!r}"
    )

FINAL_CORE: tuple[str, ...] = ("C02", "C04", "C06", "C07", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
CORE_FAIL: tuple[str, ...] = ("C01", "C10", "C13")
D01_ID = "D01"
OUT_DIR = THIS_DIR / "step3-dev-seeds"


def targets_for_draw(draw: Any) -> list[Any]:
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


def run_seed(seed: int, out: Path) -> None:
    mods = {"engine": engine}
    with tempfile.TemporaryDirectory(prefix=f"task115-dev-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        outcome = primary_outcome()
        config = engine.DiscoveryConfig(seed=seed)
        validation_outcome, outcome_version = outcome_definition_from_manifest(draw.manifest, draw.root)
        validator = vc115.make_refinement_validator(
            mods, draw, validation_outcome, outcome_version, f"task115-dev-seed{seed}"
        )
        print(f"[modified] seed {seed}: running discover_candidates() with refinement", flush=True)
        doc = engine.discover_candidates(
            draw.frame, draw.features, outcome, config, refine_with_validation=validator
        )
        candidate_count = int(doc["candidate_count"])
        raw_candidates = cast(list[dict[str, Any]], doc["candidates"])
        refinement_meta = doc["refinement"]

        validation_mod = importlib.import_module("policy_analytics.validation.apply")
        diagnose_mod = importlib.import_module("diagnose_validation_power")

        document = {**doc, "status": "PERSISTED", "run_id": f"task115-dev-seed{seed}"}
        cpath = Path(tmp) / "candidates.json"
        cpath.write_text(json.dumps(document, sort_keys=True, default=str), encoding="utf-8")

        print(f"[modified] seed {seed}: validating {candidate_count} candidates", flush=True)
        validations, summary = validation_mod.run_validation(
            dataset_root=draw.root,
            candidates_path=cpath,
            outcome=validation_outcome,
            dataset_version=str(draw.manifest["dataset_version"]),
            outcome_definition_version=outcome_version,
            analysis_run_id=f"task115-dev-seed{seed}",
        )
        if int(summary["family_size"]) != int(cast(dict[str, Any], doc["search"])["evaluated_hypotheses"]):
            raise SystemExit(f"seed {seed}: family size mismatch")

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
        print(f"[modified] seed {seed}: scoring", flush=True)
        score_result = scoring.score(draw.space, targets_for_draw(draw), traps_list(), candidates_for_scoring)
        result: dict[str, Any] = {
            "variant": "modified",
            "seed": seed,
            "engine_sha256": hashlib.sha256(
                (ANALYTICS_SRC / "policy_analytics/discovery/engine.py").read_bytes()
            ).hexdigest(),
            "methodology_version": doc["methodology_version"],
            "dataset_identity_sha256": draw.manifest["dataset_identity_sha256"],
            "engine": {
                "candidate_count": candidate_count,
                "evaluated_hypotheses": int(cast(dict[str, Any], doc["search"])["evaluated_hypotheses"]),
                "candidates": raw_candidates,
            },
            "refinement": refinement_meta,
            "validation": cand_val,
            "score": score_result,
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"[modified] seed {seed}: wrote {out}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for seed in args.seeds:
        out_path = OUT_DIR / f"modified-seed-{seed}.json"
        if out_path.exists():
            print(f"seed {seed}: already built, skipping")
            continue
        run_seed(seed, out_path)


if __name__ == "__main__":
    main()
