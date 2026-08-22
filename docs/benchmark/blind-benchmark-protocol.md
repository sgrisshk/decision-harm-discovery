# Blind synthetic benchmark protocol

## Problem

The repository contains both public benchmark inputs and restricted artifacts. A directory name,
CLI flag, or caller-supplied `status=PERSISTED` cannot prove that ML Discovery was blind or that its
candidates existed before hidden truth was opened.

## Current architecture

The full trusted checkout contains the generator, corruption manifest, hidden ground truth, and
evaluator. Generated public inputs and restricted files currently share that checkout.

## Proposed change

Use two execution identities and two workspaces:

1. A trusted coordinator creates a fresh blind workspace from a registry-backed file allowlist.
2. ML Discovery receives only that workspace. It does not receive the full checkout, evaluator
   signing key, generator implementation, corruption manifest, hidden truth, or evaluation code.
3. Discovery returns a candidate JSON containing the workspace `bundle_id`.
4. An evaluation actor accepts the bytes once and produces an HMAC-signed commitment receipt.
5. Post-hoc evaluation verifies both the receipt signature and candidate SHA-256 before opening
   hidden truth.

The workspace manifest hashes every supplied file. Workspace validation rejects additions,
deletions, modifications, symlinks, and known restricted filenames.

## Why

This is the smallest credible identity and commitment boundary. It uses filesystem workspaces,
SHA-256, HMAC, and role separation already available on developer machines and CI runners. The
receipt replaces unverifiable candidate metadata with evaluator-controlled evidence that exact
candidate bytes were committed.

## Alternatives considered

- Directory naming and documentation: not an access boundary.
- Candidate `status` and timestamp: controlled by Discovery and therefore not trusted.
- PostgreSQL audit tables: unnecessary before the discovery pipeline exists and still require an
  identity boundary.
- Separate repository, object store, or CI environment: stronger operational packaging, but more
  infrastructure than the MVP requires. The same allowlist bundle and signed receipt can later be
  transported through those systems unchanged.

## Dependency impact

No new dependency. The implementation uses the Python standard library.

## Migration impact

None. No database schema changes.

## Security impact

The boundary is valid only if Discovery is launched as a separate actor whose filesystem scope is
the blind workspace. Giving that actor the full checkout, the signing key, shell access to the
evaluation identity, or a previously contaminated conversation invalidates the run. HMAC is used
for provenance and commitment, not encryption. Hidden truth remains in the trusted checkout.

The public payload is limited to the versioned analytical partitions (`features`, `outcomes`,
`identifiers`, and `metadata`), TASK-012's `split_manifest.json` and `split_membership.csv`, plus
four generated, sanitized files under `public/`: schema, feature timing, approved outcome
metadata, and run configuration. Split membership exposes only booking ID/date, split label, and
the closed-benchmark outcome-finality flag. It contains no Python source.
`generation_config.json`, `corruption_manifest.json`, full lineage/missingness manifests,
raw/reference exports, private checksums, generator source, evaluator source, and all
`evaluation/` files are absent. Outcome metadata is serialized from the Statistics-approved
TASK-013 contract; the exporter does not invent or modify it.

## Rollback

Remove the blind-isolation scripts/module and return to the old evaluator signature. Existing
benchmark data and database state are unaffected. Previously signed receipts remain plain JSON
audit artifacts but would no longer be accepted by the reverted evaluator.

## Files affected

- `packages/analytics/src/policy_analytics/blind_isolation.py`
- `packages/analytics/src/policy_analytics/synthetic_benchmark.py`
- `scripts/prepare_blind_workspace.py`
- `scripts/commit_blind_candidates.py`
- `scripts/evaluate_synthetic_benchmark.py`
- `tests/analytics/test_synthetic_benchmark.py`
- `synthetic_data/README.md`

## Run blind discovery

One coordinator command rebuilds the benchmark and analytical dataset, then exports the public
artifact. It runs from the trusted full checkout; the destination must be new and outside the
repository:

```sh
make blind-key-init RUN=run-001
make blind-image
make blind-rehearsal BLIND_DATASET=travel
make blind-issue RUN=run-001 BLIND_DATASET=travel
make blind-verify RUN=run-001 BLIND_DATASET=travel
```

Start ML Discovery as a separate OS/container identity with
`/tmp/policy-blind-runs/run-001/workspace` as its only mounted workspace. Merely changing the working directory in
the full checkout is not isolation and invalidates the run. Do not fork a context that has seen
restricted files. The coordinator signature in `BLIND_MANIFEST.json` authenticates the issued
allowlist, output acceptance contract, and immutable runtime digest. Verification/launch also
compare the current allowlist and source hashes to the issued snapshot; any drift requires a new
run ID. Candidate commitment rejects unsigned, forged, incomplete, or modified manifests.

The required `BLIND_DATASET` value is a reviewed key in `blind/allowlist.yaml`, never an arbitrary
path. Each key pins one versioned analytical root. Issuance derives the fixed six public partition
paths from that root and signs the selector, root, acceptance fields, and copied-file hashes.
Verification and launch require the same selector. Unknown keys, absent analytical/split manifests,
missing partitions, selector drift, analytical/split identity or version mismatch, and declared
partition/membership hash mismatch are terminal errors. This permits a preregistered domain to
reuse the isolation mechanism without copying any other registered domain into its workspace.

The repository provides a fail-closed container boundary for interactive execution:

```sh
make blind-shell RUN=run-001 BLIND_DATASET=travel
```

The coordinator owns `/tmp/policy-blind-evaluator/signing.key` (mode `0600`) and invokes the
launcher after signature verification. The key path and bytes are not mounted or passed as an
environment variable. The signed manifest fixes the deterministic actor, null provider model,
and immutable image; launch fails if any drift. The launcher mounts only the issued workspace,
uses a read-only root, drops all capabilities, sets `no-new-privileges`, and always disables
network. It passes no provider credential. The hard paid-usage ceiling is zero requests, zero
tokens, and zero cost.

Issuance requires `blind-rehearsal` against the same digest. Rehearsal creates a temporary signed
truth-free workspace, executes the real allowlisted engine, writes all three schema-v1.1.0
outputs, and passes normal freeze validation. It does not allocate an official run ID or open
hidden truth.
The ML Discovery process/agent must be started inside that boundary; an agent already running in
the repository cannot be made blind retroactively.

Discovery writes schema v1.1.0 outputs defined in `tools/blind_agent/models.py`. The signed
`BLIND_MANIFEST.json.acceptance_contract` supplies exact expected values. In particular,
`candidates.json` binds:

```json
{
  "schema_version": "1.1.0",
  "status": "PERSISTED",
  "blind_bundle_id": "<BLIND_MANIFEST.json bundle_id>",
  "dataset_identity_sha256": "<signed dataset identity>",
  "input_provenance_hashes": {"<allowlisted path>": "<sha256>"},
  "selection_used_only_fit_split": true,
  "candidates": ["10-20 typed candidates"]
}
```

Fewer than 10 candidates are accepted only with `status=INSUFFICIENT_CANDIDATES` and a non-empty
reason. Freeze rejects contract/version/provenance drift, non-`DECISION_TIME` condition features,
unapproved outcomes/methods, incorrect split declarations, and prohibited causal language.

Discovery freezes all three required outputs. Only frozen `candidates.json` crosses into the
separate evaluation process; no later message or evaluation file returns to the blind workspace.

## Run separate post-hoc evaluation

Use a separate evaluation actor in the trusted checkout. Generate and retain the key outside the
blind workspace; do not commit it:

```sh
uv run python scripts/commit_blind_candidates.py /path/to/candidates.json \
  --manifest /path/to/issued/BLIND_MANIFEST.json \
  --receipt artifacts/blind/run-001.receipt.json \
  --key-file /tmp/policy-blind-evaluator/signing.key
uv run python scripts/evaluate_synthetic_benchmark.py /path/to/candidates.json \
  --receipt artifacts/blind/run-001.receipt.json \
  --ground-truth synthetic_data/evaluation/hidden_ground_truth.json \
  --key-file /tmp/policy-blind-evaluator/signing.key
```

The commitment command accepts only a `PERSISTED` envelope tied to the issued blind manifest and
refuses to overwrite a receipt.
That status remains useful workflow metadata but is not trusted as proof: the signed receipt is the
commitment. Evaluation fails if the receipt is absent, forged, signed with another key, tied to
another bundle, or if a single candidate byte changed.
Archive the candidate file, receipt, evaluation output, and key in evaluator-controlled storage;
the key must remain unavailable to Discovery.
