"""CLI: apply the TASK-018 validation contract to persisted TASK-015 candidates (TASK-019).

Never opens hidden ground truth. Freezes its output as a versioned validation-report artifact for
a separate benchmark-evaluation step (TASK-028) to later compare against ground truth independently.

**Frozen results are immutable.** This script refuses to overwrite an existing output file unless
`--force` is passed, specifically so a code or contract change (e.g. the ADR-014/ADR-015 G05 fix)
can never silently rewrite a result that was already frozen and referenced elsewhere (TASKS.md,
HANDOFF-016, ADR-014/ADR-015). Re-grading the same candidates under a new contract version is a
new run with its own record, not a correction of the old one
(`docs/analytics/validation-contract.md` §2).

**Two candidate document shapes are supported**, matching the two produced in this repository:
the original discovery engine's inline shape (`--candidates` alone; `evaluated_hypotheses` nested
under `search`) and the blind-agent output schema (`tools/blind_agent/models.py`,
`OUTPUT_SCHEMA_VERSION = "1.1.0"`; pass its sibling `discovery_metrics.json` via `--metrics`, since
that schema does not carry the evaluated-hypothesis count inline). A frozen blind run's outputs
land at `<BLIND_RUNS_ROOT>/<run-id>/frozen/candidates.json` and
`<BLIND_RUNS_ROOT>/<run-id>/frozen/discovery_metrics.json` (`blind/README.md`).

**Compliance is asserted explicitly, not inferred.** Whenever `--candidates` points anywhere other
than the historical dry-run artifact, `--blind-compliant` and `--founder-block-lifted` are
required — this script does not parse `TASKS.md`/`HANDOFF-*` prose to guess whether a candidate
artifact is actually usable; the operator states it, and the statement is frozen into the record
alongside the result so a later reader never has to trust an unstated default.

Usage:
  uv run python scripts/validate_candidates.py            # reproduce the historical dry run
  uv run python scripts/validate_candidates.py \\
      --candidates /tmp/policy-blind-runs/<run-id>/frozen/candidates.json \\
      --metrics    /tmp/policy-blind-runs/<run-id>/frozen/discovery_metrics.json \\
      --output artifacts/validation/task-019-validation-report-<run-id>.json \\
      --analysis-run-id task-019-validation-run-<run-id> \\
      --blind-compliant --founder-block-lifted
"""

from __future__ import annotations

import argparse
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

DEFAULT_DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
DEFAULT_CANDIDATES_PATH = REPOSITORY / "artifacts/discovery/task-015-candidates.json"
DEFAULT_OUTPUT_PATH = REPOSITORY / "artifacts/validation/task-019-validation-report.json"
DEFAULT_ANALYSIS_RUN_ID = "task-019-validation-run-1"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument(
        "--metrics",
        type=Path,
        default=None,
        help="sibling discovery_metrics.json, required for blind-agent-schema candidate documents",
    )
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--analysis-run-id", type=str, default=DEFAULT_ANALYSIS_RUN_ID)
    parser.add_argument(
        "--force", action="store_true", help="allow overwriting an existing output file"
    )
    parser.add_argument(
        "--blind-compliant",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="required (--blind-compliant or --no-blind-compliant) whenever --candidates is not "
        "the historical dry-run default; states whether this artifact satisfies ADR-008/TASK-017",
    )
    parser.add_argument(
        "--founder-block-lifted",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="required alongside --blind-compliant; states whether the founder readiness block "
        "on TASK-015/TASK-016 has been lifted for this artifact",
    )
    args = parser.parse_args(argv)

    is_default_run = args.candidates == DEFAULT_CANDIDATES_PATH
    if not is_default_run and (args.blind_compliant is None or args.founder_block_lifted is None):
        parser.error(
            "--candidates points at a non-default artifact; --blind-compliant/--no-blind-compliant "
            "and --founder-block-lifted/--no-founder-block-lifted are both required so compliance "
            "is recorded explicitly rather than assumed"
        )
    if is_default_run:
        # Reproducing the historical dry run: these are known facts about that specific artifact,
        # not a fresh assertion — see TASK-015's evidence trail in TASKS.md.
        args.blind_compliant = False
        args.founder_block_lifted = False
    return args


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.output.exists() and not args.force:
        print(
            f"{args.output} already exists and is a frozen result (status=FROZEN). Refusing to "
            "overwrite it. Point --output at a new file, or pass --force with a clear reason "
            "recorded in TASKS.md/HANDOFFS.md — do not use --force to silently regrade the same "
            "candidates under a changed contract.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    manifest = json.loads((args.dataset_root / "manifest.json").read_text(encoding="utf-8"))
    frozen_identity = manifest["dataset_identity_sha256"]
    candidates_payload = json.loads(args.candidates.read_text(encoding="utf-8"))
    candidates_identity = candidates_payload.get("dataset_identity_sha256")
    identity_note = None
    if candidates_identity is not None and candidates_identity != frozen_identity:
        identity_note = (
            f"Candidate artifact pins dataset_identity_sha256={candidates_identity}, current "
            f"manifest reports {frozen_identity}. This must be reconciled by hand before trusting "
            "the result — confirm whether the underlying row-level partitions actually match "
            "(e.g. via `git diff` on features.csv/outcomes.csv/identifiers.csv) or whether this "
            "candidate set was genuinely computed against different data, in which case it cannot "
            "be validated against this dataset_root at all."
        )

    results, run_manifest = run_validation(
        dataset_root=args.dataset_root,
        candidates_path=args.candidates,
        outcome=primary_outcome(),
        dataset_version=manifest["dataset_version"],
        outcome_definition_version=OUTCOME_CONTRACT_VERSION,
        analysis_run_id=args.analysis_run_id,
        metrics_path=args.metrics,
    )

    verdict_counts: dict[str, int] = {}
    for result in results:
        verdict_counts[result.verdict] = verdict_counts.get(result.verdict, 0) + 1

    payload = {
        "status": "FROZEN",
        "frozen_at": datetime.now(UTC).isoformat(),
        "analysis_run_id": args.analysis_run_id,
        "validation_contract_version": CONTRACT_VERSION,
        "outcome_contract_version": OUTCOME_CONTRACT_VERSION,
        "dataset_version": manifest["dataset_version"],
        "dataset_identity_sha256": frozen_identity,
        "dataset_identity_reconciliation": identity_note,
        "candidates_source": str(args.candidates),
        "metrics_source": str(args.metrics) if args.metrics else None,
        "hidden_ground_truth_opened": False,
        "process_compliance": {
            "blind_discovery_protocol_satisfied": args.blind_compliant,
            "founder_readiness_block_lifted": args.founder_block_lifted,
            "note": (
                "Both fields are an explicit operator assertion recorded at run time (see "
                "--blind-compliant/--founder-block-lifted), not something this script verifies "
                "against ADR-008 or TASKS.md automatically. A PASS verdict below is not usable "
                "evidence unless both are true."
            ),
        },
        "g05_methodology": {
            "gate": "G05_MULTIPLE_COMPARISONS",
            "note": (
                "Contract v1.0.0's G05 used an empirical bootstrap tail-count p-value "
                "(bootstrap_two_sided_p), whose 2000-replicate resolution floor (~0.0005) could "
                "not pass BH correction at family sizes in the low thousands regardless of true "
                "effect size (ADR-014). Fixed in v1.1.0: G05's binding p-value is "
                "normal_approx_two_sided_p on the bootstrap standard error, which has no such "
                "floor (ADR-015). validation_contract_version above records which version graded "
                "this run — see docs/analytics/validation-contract.md §4a."
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

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Verdicts: {verdict_counts}")
    print(
        f"process_compliance: blind_compliant={args.blind_compliant} "
        f"founder_block_lifted={args.founder_block_lifted}"
    )
    for result in results:
        print(f"  {result.candidate_id}: {result.verdict} ({result.report.evidence_level})")


if __name__ == "__main__":
    main()
