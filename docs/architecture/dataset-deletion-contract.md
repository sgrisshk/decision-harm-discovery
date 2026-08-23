# Dataset deletion contract (TASK-055)

Implements `TASK-055` against the current synthetic/test-data ingestion pipeline
(`TASK-005`–`TASK-009`), per `ADR-058`'s resolution that the pre-customer-safe portion of
`TASK-037`/`TASK-055` is achievable, and required, without a real customer dataset already in
hand. See `ADR-060` for the decision record and `docs/security/task-037-pre-customer-review-prep.md`
for how this feeds `TASK-037`'s security review.

## What "delete" means here

Three shapes were considered for a request to delete a dataset:

1. **Pure tombstone** — hide the row, never touch bytes. Rejected as the sole mechanism: it does
   not remove anything, so it cannot satisfy an actual erasure request (a real customer asking
   "delete our data" almost certainly means the bytes, not just the list view).
2. **Retention-expiry sweep** — a background job that purges anything past a configured age.
   Rejected for this iteration: no async/worker infrastructure exists anywhere in this codebase
   (`PolicyBacktestRunModel`'s own precedent — everything here runs synchronously inside the
   request that needs it), and a sweep answers a different question ("how long do we keep
   things by default", currently "indefinitely", `docs/architecture/ingestion-contract.md`
   Retention section) than "delete this dataset now", which is what `TASK-055`'s goal text asks
   for.
3. **Immediate tombstone + immediate conditional byte purge** — chosen. `DELETE
   /api/v1/datasets/{id}` synchronously: marks the dataset row `deleted_at` (never removes it —
   see "Why the row survives" below), redacts literal-content derived fields, and physically
   unlinks the raw CSV unless another *active* dataset still references the same content hash.

Content-addressed storage (`TASK-005`/`TASK-006`) stores identical bytes once and lets multiple
dataset rows point at the same file (`store_immutable_csv`'s own dedup no-op). Unlinking on the
first delete request would silently corrupt every other dataset sharing that hash — so disposition
must be computed per request, not assumed: `delete_dataset` checks for another active row with the
same `checksum_sha256` before touching the filesystem, and records which branch it took on the
audit row (`raw_bytes_purged`, `raw_bytes_retained_reason`).

**Ordering guarantee:** the physical unlink happens *before* the database commit. If it raises
(anything other than "already gone", which `delete_immutable_csv` treats as success for
idempotency), the whole request fails and nothing commits — the dataset stays active with intact
bytes rather than ending up tombstoned with missing bytes. The one residual gap, disclosed rather
than engineered around (no outbox/2PC — `agents/ARCHITECT.md`'s bar for introducing that kind of
infrastructure is a demonstrated requirement, not a single delete path): if the unlink succeeds and
the subsequent commit then fails (e.g. the database connection drops in that instant), the dataset
row is left active while pointing at now-missing bytes. This is a narrow, rare double-failure
window, not a routine path.

## Why the row survives

Every downstream table (`analysis_runs`, `dataset_column_profiles`, and transitively
`candidate_patterns`, `validation_reports`, `findings`, `policy_candidates`) references `datasets`
with `ondelete="RESTRICT"`. This is already true today, for reasons unrelated to deletion (the
codebase's general append-only/immutable-snapshot convention — `CandidatePatternModel`,
`ValidationReportModel`, `FindingModel` are all explicitly immutable or snapshot-based). A literal
`DELETE FROM datasets` would fail with a foreign-key violation the moment any derived artifact
exists, which in practice is almost always. Rather than work around that with `ON DELETE CASCADE`
(which would silently destroy the very audit trail `TASK-037`'s goal text asks this review to
cover), deletion is a tombstone: `datasets.deleted_at` gates every read path
(`list_datasets`/`get_dataset` in `apps/api/app/datasets/service.py`), and a dataset once deleted
never resolves through the dataset API again — including by direct ID.

## What happens to already-derived artifacts

| Artifact | Contains literal source content? | Action on delete |
|---|---|---|
| Raw CSV bytes (content-addressed storage) | Yes — the entire file | Unlinked, unless dedup-shared with another active dataset (see above) |
| `dataset_column_profiles.examples` | Yes — literal values from the column (the schema profiler's own conservative, disclosed-heuristic PII floor: "not a real PII detector", `policy_analytics.profiling.schema_profiler` module docstring) | Cleared to `[]`, `examples_suppressed` set `True` |
| `dataset_column_profiles.suspicious_values` | Yes — literal flagged values | Cleared to `[]` |
| `dataset_column_profiles.min_value`/`max_value`, counts, `row_count`, `missingness`, etc. | No — aggregate statistics by the profiler's own design (the same module deliberately routes only `examples`/PII-shaped fields through the suppression floor) | Left intact |
| `datasets.quality_report` (`DataQualityReport`) | No — confirmed by reading `policy_analytics.profiling.quality_report`: counts and column names only, never literal values | Left intact |
| `datasets.columns` (`DatasetColumn`: name/type/timing/nullable) | No — schema metadata only | Left intact |
| `analysis_runs`, `candidate_patterns`, `validation_reports`, `findings`, `policy_candidates` | Believed no — these hold feature names, thresholds, and aggregate statistics (conditions, effect sizes, rank scores), not raw customer rows | Left intact (also structurally required — `ondelete="RESTRICT"`) |

The last row is disclosed as an assumption, not a verified fact, for the same reason the schema
profiler itself declines to claim certainty about PII: nothing in this codebase has ever audited
`CandidatePatternModel.conditions`/`FindingModel.pattern_snapshot`/`PolicyCandidateModel`'s snapshot
fields specifically for literal-value leakage (as opposed to feature names and numeric thresholds,
which is what their schemas define). This is flagged in
`docs/security/task-037-pre-customer-review-prep.md`'s gap list for `TASK-037`'s actual review to
confirm, not asserted here as settled.

**Not implemented, and deliberately out of scope for this pass:** whether `findings`/
`policy_candidates` derived from a since-deleted source dataset should themselves become invisible
or flagged in the product UI once their source is gone. That is a product/UX question, not a
storage/logs/access/backups/secrets/deletion-boundary one — `TASK-037`'s own goal text scopes this
review to the latter. Recorded as an open question below.

## The audit record

`DatasetDeletionModel` (`dataset_deletions` table, migration `20260822_0009`) — one append-only row
per deletion request, matching this codebase's existing append-only precedent
(`CandidatePatternModel`, `FindingFeedbackModel`, `PolicyBacktestRunModel`). Fields: `dataset_id`,
`requested_by_user_id` (attributed via the existing `TASK-053` session auth — the delete endpoint
requires login, extending its "deliberately narrow protected surface" the same way `TASK-035`'s
feedback endpoint did), `requested_at`, `reason` (required, non-empty — an undisclosed reason is not
auditable), `raw_bytes_purged`, `raw_bytes_retained_reason`, `redacted_column_profile_count`. Never
updated after insert.

## Verified end to end

`tests/api/test_dataset_deletion.py`, run against a real ephemeral Postgres
(`docker run postgres:16.4-alpine`, migrated with `alembic upgrade head`, matching CI's own
service-container setup in `.github/workflows/ci.yml`): upload → delete → confirm 404 on
`GET`/absent from `GET /api/v1/datasets` → confirm the raw file is actually gone from disk (not
just hidden) → confirm column-profile examples are redacted while counts survive → confirm a second
active dataset sharing the same content hash keeps its bytes when the first is deleted → confirm
re-deleting an already-deleted dataset is `409`, not a silent no-op → confirm the endpoint requires
authentication and a non-empty reason. `alembic check` and a full `downgrade base` /
`upgrade head` round-trip both pass against the same database.

## Known limitations (disclosed, not silently assumed away)

- The commit-after-unlink race described above under "Ordering guarantee".
- No retention-expiry sweep — see "What 'delete' means here" #2. Acceptable because nothing in
  this codebase currently promises time-bound retention (`docs/architecture/ingestion-contract.md`:
  "Indefinite by default; no automatic expiry").
- Whether immediate tombstone-and-purge, as implemented, actually satisfies a real contractual or
  regulatory deletion deadline (e.g. GDPR Article 17's "without undue delay") is unverified against
  any real requirement, because no real customer contract exists yet. Flagged to Founder Strategy
  (`memory/HANDOFFS.md`) rather than guessed at — see below.
- `analysis_runs`/`candidate_patterns`/`validation_reports`/`findings`/`policy_candidates`
  literal-content risk is disclosed as an open assumption above, not resolved here.

## Flagged to Founder Strategy

Per `ADR-004`'s disclosed-methodology principle applied to this operational design (not just
numerical claims) and the founder-facing instruction to flag rather than silently guess past real
customer-conversation-dependent unknowns: whether "tombstone + conditional physical purge,
synchronous, no grace period" is the *right* deletion semantics — as opposed to, say, a mandatory
grace/undo window, or a stricter immediate-hard-delete-with-no-audit-retention model some
contracts require — depends on actual contractual/legal deletion requirements no synthetic-data
pass can determine. See `memory/HANDOFFS.md` for the recorded flag; this document implements the
best-defensible default (immediate, no invented grace period, full audit trail) pending that input,
not a claim that it is definitely the final design.
