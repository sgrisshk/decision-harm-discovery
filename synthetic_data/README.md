# Synthetic travel benchmark

Generate the complete deterministic benchmark with `make benchmark`. The full checkout is trusted
coordinator/evaluator scope and must never be assigned to the ML Discovery actor.

- `raw/` contains the intentionally dirty customer-export analogue.
- `reference/` contains the clean reference CSV used to verify ingestion and normalization.
- `metadata/` contains generation, corruption, schema, timing, split, and checksum manifests.
- `analytical/travel-bookings-analytical-v1.0.0/` contains the leakage-safe TASK-011
  feature/outcome/identifier/metadata partitions and their lineage manifest.
- `evaluation/` is restricted hidden ground truth. The generator implementation also necessarily
  encodes the simulation mechanisms. ML Discovery must not read or receive either `evaluation/` or
  `packages/analytics/src/policy_analytics/synthetic_benchmark.py` until its candidate artifact has
  been persisted; it consumes only the generated public inputs.

Blind discovery is run from a fresh allowlist-only workspace; see
`docs/blind_benchmark_protocol.md`. The evaluator fails closed unless the exact candidate bytes
match an evaluator-signed commitment receipt:

```sh
uv run python scripts/evaluate_synthetic_benchmark.py candidates.json \
  --receipt artifacts/blind/run-001.receipt.json \
  --ground-truth synthetic_data/evaluation/hidden_ground_truth.json
```

No file in this directory contains customer data.
