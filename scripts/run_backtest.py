"""CLI: run the TASK-032 policy backtest for every eligible candidate in a frozen validation report.

**Eligibility** matches `docs/product/policy-candidate-domain-model.md` §1 exactly: only
candidates whose `policy_readiness` is `shadow_policy` or `high_confidence` — the same gate a real
Policy Candidate would need to exist at all. A candidate that never reached that readiness has
nothing to backtest; this script does not compute or report a number for it.

Never opens `hidden_ground_truth.json` — this is a real backtest over the actual `future_holdout`
split of the analytical dataset, not an evaluation against synthetic ground truth (that is
`scripts/validate_backtest_synthetic.py`, TASK-033, run only after this methodology is frozen).

**Frozen results are immutable** — same discipline as `validate_candidates.py`/
`evaluate_benchmark.py`: refuses to overwrite an existing output file without `--force`.

Usage:
  uv run python scripts/run_backtest.py \\
      --validation-report artifacts/validation/task-019-official-...-001.json \\
      --output artifacts/backtest/task-032-backtest-...-001.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.backtest import BACKTEST_CONTRACT_VERSION, run_backtest  # noqa: E402
from policy_analytics.outcomes import primary_outcome  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    BOOTSTRAP_SEED,
    Condition,
    load_analytical_frame,
)

DEFAULT_DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
ELIGIBLE_READINESS = ("shadow_policy", "high_confidence")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cost-per-review-eur",
        type=float,
        default=None,
        help="assumed operational cost per flagged review, EUR — omit to leave operational_cost "
        "null (no invented figure; see docs/analytics/policy-backtest-contract.md)",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.output.exists() and not args.force:
        print(
            f"{args.output} already exists and is a frozen result. Refusing to overwrite without "
            "--force.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    validation = json.loads(args.validation_report.read_text(encoding="utf-8"))
    candidates_source = Path(validation["candidates_source"])
    candidates_payload = json.loads(candidates_source.read_text(encoding="utf-8"))
    raw_by_id = {c["candidate_id"]: c for c in candidates_payload["candidates"]}

    eligible = [
        c
        for c in validation["candidates"]
        if c["validation_report"]["policy_readiness"] in ELIGIBLE_READINESS
    ]
    if not eligible:
        print("No candidate reached shadow_policy/high_confidence readiness; nothing to backtest.")

    frame = load_analytical_frame(args.dataset_root)
    outcome = primary_outcome()
    rng = random.Random(BOOTSTRAP_SEED)

    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for entry in eligible:
        candidate_id = entry["candidate_id"]
        raw = raw_by_id[candidate_id]
        conditions = [Condition(c["feature"], c["operator"], c["value"]) for c in raw["conditions"]]
        try:
            result = run_backtest(
                frame=frame,
                conditions=conditions,
                outcome=outcome,
                cost_per_review_eur=args.cost_per_review_eur,
                rng=rng,
            )
        except ValueError as exc:
            skipped.append({"candidate_id": candidate_id, "reason": str(exc)})
            continue
        results.append(
            {
                "candidate_id": candidate_id,
                "policy_readiness": entry["validation_report"]["policy_readiness"],
                "evidence_level": entry["validation_report"]["evidence_level"],
                "pattern_definition": entry["validation_report"]["pattern_definition"],
                "backtest_result": result.to_dict(),
            }
        )

    payload = {
        "status": "FROZEN",
        "frozen_at": datetime.now(UTC).isoformat(),
        "task": "TASK-032",
        "backtest_contract_version": BACKTEST_CONTRACT_VERSION,
        "validation_report_source": str(args.validation_report),
        "eligible_readiness_values": list(ELIGIBLE_READINESS),
        "cost_per_review_eur_assumed": args.cost_per_review_eur,
        "hidden_ground_truth_opened": False,
        "results": results,
        "skipped": skipped,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Backtested {len(results)} eligible candidate(s); {len(skipped)} skipped.")
    for row in results:
        r = row["backtest_result"]
        print(
            f"  {row['candidate_id']}: affected={r['affected_decisions']} "
            f"avoided_bad={r['avoided_bad_outcomes']} "
            f"suppressed_good={r['suppressed_good_outcomes']}"
        )
        print(
            f"    benefit={r['benefit']['value']:.0f} "
            f"no_measurable_net_effect={r['no_measurable_net_effect']}"
        )
    for row in skipped:
        print(f"  SKIPPED {row['candidate_id']}: {row['reason']}")


if __name__ == "__main__":
    main()
