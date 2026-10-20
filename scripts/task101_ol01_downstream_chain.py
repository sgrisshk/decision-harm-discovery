"""TASK-101/ADR-096 step 4/5: full, unmodified downstream chain for `OL01` under the new
`_eligible()` search-eligibility mechanism -- candidate generation -> statistical validation ->
confounding/safety gates (including `G16`, run exactly as it stands today) -> promotion.

Not part of the official discovery/validation pipeline. Disclosed, non-production forensic/
experiment tooling, matching `scripts/task100_run_experiment.py`/`scripts/diagnose_*` precedent.
Reuses `scripts/task100_run_experiment.py`'s own already-reviewed join/split/classification/
outcome/Stage-3-scaffolding functions verbatim (imported by file path, nothing re-derived) so the
frame and validation-input scaffolding are byte-identical in construction to what `TASK-100` itself
used -- the only thing different from a literal `TASK-100` re-run is the installed `engine.py`
(the new mechanism) and that this script scopes itself to `OUTCOME_LATE` only (the outcome `OL01`
uses), at both scales, rather than all four patterns/outcomes.

Usage:
  uv run python3 scripts/task101_ol01_downstream_chain.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402
from policy_analytics.discovery.engine import DiscoveryConfig, discover_candidates  # noqa: E402
from policy_analytics.validation.apply import run_validation  # noqa: E402

ARTIFACTS = REPOSITORY / "artifacts/task-101"
ARTIFACTS.mkdir(parents=True, exist_ok=True)

TASK100_SCRIPT = REPOSITORY / "scripts" / "task100_run_experiment.py"


def _load_task100_module() -> Any:
    spec = importlib.util.spec_from_file_location("task100_run_experiment", TASK100_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: object) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> None:
    t100 = _load_task100_module()

    print("Phase 1-3: join, split, real TASK-008 classification (real Olist data)...")
    frame = t100.phase1_join()
    frame, _split_info = t100.phase2_split(frame)
    matched = t100.build_matched_downsample(frame)
    classifications = t100.phase3_classify(frame)

    dev_full_raw = frame.filter(pl.col("split_label") == "development")
    frame_full_outcomes, _p25_full = t100.add_outcomes(frame, development_only_for_p25=dev_full_raw)

    dev_matched_raw = matched.filter(pl.col("split_label") == "development")
    frame_matched_outcomes, _p25_matched = t100.add_outcomes(
        matched, development_only_for_p25=dev_matched_raw
    )

    outcome = t100.outcome_definitions()["OUTCOME_LATE"]
    feature_cols = t100.feature_columns_for(classifications, "OUTCOME_LATE")
    print(f"OUTCOME_LATE feature_columns ({len(feature_cols)}): {feature_cols}")

    scale_frames = {"full": frame_full_outcomes, "matched": frame_matched_outcomes}
    dev_by_scale = {
        "full": frame_full_outcomes.filter(pl.col("split_label") == "development"),
        "matched": frame_matched_outcomes.filter(pl.col("split_label") == "development"),
    }

    config = DiscoveryConfig()  # the real, current default -- the fixed engine, no overrides
    summary: dict[str, Any] = {}

    for scale_name in scale_frames:
        print(f"\n=== scale={scale_name} ===")
        dev = dev_by_scale[scale_name]
        eligible = dev.filter(pl.col("OUTCOME_LATE_eligible"))
        run_frame = eligible.select([*feature_cols, outcome.column, "split_label"])

        # --- Stage 2: real, unmodified discover_candidates, new engine ---
        stage2 = discover_candidates(run_frame, feature_cols, outcome, config)
        print(
            f"Stage 2: evaluated_hypotheses={stage2['search']['evaluated_hypotheses']} "
            f"candidate_count={stage2['candidate_count']}"
        )
        ol01_candidates = [
            c
            for c in stage2["candidates"]
            if any(
                cond["feature"] == "seller_customer_cross_state" and cond["operator"] == "ge"
                for cond in c["conditions"]
            )
        ]
        ol01_ids_preview = [c["candidate_id"] for c in ol01_candidates]
        print(f"Candidates touching OL01's own atom: {ol01_ids_preview}")
        for c in ol01_candidates:
            support = c["development"]["support"]
            print(f"  {c['candidate_id']}: {c['conditions']} support={support:.4f}")

        # --- Stage 3: real, unmodified run_validation (G16 and every other gate, untouched) ---
        eligible_key = f"OUTCOME_LATE__{scale_name}"
        dataset_root = ARTIFACTS / "analytical" / eligible_key
        manifest = t100.build_manifest_and_partitions(
            dataset_root,
            eligible,
            feature_cols,
            outcome,
            classifications,
            dataset_version=eligible_key,
        )
        candidates_payload = dict(stage2)
        candidates_payload["status"] = "PERSISTED"
        candidates_path = dataset_root / "candidates.json"
        _write_json(candidates_path, candidates_payload)

        validations, _run_meta = run_validation(
            dataset_root=dataset_root,
            candidates_path=candidates_path,
            outcome=outcome,
            dataset_version=eligible_key,
            outcome_definition_version="task-101-v1",
            analysis_run_id=f"task101-{eligible_key}",
            bootstrap_seed=1729,
        )
        print(f"Stage 3: {len(validations)} candidates validated (all gates, including G16)")

        ol01_ids = {c["candidate_id"] for c in ol01_candidates}
        scale_result: dict[str, Any] = {
            "manifest_dataset_identity_sha256": manifest["dataset_identity_sha256"],
            "stage2_evaluated_hypotheses": stage2["search"]["evaluated_hypotheses"],
            "stage2_candidate_count": stage2["candidate_count"],
            "stage2_ol01_candidates": [
                {
                    "candidate_id": c["candidate_id"],
                    "conditions": c["conditions"],
                    "development": c["development"],
                }
                for c in ol01_candidates
            ],
            "stage3_ol01_validations": [],
        }
        for v in validations:
            if v.candidate_id not in ol01_ids:
                continue
            gate_results = {g.gate_id.value: g.outcome.value for g in v.report.gate_results}
            g16 = gate_results.get("G16_CANDIDATE_COMPOSITION_SAFETY")
            evidence_level = v.report.evidence_level.value if v.report.evidence_level else None
            print(
                f"  {v.candidate_id}: verdict={v.verdict} evidence_level={evidence_level} "
                f"policy_readiness={v.report.policy_readiness.value} G16={g16}"
            )
            scale_result["stage3_ol01_validations"].append(
                {
                    "candidate_id": v.candidate_id,
                    "verdict": v.verdict,
                    "pattern_definition": v.report.pattern_definition,
                    "evidence_level": (
                        v.report.evidence_level.value if v.report.evidence_level else None
                    ),
                    "policy_readiness": v.report.policy_readiness.value,
                    "gate_results": gate_results,
                    "raw_effect": v.report.raw_effect.value,
                    "exposed_records": v.report.exposed_records,
                    "failure_modes": list(v.report.failure_modes),
                }
            )
        summary[scale_name] = scale_result

    out_path = ARTIFACTS / "ol01_downstream_chain_summary.json"
    _write_json(out_path, summary)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
