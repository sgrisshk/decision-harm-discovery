"""TASK-093: re-grade ecommerce's frozen `TASK-068`/`TASK-019` candidates under contract v1.3.0's
corrected `G12` (`ADR-092` follow-on F1).

**Why this script exists rather than a plain `scripts/validate_candidates.py` invocation.** The
official frozen candidate artifacts (`artifacts/blind/task-068-ecommerce-{baseline,cap}-20260827-
001.candidates.json`) are not present in this worktree — `artifacts/` is gitignored and untracked,
so a fresh `git worktree add` checkout never receives them even though they exist in some other
checkouts. This script therefore reproduces the identical candidate set itself, by calling the
real, unmodified `discover_candidates()` against the real `ecommerce` analytical dataset with the
exact documented `TASK-068` configuration, and verifies the reproduction's fidelity against the
real, git-tracked numbers recorded in `docs/benchmark/task-068-ecommerce-preregistration.md` §10
before trusting it for anything (`TASK-075`/`078`/`079`'s own fidelity-check discipline).

It then grades both reproduced candidate sets twice each — once under
`RobustnessSemantics.FIXED_QUANTILE_V1` (contract v1.2.0's superseded, defect-carrying semantics,
so the "before" figure is independently re-derived here too, not merely quoted from the
preregistration doc) and once under the current default (`ROBUSTNESS_SEMANTICS_VERSION`,
`RobustnessSemantics.ONE_BIN_RELATIVE_V2`, contract v1.3.0's corrected semantics) — by calling
`policy_analytics.validation.apply.run_validation` directly, since `scripts/validate_candidates.py`
does not expose a `--robustness-semantics` CLI flag.

No code, gate, threshold, or `ADR-064` fix is changed by this script. It only calls existing,
unmodified functions with different inputs. All outputs are written under `artifacts/` (gitignored,
regenerable) except the final summary JSON, written under `docs/benchmark/` for provenance
alongside `docs/benchmark/task-093-ecommerce-g12-regrade.md`, matching `TASK-070`'s own precedent
(`docs/benchmark/task-070-validation-power-remeasurement-raw.json`).

Usage:
  uv run python scripts/diagnose_task093_ecommerce_g12_regrade.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.discovery.engine import (  # noqa: E402
    DISCOVERY_METHOD_VERSION,
    DiscoveryConfig,
    discover_candidates,
)
from policy_analytics.domain_benchmarks.ecommerce import SPEC  # noqa: E402
from policy_analytics.outcomes.manifest_binding import (  # noqa: E402
    outcome_definition_from_manifest,
)
from policy_analytics.validation.apply import load_analytical_frame, run_validation  # noqa: E402
from policy_analytics.validation.contract import (  # noqa: E402
    CONTRACT_VERSION,
    ROBUSTNESS_SEMANTICS_VERSION,
    GateId,
    RobustnessSemantics,
)

DATASET_ROOT = (
    REPOSITORY / "synthetic_data_domains/ecommerce/analytical/ecommerce-analytical-v1.0.0"
)
DISCOVERY_OUT_DIR = REPOSITORY / "artifacts/discovery"
VALIDATION_OUT_DIR = REPOSITORY / "artifacts/validation"
RAW_OUTPUT_PATH = REPOSITORY / "docs/benchmark/task-093-ecommerce-g12-regrade-raw.json"

#: `docs/benchmark/task-068-ecommerce-preregistration.md` §10.2 -- both official runs.
EXPECTED_DATASET_IDENTITY = "fb8d049d5f81bb0d792ead8d6310e301b998f4eed7acf63a3274456b9f56c658"
EXPECTED_EVALUATED_HYPOTHESES = 17523
EXPECTED_CANDIDATE_COUNT = 15

#: §10.5's structural-check table -- the exact per-feature-identity slot counts frozen candidates
#: produced. Reproduction fidelity is judged against this table exactly, not just aggregate counts.
EXPECTED_FEATURE_SLOTS = {
    "baseline": {
        "discount_pct": 11,
        "product_price_usd": 8,
        "quantity": 4,
        "items_in_cart": 2,
        "coupon_used": 2,
        "acquisition_channel": 2,
        "product_tier": 1,
    },
    "cap": {
        "discount_pct": 5,
        "product_price_usd": 5,
        "quantity": 5,
        "product_category": 5,
        "items_in_cart": 4,
        "coupon_used": 1,
        "acquisition_channel": 1,
        "product_tier": 3,
        "days_since_last_visit": 1,
    },
}

ARMS: dict[str, float] = {"baseline": 1.0, "cap": 0.34}

SEMANTICS: dict[str, RobustnessSemantics] = {
    "before_v1.2.0_fixed_quantile": RobustnessSemantics.FIXED_QUANTILE_V1,
    "after_v1.3.0_one_bin_relative": RobustnessSemantics.ONE_BIN_RELATIVE_V2,
}

assert ROBUSTNESS_SEMANTICS_VERSION is RobustnessSemantics.ONE_BIN_RELATIVE_V2


def _feature_identity_slots(candidates: list[dict[str, Any]]) -> dict[str, int]:
    """§5a's structural check: distinct-feature-identity slot tally over all frozen conditions."""
    tally: dict[str, int] = {}
    for candidate in candidates:
        for condition in candidate["conditions"]:
            feature = condition["feature"]
            tally[feature] = tally.get(feature, 0) + 1
    return tally


def reproduce_candidates(arm: str, fraction: float) -> dict[str, Any]:
    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_identity_sha256"] != EXPECTED_DATASET_IDENTITY:
        raise ValueError(
            f"ecommerce analytical dataset identity {manifest['dataset_identity_sha256']!r} does "
            f"not match the preregistration's recorded identity {EXPECTED_DATASET_IDENTITY!r} -- "
            "refusing to reproduce against the wrong dataset instance."
        )
    frame = load_analytical_frame(DATASET_ROOT)
    outcome, outcome_definition_version = outcome_definition_from_manifest(manifest, DATASET_ROOT)

    # Same rule `scripts/run_discovery.py` applies for travel: every DECISION_TIME column is an
    # eligible discovery feature except the domain's own decision-timestamp column itself (a raw
    # calendar date is not a reusable policy-rule condition). Derived generically from the
    # registered `DomainSpec`, not hardcoded to ecommerce's column names.
    feature_columns = tuple(
        name
        for name, (classification, _description) in SPEC.feature_timing.items()
        if classification == "DECISION_TIME" and name != SPEC.decision_timestamp_column
    )

    config = DiscoveryConfig(seed=1729, max_feature_identity_fraction=fraction)
    result = discover_candidates(frame, feature_columns, outcome, config)

    payload = {
        "status": "PERSISTED",
        "run_id": f"task-093-ecommerce-{arm}-reproduction",
        "discovery_method_version": DISCOVERY_METHOD_VERSION,
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "dataset_version": manifest["dataset_version"],
        "outcome_contract_version": outcome_definition_version,
        "search": result["search"],
        "outcome": result["outcome"],
        "candidate_count": result["candidate_count"],
        "candidates": result["candidates"],
    }

    out_path = DISCOVERY_OUT_DIR / f"task-093-ecommerce-{arm}-candidates.json"
    DISCOVERY_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "arm": arm,
        "max_feature_identity_fraction": fraction,
        "candidates_path": str(out_path),
        "manifest": manifest,
        "outcome": outcome,
        "outcome_definition_version": outcome_definition_version,
        "evaluated_hypotheses": result["search"]["evaluated_hypotheses"],
        "candidate_count": result["candidate_count"],
        "feature_identity_slots": _feature_identity_slots(result["candidates"]),
        "distinct_feature_identities": len(_feature_identity_slots(result["candidates"])),
    }


def check_fidelity(reproductions: dict[str, dict[str, Any]]) -> list[str]:
    """Compare the reproduction against every real, git-tracked figure available to check
    against. Returns a list of mismatch descriptions; empty means fidelity confirmed."""
    problems: list[str] = []
    for arm, repro in reproductions.items():
        if repro["evaluated_hypotheses"] != EXPECTED_EVALUATED_HYPOTHESES:
            problems.append(
                f"{arm}: evaluated_hypotheses={repro['evaluated_hypotheses']}, "
                f"expected {EXPECTED_EVALUATED_HYPOTHESES} (task-068-ecommerce-preregistration.md "
                "§10.2)"
            )
        if repro["candidate_count"] != EXPECTED_CANDIDATE_COUNT:
            problems.append(
                f"{arm}: candidate_count={repro['candidate_count']}, expected "
                f"{EXPECTED_CANDIDATE_COUNT}"
            )
        expected_slots = EXPECTED_FEATURE_SLOTS[arm]
        actual_slots = repro["feature_identity_slots"]
        # Compare only the non-zero entries the preregistration table records; a feature absent
        # from both sides is not a mismatch (the table records zero-slot features as "0", i.e.
        # simply omitted from a tally dict built the same way this script's is).
        expected_nonzero = {k: v for k, v in expected_slots.items() if v > 0}
        if actual_slots != expected_nonzero:
            problems.append(
                f"{arm}: feature_identity_slots={actual_slots}, expected {expected_nonzero} "
                "(task-068-ecommerce-preregistration.md §10.5)"
            )
    return problems


def grade(
    repro: dict[str, Any], semantics_label: str, semantics: RobustnessSemantics
) -> dict[str, Any]:
    manifest = repro["manifest"]
    analysis_run_id = f"task-093-{repro['arm']}-{semantics_label}"
    output_path = VALIDATION_OUT_DIR / f"{analysis_run_id}.json"
    results, run_manifest = run_validation(
        dataset_root=DATASET_ROOT,
        candidates_path=Path(repro["candidates_path"]),
        outcome=repro["outcome"],
        dataset_version=manifest["dataset_version"],
        outcome_definition_version=repro["outcome_definition_version"],
        analysis_run_id=analysis_run_id,
        robustness_semantics=semantics,
    )

    verdict_counts: dict[str, int] = {}
    evidence_level_counts: dict[str, int] = {}
    per_candidate: list[dict[str, Any]] = []
    for result in results:
        verdict_counts[result.verdict] = verdict_counts.get(result.verdict, 0) + 1
        level = result.report.evidence_level
        level_key = level.value if level is not None else "REJECTED"
        evidence_level_counts[level_key] = evidence_level_counts.get(level_key, 0) + 1
        gate_by_id = {g.gate_id: g for g in result.report.gate_results}
        g12 = gate_by_id[GateId.ROBUSTNESS]
        g09 = gate_by_id[GateId.SIMPSON]
        per_candidate.append(
            {
                "candidate_id": result.candidate_id,
                "pattern_definition": result.report.pattern_definition,
                "verdict": result.verdict,
                "evidence_level": level_key,
                "g12_outcome": g12.outcome.value,
                "g12_detail": g12.detail,
                "g09_outcome": g09.outcome.value,
                "g09_detail": g09.detail,
            }
        )

    # Serialize the full frozen-report-shaped payload too, for provenance, mirroring
    # `scripts/validate_candidates.py`'s own output shape (including `candidates_source` so
    # `scripts/evaluate_benchmark.py` could load it downstream if evidence levels ever moved).
    full_payload = {
        "status": "FROZEN",
        "analysis_run_id": analysis_run_id,
        "validation_contract_version": CONTRACT_VERSION,
        "robustness_semantics_requested": semantics.value,
        "dataset_version": manifest["dataset_version"],
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "candidates_source": repro["candidates_path"],
        "hidden_ground_truth_opened": False,
        "verdict_counts": verdict_counts,
        "run_manifest": run_manifest,
        "candidates": [
            {
                "candidate_id": result.candidate_id,
                "verdict": result.verdict,
                "validation_report": result.report.to_dict(),
            }
            for result in results
        ],
    }
    VALIDATION_OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(full_payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )

    g12_pass = sum(1 for c in per_candidate if c["g12_outcome"] == "pass")
    g12_fail = sum(1 for c in per_candidate if c["g12_outcome"] in ("fail", "not_evaluated"))

    return {
        "semantics_label": semantics_label,
        "semantics_value": semantics.value,
        "report_path": str(output_path),
        "g12_pass": g12_pass,
        "g12_fail_or_not_evaluated": g12_fail,
        "verdict_counts": verdict_counts,
        "evidence_level_counts": evidence_level_counts,
        "per_candidate": per_candidate,
    }


def main() -> None:
    reproductions = {arm: reproduce_candidates(arm, fraction) for arm, fraction in ARMS.items()}

    fidelity_problems = check_fidelity(reproductions)
    summary: dict[str, Any] = {
        "task": "TASK-093",
        "dataset_identity_sha256": EXPECTED_DATASET_IDENTITY,
        "fidelity_check": {
            "passed": not fidelity_problems,
            "problems": fidelity_problems,
        },
    }

    if fidelity_problems:
        print("FIDELITY CHECK FAILED:")
        for problem in fidelity_problems:
            print(f"  - {problem}")
        RAW_OUTPUT_PATH.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        raise SystemExit(1)

    print("Fidelity check PASSED: reproduction matches every checkable recorded figure exactly.")

    grades: dict[str, dict[str, Any]] = {}
    for arm, repro in reproductions.items():
        for semantics_label, semantics in SEMANTICS.items():
            key = f"{arm}__{semantics_label}"
            grades[key] = grade(repro, semantics_label, semantics)
            print(
                f"{arm} / {semantics_label}: G12 pass={grades[key]['g12_pass']} "
                f"fail_or_ne={grades[key]['g12_fail_or_not_evaluated']} "
                f"evidence_levels={grades[key]['evidence_level_counts']}"
            )

    summary["reproductions"] = {
        arm: {
            "max_feature_identity_fraction": r["max_feature_identity_fraction"],
            "evaluated_hypotheses": r["evaluated_hypotheses"],
            "candidate_count": r["candidate_count"],
            "distinct_feature_identities": r["distinct_feature_identities"],
            "feature_identity_slots": r["feature_identity_slots"],
            "candidates_path": r["candidates_path"],
        }
        for arm, r in reproductions.items()
    }
    summary["grades"] = grades
    RAW_OUTPUT_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print(f"\nRaw summary written to {RAW_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
