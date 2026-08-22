# Analytical benchmark datasets

`travel-bookings-analytical-v1.1.0/` is the current dataset generated with
`make analytical-dataset`. The immutable `v1.0.0/` remains for reproducibility of frozen runs.

Version 1.1.0 adds `travel_month` to `features.csv`. It is the Gregorian month (1–12)
deterministically extracted from decision-known `travel_date`; invalid or missing source dates
fail the build. Its decision-time classification and complete transform lineage are recorded in
`feature_manifest.json`, `version_metadata.json`, and `manifest.json`.

ML Discovery may consume `features.csv`, `identifiers.csv`, `metadata.csv`, and `outcomes.csv`
only through the attached Statistics-owned TASK-013 outcome contract v1.1.0. Discovery does not
select, redefine, or reweight outcomes.

The directory also contains standalone feature, outcome-column, excluded-column, and version
manifests. `manifest.json` is the aggregate entrypoint.

`make temporal-splits` produces `split_manifest.json` and row-level `split_membership.csv`. Only
`development` rows may fit/select/rank conditions; `validation` and `future_holdout` are
diagnostic-only during discovery.

All four CSV partitions preserve identical row ordering. `source_row_number` in `metadata.csv`
links a row back to the clean reference, while identifiers remain physically separate from
features. Post-decision fields are not copied into any partition.
