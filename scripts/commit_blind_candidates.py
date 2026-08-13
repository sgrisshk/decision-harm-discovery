"""Evaluator-only command that signs a received blind candidate artifact."""

import argparse
import json
import os
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))

from policy_analytics.blind_isolation import commit_candidates  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path)
    parser.add_argument("--manifest", type=Path, required=True, help="Issued BLIND_MANIFEST.json")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ.get("BLIND_EVALUATION_KEY")
    if key is None:
        raise SystemExit("BLIND_EVALUATION_KEY is required")
    receipt = commit_candidates(args.candidates, args.manifest, args.receipt, key.encode("utf-8"))
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
