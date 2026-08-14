"""Create an allowlist-only workspace for the ML Discovery actor."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.blind_isolation import (  # noqa: E402
    prepare_blind_workspace,
    read_evaluator_key,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path, help="New directory outside this repository")
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path(tempfile.gettempdir()) / "policy-blind-evaluator/signing.key",
    )
    args = parser.parse_args()
    manifest = prepare_blind_workspace(
        REPOSITORY, args.destination, read_evaluator_key(args.key_file)
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
