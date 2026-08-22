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
    # TASK-011 v1.1.0 is an additive, versioned successor. v1.0.0 remains tracked because frozen
    # benchmark runs reference it and must remain reproducible.
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/features.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/outcomes.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/identifiers.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/metadata.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/split_membership.csv",
    # TASK-061/TASK-062: six-domain generalization benchmark suite, all synthetic,
    # generated deterministically by policy_analytics.domain_benchmarks -- same public,
    # non-customer status as the travel-benchmark files above.
    "synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0/features.csv",
    "synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0/identifiers.csv",
    "synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0/metadata.csv",
    "synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0/outcomes.csv",
    "synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0/split_membership.csv",
    "synthetic_data_domains/b2b_sales/comparable/raw/b2b_sales_dirty.csv",
    "synthetic_data_domains/b2b_sales/comparable/reference/b2b_sales_clean.csv",
    "synthetic_data_domains/b2b_sales/dominant_weak/raw/b2b_sales_dirty.csv",
    "synthetic_data_domains/b2b_sales/dominant_weak/reference/b2b_sales_clean.csv",
    "synthetic_data_domains/b2b_sales/noise/raw/b2b_sales_dirty.csv",
    "synthetic_data_domains/b2b_sales/noise/reference/b2b_sales_clean.csv",
    "synthetic_data_domains/b2b_sales/traps_only/raw/b2b_sales_dirty.csv",
    "synthetic_data_domains/b2b_sales/traps_only/reference/b2b_sales_clean.csv",
    "synthetic_data_domains/ecommerce/analytical/ecommerce-analytical-v1.0.0/features.csv",
    "synthetic_data_domains/ecommerce/analytical/ecommerce-analytical-v1.0.0/identifiers.csv",
    "synthetic_data_domains/ecommerce/analytical/ecommerce-analytical-v1.0.0/metadata.csv",
    "synthetic_data_domains/ecommerce/analytical/ecommerce-analytical-v1.0.0/outcomes.csv",
    "synthetic_data_domains/ecommerce/comparable/raw/ecommerce_dirty.csv",
    "synthetic_data_domains/ecommerce/comparable/reference/ecommerce_clean.csv",
    "synthetic_data_domains/ecommerce/dominant_weak/raw/ecommerce_dirty.csv",
    "synthetic_data_domains/ecommerce/dominant_weak/reference/ecommerce_clean.csv",
    "synthetic_data_domains/ecommerce/noise/raw/ecommerce_dirty.csv",
    "synthetic_data_domains/ecommerce/noise/reference/ecommerce_clean.csv",
    "synthetic_data_domains/ecommerce/traps_only/raw/ecommerce_dirty.csv",
    "synthetic_data_domains/ecommerce/traps_only/reference/ecommerce_clean.csv",
    "synthetic_data_domains/healthcare/analytical/healthcare-analytical-v1.0.0/features.csv",
    "synthetic_data_domains/healthcare/analytical/healthcare-analytical-v1.0.0/identifiers.csv",
    "synthetic_data_domains/healthcare/analytical/healthcare-analytical-v1.0.0/metadata.csv",
    "synthetic_data_domains/healthcare/analytical/healthcare-analytical-v1.0.0/outcomes.csv",
    "synthetic_data_domains/healthcare/comparable/raw/healthcare_dirty.csv",
    "synthetic_data_domains/healthcare/comparable/reference/healthcare_clean.csv",
    "synthetic_data_domains/healthcare/dominant_weak/raw/healthcare_dirty.csv",
    "synthetic_data_domains/healthcare/dominant_weak/reference/healthcare_clean.csv",
    "synthetic_data_domains/healthcare/noise/raw/healthcare_dirty.csv",
    "synthetic_data_domains/healthcare/noise/reference/healthcare_clean.csv",
    "synthetic_data_domains/healthcare/traps_only/raw/healthcare_dirty.csv",
    "synthetic_data_domains/healthcare/traps_only/reference/healthcare_clean.csv",
    "synthetic_data_domains/insurance/analytical/insurance-analytical-v1.0.0/features.csv",
    "synthetic_data_domains/insurance/analytical/insurance-analytical-v1.0.0/identifiers.csv",
    "synthetic_data_domains/insurance/analytical/insurance-analytical-v1.0.0/metadata.csv",
    "synthetic_data_domains/insurance/analytical/insurance-analytical-v1.0.0/outcomes.csv",
    "synthetic_data_domains/insurance/comparable/raw/insurance_dirty.csv",
    "synthetic_data_domains/insurance/comparable/reference/insurance_clean.csv",
    "synthetic_data_domains/insurance/dominant_weak/raw/insurance_dirty.csv",
    "synthetic_data_domains/insurance/dominant_weak/reference/insurance_clean.csv",
    "synthetic_data_domains/insurance/noise/raw/insurance_dirty.csv",
    "synthetic_data_domains/insurance/noise/reference/insurance_clean.csv",
    "synthetic_data_domains/insurance/traps_only/raw/insurance_dirty.csv",
    "synthetic_data_domains/insurance/traps_only/reference/insurance_clean.csv",
    "synthetic_data_domains/manufacturing/analytical/manufacturing-analytical-v1.0.0/features.csv",
    "synthetic_data_domains/manufacturing/analytical/manufacturing-analytical-v1.0.0/identifiers.csv",
    "synthetic_data_domains/manufacturing/analytical/manufacturing-analytical-v1.0.0/metadata.csv",
    "synthetic_data_domains/manufacturing/analytical/manufacturing-analytical-v1.0.0/outcomes.csv",
    "synthetic_data_domains/manufacturing/comparable/raw/manufacturing_dirty.csv",
    "synthetic_data_domains/manufacturing/comparable/reference/manufacturing_clean.csv",
    "synthetic_data_domains/manufacturing/dominant_weak/raw/manufacturing_dirty.csv",
    "synthetic_data_domains/manufacturing/dominant_weak/reference/manufacturing_clean.csv",
    "synthetic_data_domains/manufacturing/noise/raw/manufacturing_dirty.csv",
    "synthetic_data_domains/manufacturing/noise/reference/manufacturing_clean.csv",
    "synthetic_data_domains/manufacturing/traps_only/raw/manufacturing_dirty.csv",
    "synthetic_data_domains/manufacturing/traps_only/reference/manufacturing_clean.csv",
    "synthetic_data_domains/saas/analytical/saas-analytical-v1.0.0/features.csv",
    "synthetic_data_domains/saas/analytical/saas-analytical-v1.0.0/identifiers.csv",
    "synthetic_data_domains/saas/analytical/saas-analytical-v1.0.0/metadata.csv",
    "synthetic_data_domains/saas/analytical/saas-analytical-v1.0.0/outcomes.csv",
    "synthetic_data_domains/saas/comparable/raw/saas_dirty.csv",
    "synthetic_data_domains/saas/comparable/reference/saas_clean.csv",
    "synthetic_data_domains/saas/dominant_weak/raw/saas_dirty.csv",
    "synthetic_data_domains/saas/dominant_weak/reference/saas_clean.csv",
    "synthetic_data_domains/saas/noise/raw/saas_dirty.csv",
    "synthetic_data_domains/saas/noise/reference/saas_clean.csv",
    "synthetic_data_domains/saas/traps_only/raw/saas_dirty.csv",
    "synthetic_data_domains/saas/traps_only/reference/saas_clean.csv",
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
