"""TASK-116 Step 2 -- real, frozen `run_validation` (contract 1.3.0) over the candidates Step 1's
pool needs checked, batched once per seed exactly as `TASK-114`/`TASK-115`'s own probe-validation
precedent (`docs/benchmark/task-114-evidence/step4_validate_chains.py`,
`docs/benchmark/task-115-evidence/v2_common115.py`): these rules are additional probes within the
same real search family, not a new search, so each seed's own already-recorded
`evaluated_hypotheses` is reused as the family size, never fabricated.

Per seed, validates the UNION of:
  * the top-60 admissible pool items by `_development_score` (covers the K=15/2K=30/4K=60
    capacity-sensitivity curve, ADR-117 Decision 3 item 3) -- every one of these is validated for
    real regardless of target, so the exact real batching semantics can be replayed later without
    guessing pass/fail;
  * each target's own identified "productive descendant" (Step 1's `per_target_summary`), if its
    rank lies beyond 60 (the decisive counterfactual-unlimited-cap test, ADR-117 Decision 3 item 1 --
    this candidate specifically must be validated for real, not simulated);
  * any C07 guard-literal hit beyond rank 60 (ADR-117 Decision 5).

This keeps real validation calls bounded (~60-70/seed) instead of the full ~700-1000-item pool
(previously measured at ~0.7-0.9s/candidate in `TASK-115`'s own disclosed performance note --
validating every admissible descendant in every seed would be impractical).
"""
# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
ANALYTICS_SRC = REPO / "packages/analytics/src"
SCHEMAS_SRC = REPO / "packages/schemas/src"
SCRIPTS = REPO / "scripts"
T107_EVIDENCE = REPO / "docs/benchmark/task-107-evidence"
HERE = Path(__file__).resolve().parent
POOL_DIR = HERE / "step1-pool-raw"
OUT_DIR = HERE / "step2-validation-raw"

ENGINE_PATH = ANALYTICS_SRC / "policy_analytics/discovery/engine.py"
EXPECTED_ENGINE_SHA256 = "fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549"

sys.path[:0] = [str(ANALYTICS_SRC), str(SCHEMAS_SRC), str(SCRIPTS), str(T107_EVIDENCE)]


def _verify_engine() -> str:
    digest = hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest()
    if digest != EXPECTED_ENGINE_SHA256:
        raise SystemExit(f"engine.py sha256 mismatch: got {digest}, expected {EXPECTED_ENGINE_SHA256}")
    return digest


_verify_engine()

import v2_common as vc  # noqa: E402
import policy_analytics.synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics.outcomes import outcome_definition_from_manifest  # noqa: E402

TARGETS: tuple[str, ...] = ("C04", "C06", "C09", "C14", "C15", "C07")


def _rule_key(conditions: list[dict[str, Any]]) -> str:
    return " & ".join(
        f"{c['feature']} {c['operator']} {c['value']!r}"
        for c in sorted(conditions, key=lambda c: (c["feature"], c["operator"], str(c["value"])))
    )


def _collect_probe_rules(pool_doc: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rules: dict[str, list[dict[str, Any]]] = {}
    for item in pool_doc["top60_pool"]:
        rules[_rule_key(item["conditions"])] = item["conditions"]
    for tid in TARGETS:
        summary = pool_doc["per_target_summary"][tid]
        pd = summary.get("productive_descendant")
        if pd is not None:
            rules[_rule_key(pd["conditions"])] = pd["conditions"]
        ba = summary.get("best_j_e_descendant_any")
        if ba is not None:
            rules[_rule_key(ba["conditions"])] = ba["conditions"]
    for hit in pool_doc.get("c07_guard_literal_hits", []):
        rules[_rule_key(hit["conditions"])] = hit["conditions"]
    return rules


def validate_seed(seed: int) -> dict[str, Any]:
    pool_path = POOL_DIR / f"pool-seed-{seed}.json"
    pool_doc = json.loads(pool_path.read_text(encoding="utf-8"))
    rules = _collect_probe_rules(pool_doc)
    family_size = pool_doc["evaluated_hypotheses"]

    validation_mod = importlib.import_module("policy_analytics.validation.apply")
    diagnose_mod = importlib.import_module("diagnose_validation_power")

    with tempfile.TemporaryDirectory(prefix=f"task116-val-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
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
            analysis_run_id=f"task116-probe-seed{seed}",
        )
        if int(summary["family_size"]) != family_size:
            raise SystemExit(f"seed {seed}: family size mismatch")

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
            }

    return {
        "seed": seed,
        "family_size": family_size,
        "n_rules_validated": len(rules),
        "rules": out_rules,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for seed in args.seeds:
        out_path = OUT_DIR / f"val-seed-{seed}.json"
        if out_path.exists():
            print(f"seed {seed}: already validated, skipping")
            continue
        print(f"seed {seed}: validating pool probes...", flush=True)
        result = validate_seed(seed)
        out_path.write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
        n_pass = sum(1 for r in result["rules"].values() if r["verdict"] != "REJECT")
        print(f"  seed {seed}: {result['n_rules_validated']} validated, {n_pass} not-REJECT, wrote {out_path}")
    final_digest = _verify_engine()
    print(f"engine.py sha256 after run: {final_digest} (unchanged)")


if __name__ == "__main__":
    main()
