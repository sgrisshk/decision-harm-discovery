"""Generate the TASK-003 synthetic benchmark."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/analytics/src"))

from policy_analytics.synthetic_benchmark import BenchmarkConfig, generate_benchmark

OUTPUT = Path("synthetic_data")


def main() -> None:
    checksums = generate_benchmark(OUTPUT, BenchmarkConfig())
    print(f"Generated {len(checksums)} benchmark artifacts under {OUTPUT}")


if __name__ == "__main__":
    main()
