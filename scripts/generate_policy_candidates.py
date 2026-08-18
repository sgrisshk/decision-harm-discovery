"""CLI: generate Policy Candidates from validated Findings (`TASK-031`).

Implements `docs/product/policy-candidate-domain-model.md` §12's generation procedure — a thin
argparse/session wrapper around `app.policies.generation.generate_policy_candidates`, which does
all the real work (delegating eligibility/idempotency/guardrails to
`app.policies.service.create_draft_policy_candidate`, `TASK-030`, `ADR-029`). Manually triggered,
matching every other batch operation in this codebase (`scripts/promote_findings.py`,
`scripts/run_backtest.py`) — nothing runs this automatically.

Usage:
  uv run python scripts/generate_policy_candidates.py                # batch: every ACTIVE Finding
  uv run python scripts/generate_policy_candidates.py --finding-id UUID
  # --force creates an explicit additional candidate for one Finding (§6/§12):
  uv run python scripts/generate_policy_candidates.py --finding-id UUID --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "apps/api"))
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from app.db.session import SessionLocal  # noqa: E402
from app.policies.generation import generate_policy_candidates  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Policy Candidates from currently-eligible Findings."
    )
    parser.add_argument(
        "--finding-id",
        type=UUID,
        default=None,
        help="generate for exactly this Finding instead of every ACTIVE one",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="create an explicit additional candidate even if one already exists "
        "(requires --finding-id — never allowed in batch mode, §6/§12)",
    )
    args = parser.parse_args()
    if args.force and args.finding_id is None:
        parser.error("--force requires --finding-id (never allowed in batch mode)")
    return args


def main() -> None:
    args = parse_args()
    finding_ids = (args.finding_id,) if args.finding_id is not None else None

    session = SessionLocal()
    try:
        report = generate_policy_candidates(session, finding_ids=finding_ids, force=args.force)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    for candidate_id in report.created:
        print(f"created {candidate_id}")
    for skip in report.skipped:
        print(f"skipped {skip.finding_id}: {skip.reason}")
    print(f"{len(report.created)} created, {len(report.skipped)} skipped")


if __name__ == "__main__":
    main()
