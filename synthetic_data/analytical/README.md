# Analytical benchmark datasets

`travel-bookings-analytical-v1.0.0/` is generated with `make analytical-dataset`.

ML Discovery may consume `features.csv`, `identifiers.csv`, and `metadata.csv`. It must not select
an outcome from `outcomes.csv` until Statistics attaches the versioned TASK-013 contract. The
manifest deliberately records `primary_outcome: null` while that contract is pending.

All four CSV partitions preserve identical row ordering. `source_row_number` in `metadata.csv`
links a row back to the clean reference, while identifiers remain physically separate from
features. Post-decision fields are not copied into any partition.
