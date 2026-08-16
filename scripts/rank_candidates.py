"""CLI: rank persisted TASK-015 candidates by economic impact, support, stability, actionability,
and novelty (TASK-016).

Never opens hidden ground truth. Consumes an already-frozen `status=PERSISTED` candidates document
(the blind-agent schema or the original discovery-engine shape) plus the analytical dataset, and
writes a versioned ranking artifact. See `policy_analytics.discovery.ranking` for the scoring
method and `policy_analytics.discovery.ranking_signals` for how its inputs are derived. Ranking
never edits, drops, reorders within, or adds to the persisted candidate list, nor changes any of a
candidate's own committed metrics — it only orders and annotates an already-frozen set.

**Frozen results are immutable**, matching `scripts/validate_candidates.py`'s discipline: point
`--output` at a new file (or pass `--force` with a reason recorded in TASKS.md/HANDOFFS.md) rather
than silently overwrite a ranking result that may already be referenced elsewhere.

Usage:
  uv run python scripts/rank_candidates.py \\
      --candidates artifacts/blind/task-015-official-20260816-015.candidates.json \\
      --dataset-root synthetic_data/analytical/travel-bookings-analytical-v1.0.0 \\
      --output artifacts/discovery/task-016-candidate-ranking-task-015-official-20260816-015.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.discovery.ranking import (  # noqa: E402
    DEFAULT_WEIGHTS,
    RANKING_METHOD_VERSION,
    rank_candidates,
)
from policy_analytics.discovery.ranking_signals import build_candidate_signals  # noqa: E402
from policy_analytics.outcomes import OUTCOME_CONTRACT_VERSION, primary_outcome  # noqa: E402
from policy_analytics.validation.apply import load_analytical_frame  # noqa: E402

DEFAULT_CANDIDATES_PATH = (
    REPOSITORY / "artifacts/blind/task-015-official-20260816-015.candidates.json"
)
DEFAULT_DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
DEFAULT_OUTPUT_PATH = (
    REPOSITORY
    / "artifacts/discovery/task-016-candidate-ranking-task-015-official-20260816-015.json"
)

WEIGHTS_PROVENANCE = (
    "ML_DISCOVERY v0 defaults (candidate-ranking-v0.1.0), fixed from generic business reasoning "
    "before this ranking was ever run against a specific candidate set; not tuned against ranking "
    "output, benchmark grades, or hidden ground truth. Pending Product/Statistics review per "
    "docs/analytics/discovery-design.md section 7 (see HANDOFF-045 in memory/HANDOFFS.md)."
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--force", action="store_true", help="allow overwriting an existing output file"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.output.exists() and not args.force:
        print(
            f"{args.output} already exists and is a frozen ranking result. Refusing to "
            "overwrite it. Point --output at a new file, or pass --force with a clear reason "
            "recorded in TASKS.md/HANDOFFS.md.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    payload = cast(dict[str, Any], json.loads(args.candidates.read_text(encoding="utf-8")))
    status = payload.get("status")
    if status != "PERSISTED":
        raise SystemExit(f"candidates must have status=PERSISTED to be ranked, got {status!r}")

    outcome = primary_outcome()
    candidate_outcomes = {
        candidate["outcome"]
        for candidate in cast(list[dict[str, Any]], payload["candidates"])
        if isinstance(candidate.get("outcome"), str)
    }
    if candidate_outcomes - {outcome.outcome_id}:
        raise SystemExit(
            f"candidate(s) target outcome(s) {sorted(candidate_outcomes)}, expected only "
            f"{outcome.outcome_id!r} — refusing to rank a mixed-outcome candidate set"
        )

    frame = load_analytical_frame(args.dataset_root)
    signals = build_candidate_signals(payload, frame, outcome)
    ranked = rank_candidates(signals, DEFAULT_WEIGHTS)
    ranked_by_id = {candidate.candidate_id: candidate for candidate in ranked}

    candidates_out: list[dict[str, Any]] = []
    for candidate in cast(list[dict[str, Any]], payload["candidates"]):
        ranked_candidate = ranked_by_id[candidate["candidate_id"]]
        candidates_out.append(
            {
                **ranked_candidate.to_dict(),
                "conditions": candidate["conditions"],
                "description": candidate.get("description"),
                "economic_exposure": candidate["economic_exposure"],
                "support": candidate["support"],
                "raw_effect": candidate["raw_effect"],
                "sample_size": candidate["sample_size"],
                "warnings": candidate.get("warnings", []),
            }
        )
    candidates_out.sort(key=lambda item: cast(int, item["rank"]))

    def _display_path(path: Path) -> str:
        resolved = path.resolve()
        try:
            return str(resolved.relative_to(REPOSITORY))
        except ValueError:
            return str(resolved)

    output_payload = {
        "status": "FROZEN",
        "frozen_at": datetime.now(UTC).isoformat(),
        "ranking_method_version": RANKING_METHOD_VERSION,
        "weights": asdict(DEFAULT_WEIGHTS),
        "weights_provenance": WEIGHTS_PROVENANCE,
        "candidates_source": _display_path(args.candidates),
        "dataset_root": _display_path(args.dataset_root),
        "run_id": payload.get("run_id"),
        "blind_bundle_id": payload.get("blind_bundle_id"),
        "outcome_contract_version": OUTCOME_CONTRACT_VERSION,
        "candidate_count": len(candidates_out),
        "hidden_ground_truth_opened": False,
        "candidates": candidates_out,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {args.output}")
    for candidate in candidates_out:
        print(
            f"  #{candidate['rank']} {candidate['candidate_id']}: "
            f"score={candidate['rank_score']:.3f} "
            f"stability_missing={candidate['stability_missing']}"
        )


if __name__ == "__main__":
    main()
