# TASK-037 pre-customer review prep

`TASK-037` ("Real-dataset security review") is `BLOCKED` on `TASK-057` (a live customer) and its
goal text is: *"Review storage, logs, access, backups, local copies, secrets, and deletion before
any real data enters the system."* Per `ADR-058`'s resolution of the apparent
`TASK-037`↔`TASK-057`↔`TASK-055` circularity, the portion of that review achievable against the
*current* ingestion pipeline (`TASK-005`–`TASK-009`) — without a real customer dataset already in
hand — is real, scoped work, not something to defer. This document is that prep: what already
exists per area, and the gap list against `SECURITY.md` and `TASK-037`'s own goal text, so
`CODE_REVIEWER`'s actual review does not have to re-derive any of this from scratch. It is prep,
not the review itself — nothing here is a Code-Reviewer sign-off.

## What already exists, per area

### Storage
Content-addressed, immutable local-filesystem storage (`TASK-005`/`TASK-006`,
`docs/architecture/ingestion-contract.md`): `{root}/{sha256[:2]}/{sha256}.csv`, write-to-temp +
`fsync` + atomic `os.replace` + `chmod 0o440`. Re-storing identical bytes is a dedup no-op, never a
rewrite. `UNIQUE(name, version)` prevents silent overwrite at the row level.

### Logs
`SECURITY.md`: "Logs must not contain uploaded rows, credentials, tokens, or PII." Verified
directly, not just asserted: `app.datasets.service`/`app.datasets.profiling` log only IDs,
checksums, sizes, and boolean/count fields (grepped for every `logger.*` call site in the datasets
and ingestion modules); `RequestLoggingMiddleware` logs path/method/status/duration only. A
regression test already exists for this specific guarantee:
`tests/api/test_datasets_upload.py::test_upload_never_logs_the_filename`.

### Access
`TASK-053`/`ADR-027`: real internal-staff auth (bcrypt, DB-backed opaque session cookies, real
logout revocation, no JWT). Deliberately narrow protected surface — originally only
`POST /api/v1/findings/{id}/feedback`; `TASK-055` (this pass) extends it to
`DELETE /api/v1/datasets/{id}`. Every other route, including dataset upload and all reads, is
explicitly unauthenticated by design (`SECURITY.md`, restated there so it cannot be misread as a
full lockdown).

### Backups
Not decided (`docs/operations/deployment.md`, "Still undecided"): "backups/PITR policy on the Neon
project." No backup mechanism exists or is configured anywhere in this repository today.

### Local copies
Traced the full upload path (`app.ingestion.storage.store_immutable_csv`,
`app.datasets.service.create_dataset_from_upload`): the uploaded stream is read into memory once
(bounded by `MAX_UPLOAD_BYTES`), content-addressed, and written directly to its final immutable
location via a temp-file-in-the-same-directory + atomic rename — the temp file is unconditionally
unlinked in a `finally` block whether or not the rename succeeds. No second on-disk copy is ever
created; profiling (`TASK-007`) reads the same in-memory dataframe rather than re-reading or copying
the file. One caveat carried over from deployment config, not the ingestion code itself: Render's
free tier has no persistent disk, so `INGESTION_STORAGE_ROOT` does not survive a restart/redeploy —
disclosed in `docs/operations/deployment.md` as a real blocker to resolve before `TASK-038`, not
silently ignored.

### Secrets
`SECURITY.md`: env vars locally, `.env` gitignored, DB credentials server-only, browser bundles get
only `NEXT_PUBLIC_API_URL`. Deployment secrets (`DATABASE_URL`, `CORS_ORIGINS`) are set directly in
the Render dashboard, never committed (`docs/operations/deployment.md`). No secret-manager service
beyond that is decided yet ("Still undecided": "secret manager beyond Render's own env vars").

### Deletion
Was the one genuinely missing piece before this pass — `TASK-055`, now implemented against the
synthetic/test-data path: `docs/architecture/dataset-deletion-contract.md`. Tombstone +
conditional physical purge, literal-content redaction on derived column profiles, append-only audit
record. See that document for the full contract and its own disclosed limitations.

## Gap list against `SECURITY.md` and `TASK-037`'s goal text

Ranked by what a real customer dataset would actually expose, not file order.

1. **No persistent disk on the current free-tier deploy target.** Real customer raw bytes would not
   survive a Render restart/redeploy under the current `docs/operations/deployment.md` config — a
   real blocker, already disclosed there as one, not new information, but restated here because
   `TASK-037`'s goal text asks specifically about storage and this is the storage gap that matters
   most before real data. **Must resolve before `TASK-038`:** either a paid Render plan with a
   persistent disk, or move raw storage to object storage (Cloudflare R2, per that doc).
2. **No backup/PITR policy on the database.** `dataset_column_profiles`, `datasets`, and now
   `dataset_deletions` (the audit trail itself) have no backup story at all. A database-level
   incident before this is decided loses both the data and the audit record of what was deleted.
3. **Unverified literal-content risk in `analysis_runs`/`candidate_patterns`/`validation_reports`/
   `findings`/`policy_candidates`.** Disclosed in
   `docs/architecture/dataset-deletion-contract.md` as an assumption, not a verified fact: these
   tables are believed to hold only feature names, thresholds, and aggregate statistics, never raw
   customer rows, but nothing in this codebase has specifically audited them for literal-value
   leakage the way the schema profiler's own `examples_suppressed` design already does for column
   profiles. Real customer data raises the stakes of this being wrong.
4. **No secret-manager service decided for deployment**, beyond Render's own env-var store. Low
   urgency pre-customer (no real secrets exist yet beyond `DATABASE_URL`/`CORS_ORIGINS`), but should
   be decided before it matters.
5. **Dataset deletion's grace-period-free, no-invented-retention-window design is unverified
   against any real contractual/legal deletion requirement** (e.g. GDPR Article 17 timing) — see
   `docs/architecture/dataset-deletion-contract.md`'s "Flagged to Founder Strategy" section and the
   matching `memory/HANDOFFS.md` entry. Not a code gap; a requirements gap only a real customer
   contract can close.
6. **Malware/content scanning is a deployment-platform hook, not implemented locally**
   (`SECURITY.md`, already disclosed, restated here for completeness against `TASK-037`'s "before
   any real data enters the system" framing).
7. **No login rate-limiting/bot protection** (`SECURITY.md`, already disclosed). Low relevance to
   *this* review's storage/logs/access/backups/local-copies/secrets/deletion scope specifically,
   listed for completeness since it is part of "access."

Items 1–4 and 6–7 are pre-existing, already-disclosed gaps this document did not create — they are
collected here so `TASK-037`'s actual review has one place to start rather than re-deriving them
from `SECURITY.md` and `docs/operations/deployment.md` separately. Item 5 is new, produced directly
by this pass's `TASK-055` work.

## What this document is not

Not a Code-Reviewer sign-off, not a claim that the pre-customer-safe portion of `TASK-037` is
"done" — `TASK-037` itself stays `BLOCKED` on `TASK-057` per `ADR-058` (final execution needs the
real dataset). This is the prepared review target `ADR-058` asks for: confirmed existing posture
plus an explicit, ranked gap list, so the real review — whenever `TASK-057` produces a customer —
starts from here instead of from zero.
