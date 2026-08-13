"""Create an allowlist-only workspace for the ML Discovery actor."""

import argparse
import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))

from policy_analytics.blind_isolation import prepare_blind_workspace  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path, help="New directory outside this repository")
    args = parser.parse_args()
    manifest = prepare_blind_workspace(REPOSITORY, args.destination)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
