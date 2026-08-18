"""Generate the TASK-003 synthetic benchmark, optionally at a TASK-004 difficulty preset."""

import argparse
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.synthetic_benchmark import (  # noqa: E402
    ROW_COUNT,
    SEED,
    Difficulty,
    difficulty_config,
    generate_benchmark,
)

DEFAULT_OUTPUT = Path("synthetic_data")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--difficulty",
        type=Difficulty,
        choices=list(Difficulty),
        default=Difficulty.MEDIUM,
        help=(
            "Difficulty preset (TASK-004). MEDIUM (default) is byte-identical to the frozen "
            "benchmark and writes to synthetic_data/, exactly as before this flag existed."
        ),
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--row-count", type=int, default=ROW_COUNT)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output directory. Defaults to synthetic_data/ for MEDIUM (the canonical, frozen "
            "benchmark location) and synthetic_data_presets/<difficulty>/ for any other "
            "difficulty, so a preset run can never overwrite the frozen artifact by accident."
        ),
    )
    args = parser.parse_args()

    output = args.output
    if output is None:
        output = (
            DEFAULT_OUTPUT
            if args.difficulty is Difficulty.MEDIUM
            else Path(f"synthetic_data_presets/{args.difficulty.value}")
        )

    config = difficulty_config(args.difficulty, seed=args.seed, row_count=args.row_count)
    checksums = generate_benchmark(output, config)
    print(
        f"Generated {len(checksums)} benchmark artifacts under {output} ({args.difficulty.value})"
    )


if __name__ == "__main__":
    main()
