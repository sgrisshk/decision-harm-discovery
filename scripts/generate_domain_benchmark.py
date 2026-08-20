"""Generate a TASK-061 multi-domain benchmark variant.

Never writes to synthetic_data/ (the TASK-003 travel benchmark) — always under
synthetic_data_domains/<domain>/<variant>/, independent and gitignored-free (these are meant to be
committed, unlike the throwaway TASK-004 difficulty-preset runs).
"""

import argparse
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.domain_benchmarks.common import (  # noqa: E402
    Variant,
    run_domain_benchmark,
    standard_variant_config,
)
from policy_analytics.domain_benchmarks.registry import DOMAIN_REGISTRY  # noqa: E402

DEFAULT_OUTPUT_ROOT = REPOSITORY / "synthetic_data_domains"
DEFAULT_SEED = 20260818
DEFAULT_ROW_COUNT = 10_000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, choices=sorted(DOMAIN_REGISTRY))
    parser.add_argument(
        "--variant",
        required=True,
        choices=["noise", "traps_only", "dominant_weak", "comparable"],
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--row-count", type=int, default=DEFAULT_ROW_COUNT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    spec = DOMAIN_REGISTRY[args.domain]
    variant: Variant = args.variant
    config = standard_variant_config(spec, variant, seed=args.seed, row_count=args.row_count)
    output = args.output or (DEFAULT_OUTPUT_ROOT / args.domain / args.variant)

    checksums = run_domain_benchmark(spec, config, output)
    print(f"Generated {len(checksums)} public artifacts under {output} ({args.domain}/{variant})")


if __name__ == "__main__":
    main()
