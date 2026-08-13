"""Build TASK-012 temporal split artifacts for the approved analytical dataset."""

import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.analytical_dataset import DATASET_VERSION  # noqa: E402
from policy_analytics.temporal_splits import build_temporal_split_manifest  # noqa: E402


def main() -> None:
    root = Path("synthetic_data/analytical") / DATASET_VERSION
    manifest = build_temporal_split_manifest(root)
    print(f"Built {manifest['split_config_version']} for {manifest['analytical_dataset_version']}")


if __name__ == "__main__":
    main()
