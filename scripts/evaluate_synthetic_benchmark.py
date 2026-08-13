"""Open hidden ground truth only after discovery candidates are persisted."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/analytics/src"))

from policy_analytics.synthetic_benchmark import evaluate_persisted_candidates


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
    args = parser.parse_args()
    key = os.environ.get("BLIND_EVALUATION_KEY")
    if key is None:
        raise SystemExit("BLIND_EVALUATION_KEY is required")
    print(
        json.dumps(
            evaluate_persisted_candidates(
                args.candidates, args.ground_truth, args.receipt, key.encode("utf-8")
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
