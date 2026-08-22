"""Build public temporal split artifacts for one registered domain analytical dataset."""

import argparse
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.domain_benchmarks.analytical_bridge import (  # noqa: E402
    temporal_split_config,
)
from policy_analytics.domain_benchmarks.registry import DOMAIN_REGISTRY  # noqa: E402
from policy_analytics.temporal_splits import build_temporal_split_manifest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, choices=sorted(DOMAIN_REGISTRY))
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        default=REPOSITORY / "synthetic_data_domains",
    )
    args = parser.parse_args()
    spec = DOMAIN_REGISTRY[args.domain]
    dataset_root = (
        args.benchmark_root / args.domain / "analytical" / f"{args.domain}-analytical-v1.0.0"
    )
    if not (dataset_root / "manifest.json").is_file():
        raise SystemExit(f"analytical dataset does not exist: {dataset_root}")
    manifest = build_temporal_split_manifest(dataset_root, temporal_split_config(spec))
    print(f"Built {manifest['split_config_version']} for {manifest['analytical_dataset_version']}")


if __name__ == "__main__":
    main()
