# Analytical benchmark datasets

`travel-bookings-analytical-v1.0.0/` is generated with `make analytical-dataset`.

ML Discovery may consume `features.csv`, `identifiers.csv`, `metadata.csv`, and `outcomes.csv`
only through the attached Statistics-owned TASK-013 outcome contract v1.0.0. Discovery does not
select, redefine, or reweight outcomes.

The directory also contains standalone feature, outcome-column, excluded-column, and version
manifests. `manifest.json` is the aggregate entrypoint.

`make temporal-splits` produces `split_manifest.json` and row-level `split_membership.csv`. Only
`development` rows may fit/select/rank conditions; `validation` and `future_holdout` are
diagnostic-only during discovery.

All four CSV partitions preserve identical row ordering. `source_row_number` in `metadata.csv`
links a row back to the clean reference, while identifiers remain physically separate from
features. Post-decision fields are not copied into any partition.
