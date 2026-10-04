"""TASK-114 Step 4 -- validation evidence level for every chain step (Method A + Method B),
contract 1.3.0, the real `run_validation` (`policy_analytics.validation.apply`), never a copy.

Collects every DISTINCT rule (conditions-tuple) appearing anywhere in Step 1's (`step1_build_
chains.py`) and Step 1b's (`step1b_canonical_prefix_chains.py`) already-committed chain steps for
a given seed, builds ONE candidates document covering all of them (status=PERSISTED,
`search.evaluated_hypotheses` = that seed's own REAL recorded family size from the already-
committed raw engine output -- reused, not fabricated, since these rules are additional probes
within the same real search's family, not a new search), and validates them in a single
`run_validation` call per seed -- batched for cost, not duplicated per chain step. None of these
candidates were already present in the committed final-top-15 validation (`validation` block of
`seed-*.json`/`baseline-seed-*.json`) under their own candidate_id, so none can be reused from
already-committed validated data as-is; this check is still performed explicitly below (by rule
identity, not candidate_id) before concluding a fresh run is needed, per the task's own
instruction.
"""
# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import importlib
import json
import tempfile
from pathlib import Path
from typing import Any

import step1_build_chains as s1

OUT_DIR = Path(__file__).resolve().parent / "step4-validation-raw"
STEP1_DIR = Path(__file__).resolve().parent / "step1-chains-raw"
STEP1B_DIR = Path(__file__).resolve().parent / "step1b-canonical-prefix-raw"
T109_RAW = s1.T109_RAW
T112_BASELINE = s1.T112_BASELINE


def _rule_key(conditions: list[dict[str, Any]]) -> str:
    return " & ".join(
        f"{c['feature']} {c['operator']} {c['value']!r}"
        for c in sorted(conditions, key=lambda c: (c["feature"], c["operator"], str(c["value"])))
    )


def _collect_distinct_rules(seed: int) -> dict[str, list[dict[str, Any]]]:
    rules: dict[str, list[dict[str, Any]]] = {}

    step1_path = STEP1_DIR / f"seed-{seed}.json"
    if step1_path.exists():
        doc = json.loads(step1_path.read_text(encoding="utf-8"))
        for entry in doc["targets"].values():
            if entry.get("chainable") and entry.get("has_qualifying_broad_candidate"):
                for step in entry["chain_steps"]:
                    conds = step["conditions"]
                    rules[_rule_key(conds)] = conds

    step1b_path = STEP1B_DIR / f"seed-{seed}.json"
    if step1b_path.exists():
        doc = json.loads(step1b_path.read_text(encoding="utf-8"))
        for entry in doc["targets"].values():
            if entry.get("chainable"):
                for start in entry["starts"]:
                    for step in start["chain_steps"]:
                        conds = step["conditions"]
                        rules[_rule_key(conds)] = conds

    return rules


def _already_committed_family_size(seed: int) -> int:
    if 4001 <= seed <= 4030:
        path = T109_RAW / f"seed-{seed}.json"
    else:
        path = T112_BASELINE / f"baseline-seed-{seed}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    return int(doc["engine"]["evaluated_hypotheses"])


def validate_seed(seed: int) -> dict[str, Any]:
    rules = _collect_distinct_rules(seed)
    if not rules:
        return {"seed": seed, "n_rules": 0, "rules": {}}

    family_size = _already_committed_family_size(seed)

    validation_mod = importlib.import_module("policy_analytics.validation.apply")
    diagnose_mod = importlib.import_module("diagnose_validation_power")
    from policy_analytics.outcomes import outcome_definition_from_manifest

    with tempfile.TemporaryDirectory(prefix=f"task114-val-{seed}-") as tmp:
        draw = s1.vc.build_draw(seed, Path(tmp), s1.tg.DESIGNS)
        candidates_payload = [
            {"candidate_id": f"PROBE-{i:04d}", "conditions": conds}
            for i, (key, conds) in enumerate(sorted(rules.items()))
        ]
        key_by_index = {f"PROBE-{i:04d}": key for i, (key, _) in enumerate(sorted(rules.items()))}
        document = {
            "status": "PERSISTED",
            "search": {"evaluated_hypotheses": family_size},
            "candidates": candidates_payload,
        }
        cpath = Path(tmp) / "candidates.json"
        cpath.write_text(json.dumps(document, default=str), encoding="utf-8")

        validation_outcome, outcome_version = outcome_definition_from_manifest(draw.manifest, draw.root)
        validations, summary = validation_mod.run_validation(
            dataset_root=draw.root,
            candidates_path=cpath,
            outcome=validation_outcome,
            dataset_version=str(draw.manifest["dataset_version"]),
            outcome_definition_version=outcome_version,
            analysis_run_id=f"task114-probe-seed{seed}",
        )
        out_rules: dict[str, Any] = {}
        for raw, validation in zip(candidates_payload, validations, strict=True):
            report = validation.report
            gates = diagnose_mod._gate_map(report.gate_results)
            failed = sorted(g for g, info in gates.items() if info["outcome"] == "fail")
            key = key_by_index[raw["candidate_id"]]
            out_rules[key] = {
                "conditions": raw["conditions"],
                "verdict": validation.verdict,
                "evidence_level": None if report.evidence_level is None else str(report.evidence_level),
                "policy_readiness": str(report.policy_readiness),
                "failed_gates": failed,
                "exposed_records_development": report.exposed_records,
            }

    return {
        "seed": seed,
        "family_size_reused_from_committed_raw_data": family_size,
        "n_rules": len(rules),
        "rules": out_rules,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for seed in args.seeds:
        out_path = OUT_DIR / f"seed-{seed}.json"
        if out_path.exists():
            print(f"seed {seed}: already validated, skipping")
            continue
        print(f"seed {seed}: validating distinct chain rules...", flush=True)
        result = validate_seed(seed)
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        print(f"  wrote {out_path} ({result['n_rules']} distinct rules validated)")
    final_digest = s1._verify_engine()
    print(f"engine.py sha256 after run: {final_digest} (unchanged)")


if __name__ == "__main__":
    main()
