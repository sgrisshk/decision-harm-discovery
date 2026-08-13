"""Build the versioned leakage-safe analytical dataset from the clean benchmark."""

import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.analytical_dataset import build_analytical_dataset  # noqa: E402

DERIVED_DATASET_FILES = {Path("split_manifest.json"), Path("split_membership.csv")}


def main() -> None:
    output_root = Path("synthetic_data/analytical")
    with tempfile.TemporaryDirectory(prefix="analytical-build-") as temporary:
        temporary_root = Path(temporary)
        manifest = build_analytical_dataset(
            Path("synthetic_data/reference/travel_bookings_clean.csv"),
            Path("synthetic_data/metadata/feature_timing.json"),
            temporary_root,
        )
        generated = temporary_root / str(manifest["dataset_version"])
        destination = output_root / str(manifest["dataset_version"])
        if destination.exists():
            generated_files = {
                path.relative_to(generated): path.read_bytes()
                for path in generated.rglob("*")
                if path.is_file()
            }
            existing_files = {
                path.relative_to(destination): path.read_bytes()
                for path in destination.rglob("*")
                if path.is_file() and path.relative_to(destination) not in DERIVED_DATASET_FILES
            }
            if generated_files != existing_files:
                raise SystemExit(
                    f"immutable analytical version differs: {destination}; bump dataset_version"
                )
        else:
            output_root.mkdir(parents=True, exist_ok=True)
            generated.replace(destination)
    print(f"Built {manifest['dataset_version']} ({manifest['dataset_identity_sha256'][:12]})")


if __name__ == "__main__":
    main()
