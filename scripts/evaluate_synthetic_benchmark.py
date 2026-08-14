"""Open hidden ground truth only after discovery candidates are persisted."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.blind_isolation import read_evaluator_key  # noqa: E402
from policy_analytics.synthetic_benchmark import evaluate_persisted_candidates  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path, help="Persisted candidate JSON")
    parser.add_argument(
        "--ground-truth",
        type=Path,
        required=True,
        help="Explicit restricted hidden_ground_truth.json path",
    )
    parser.add_argument("--receipt", type=Path, required=True, help="Signed commitment receipt")
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path(tempfile.gettempdir()) / "policy-blind-evaluator/signing.key",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            evaluate_persisted_candidates(
                args.candidates,
                args.ground_truth,
                args.receipt,
                read_evaluator_key(args.key_file),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
