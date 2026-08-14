"""Evaluator-only command that signs a received blind candidate artifact."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.blind_isolation import commit_candidates, read_evaluator_key  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path)
    parser.add_argument("--manifest", type=Path, required=True, help="Issued BLIND_MANIFEST.json")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path(tempfile.gettempdir()) / "policy-blind-evaluator/signing.key",
    )
    args = parser.parse_args()
    receipt = commit_candidates(
        args.candidates, args.manifest, args.receipt, read_evaluator_key(args.key_file)
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
