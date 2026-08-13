"""Build the versioned leakage-safe analytical dataset from the clean benchmark."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/analytics/src"))

from policy_analytics.analytical_dataset import build_analytical_dataset


def main() -> None:
    manifest = build_analytical_dataset(
        Path("synthetic_data/reference/travel_bookings_clean.csv"),
        Path("synthetic_data/metadata/feature_timing.json"),
        Path("synthetic_data/analytical"),
    )
    print(f"Built {manifest['dataset_version']} ({manifest['dataset_identity_sha256'][:12]})")


if __name__ == "__main__":
    main()
