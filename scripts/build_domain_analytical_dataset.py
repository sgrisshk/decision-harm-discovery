"""Build a TASK-061 domain's analytical dataset via the generic analytical_bridge.

Mirrors `scripts/build_synthetic_analytical_dataset.py`'s shape for the travel benchmark, but reads
one already-registered `TASK-061` domain's raw benchmark variant
(`synthetic_data_domains/<domain>/<variant>/`, from `scripts/generate_domain_benchmark.py`) and
writes to `synthetic_data_domains/<domain>/analytical/` instead of `synthetic_data/analytical/` —
never touches the travel path. No per-domain code: `AnalyticalDatasetConfig`/`OutcomeContractInputs`
are both derived from the domain's own registered `DomainSpec` by
`policy_analytics.domain_benchmarks.analytical_bridge`.

Defaults to the `comparable` variant (every pattern and trap active, unscaled) as the single
richest-signal source per domain — the same role the one canonical `synthetic_benchmark.py` run
plays for travel.
"""

import argparse
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.analytical_dataset import build_analytical_dataset  # noqa: E402
from policy_analytics.domain_benchmarks.analytical_bridge import (  # noqa: E402
    analytical_dataset_config,
    provisional_outcome_contract,
    temporal_split_config,
)
from policy_analytics.domain_benchmarks.registry import DOMAIN_REGISTRY  # noqa: E402
from policy_analytics.temporal_splits import build_temporal_split_manifest  # noqa: E402

DEFAULT_BENCHMARK_ROOT = REPOSITORY / "synthetic_data_domains"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, choices=sorted(DOMAIN_REGISTRY))
    parser.add_argument(
        "--variant",
        default="comparable",
        choices=["noise", "traps_only", "dominant_weak", "comparable"],
        help="which already-generated raw benchmark variant to build the analytical dataset from",
    )
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    spec = DOMAIN_REGISTRY[args.domain]
    variant_root = args.benchmark_root / args.domain / args.variant
    source_csv = variant_root / "reference" / f"{args.domain}_clean.csv"
    feature_timing_path = variant_root / "metadata" / "feature_timing.json"
    if not source_csv.exists():
        raise SystemExit(
            f"{source_csv} does not exist — run scripts/generate_domain_benchmark.py "
            f"--domain {args.domain} --variant {args.variant} first"
        )

    output_root = args.output or (args.benchmark_root / args.domain / "analytical")
    config = analytical_dataset_config(spec)
    outcome_contract = provisional_outcome_contract(spec)

    manifest = build_analytical_dataset(
        source_csv, feature_timing_path, output_root, config, outcome_contract
    )
    dataset_root = output_root / str(manifest["dataset_version"])
    split_manifest = build_temporal_split_manifest(dataset_root, temporal_split_config(spec))
    print(
        f"Built {manifest['dataset_version']} ({manifest['dataset_identity_sha256'][:12]}) "
        f"under {output_root} from {args.domain}/{args.variant}; "
        f"split={split_manifest['split_config_version']}"
    )


if __name__ == "__main__":
    main()
