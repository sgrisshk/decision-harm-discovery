"""Fail CI when an unapproved data artifact is tracked by Git."""

from __future__ import annotations

import subprocess
from pathlib import Path

DATA_SUFFIXES = {".csv", ".xlsx", ".xls", ".parquet", ".db", ".sqlite"}
ALLOWED_DATA_FILES = {
    "tests/fixtures/synthetic_travel_bookings.csv",
    "synthetic_data/raw/travel_bookings_dirty.csv",
    "synthetic_data/reference/travel_bookings_clean.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/features.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/outcomes.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/identifiers.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/metadata.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/split_membership.csv",
}


def tracked_files() -> set[str]:
    result = subprocess.run(["git", "ls-files"], check=True, capture_output=True, text=True)
    return {line for line in result.stdout.splitlines() if line}


def main() -> None:
    tracked_data = {path for path in tracked_files() if Path(path).suffix.lower() in DATA_SUFFIXES}
    unexpected = sorted(tracked_data - ALLOWED_DATA_FILES)
    missing = sorted(ALLOWED_DATA_FILES - tracked_data)
    if unexpected or missing:
        raise SystemExit(
            f"repository data allowlist mismatch: unexpected={unexpected}, missing={missing}"
        )
    print(f"Repository data allowlist verified ({len(tracked_data)} tracked artifacts).")


if __name__ == "__main__":
    main()
