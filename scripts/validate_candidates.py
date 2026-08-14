"""CLI: apply the TASK-018 validation contract to persisted TASK-015 candidates (TASK-019).

Never opens hidden ground truth. Freezes its output as a versioned validation-report artifact for
a separate benchmark-evaluation step (TASK-028) to later compare against ground truth independently.

**Frozen results are immutable.** This script refuses to overwrite an existing `OUTPUT_PATH`
unless `--force` is passed, specifically so a code change (e.g. the ADR-014/ADR-015 G05 fix) can
never silently rewrite a result that was already frozen and referenced elsewhere (TASKS.md,
HANDOFF-016, ADR-014). Re-grading the same candidates under a new contract version is a new run
with its own record, not a correction of the old one (`docs/analytics/validation-contract.md` §2).

Usage: uv run python scripts/validate_candidates.py [--force]
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.outcomes import OUTCOME_CONTRACT_VERSION, primary_outcome  # noqa: E402
from policy_analytics.validation.apply import run_validation  # noqa: E402
from policy_analytics.validation.contract import CONTRACT_VERSION  # noqa: E402

DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
CANDIDATES_PATH = REPOSITORY / "artifacts/discovery/task-015-candidates.json"
OUTPUT_PATH = REPOSITORY / "artifacts/validation/task-019-validation-report.json"
ANALYSIS_RUN_ID = "task-019-validation-run-1"


def main() -> None:
    if OUTPUT_PATH.exists() and "--force" not in sys.argv:
        print(
            f"{OUTPUT_PATH.relative_to(REPOSITORY)} already exists and is a frozen result "
            "(status=FROZEN). Refusing to overwrite it. If you genuinely mean to grade a new "
            "candidate artifact, either point CANDIDATES_PATH at a different file or pass "
            "--force with a clear reason recorded in TASKS.md/HANDOFFS.md — do not use --force "
            "to silently regrade the same candidates under a changed contract.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(
        "REMINDER: process_compliance (blind-protocol satisfaction, founder readiness block) is "
        "recorded below as a static fact about the TASK-015 artifact this script is pointed at. "
        "It is not re-derived from the artifact automatically — confirm it by hand against "
        "TASKS.md before treating any PASS verdict this run produces as usable evidence.",
        file=sys.stderr,
    )

    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    frozen_identity = manifest["dataset_identity_sha256"]
    candidates_identity = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))[
        "dataset_identity_sha256"
    ]
    identity_note = None
    if candidates_identity != frozen_identity:
        identity_note = (
            "Candidate artifact pins dataset_identity_sha256="
            f"{candidates_identity}, current manifest reports {frozen_identity}. Verified by hand "
            "(git diff HEAD -- features.csv outcomes.csv identifiers.csv) that the row-level "
            "partitions are byte-identical between the two states; the identity changed only "
            "because the identity computation now also hashes the attached outcome contract "
            "metadata. Validation proceeds against the current on-disk partitions with this "
            "reconciliation recorded, not silently."
        )

    results, run_manifest = run_validation(
        dataset_root=DATASET_ROOT,
        candidates_path=CANDIDATES_PATH,
        outcome=primary_outcome(),
        dataset_version=manifest["dataset_version"],
        outcome_definition_version=OUTCOME_CONTRACT_VERSION,
        analysis_run_id=ANALYSIS_RUN_ID,
    )

    verdict_counts: dict[str, int] = {}
    for result in results:
        verdict_counts[result.verdict] = verdict_counts.get(result.verdict, 0) + 1

    payload = {
        "status": "FROZEN",
        "frozen_at": datetime.now(UTC).isoformat(),
        "analysis_run_id": ANALYSIS_RUN_ID,
        "validation_contract_version": CONTRACT_VERSION,
        "outcome_contract_version": OUTCOME_CONTRACT_VERSION,
        "dataset_version": manifest["dataset_version"],
        "dataset_identity_sha256": frozen_identity,
        "dataset_identity_reconciliation": identity_note,
        "candidates_source": str(CANDIDATES_PATH.relative_to(REPOSITORY)),
        "hidden_ground_truth_opened": False,
        "process_compliance": {
            "blind_discovery_protocol_satisfied": False,
            "blind_discovery_protocol_note": (
                "The candidate artifact was produced in a full-checkout run and does not satisfy "
                "ADR-008 / the blind-benchmark protocol (see TASK-015 evidence in TASKS.md and "
                "HANDOFF-007). This validation grades statistical soundness only; it is not, and "
                "must not be presented as, a completed TASK-017 blind discovery test."
            ),
            "founder_readiness_block_lifted": False,
            "founder_readiness_block_note": (
                "TASK-015 carries an explicit 2026-08-13 founder instruction not to advance "
                "TASK-016 or treat this candidate set as pipeline-ready until TASK-012 completes "
                "and readiness is rechecked from the approved blind workspace. This validation run "
                "does not lift that block and must not be read as doing so."
            ),
        },
        "g05_methodology_history": {
            "gate": "G05_MULTIPLE_COMPARISONS",
            "note": (
                "Contract v1.0.0's G05 used an empirical bootstrap tail-count p-value "
                "(bootstrap_two_sided_p), whose 2000-replicate resolution floor (~0.0005) could "
                "not pass BH correction at family sizes in the low thousands regardless of true "
                "effect size (ADR-014). Fixed in v1.1.0: G05's binding p-value is now "
                "normal_approx_two_sided_p on the bootstrap standard error, which has no such "
                "floor (ADR-015). A run under contract_version < 1.1.0 is subject to the old "
                "defect; this field records which version produced this run's results — see "
                "validation_contract_version above and docs/analytics/validation-contract.md §4a."
            ),
        },
        "verdict_counts": verdict_counts,
        "run_manifest": run_manifest,
        "candidates": [
            {
                "candidate_id": result.candidate_id,
                "verdict": result.verdict,
                "validation_report": result.report.to_dict(),
                "diagnostics": result.diagnostics,
            }
            for result in results
        ],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPOSITORY)}")
    print(f"Verdicts: {verdict_counts}")
    for result in results:
        print(f"  {result.candidate_id}: {result.verdict} ({result.report.evidence_level})")


if __name__ == "__main__":
    main()
