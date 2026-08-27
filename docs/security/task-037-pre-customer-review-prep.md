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

---

## Code Reviewer pre-customer-safe review (2026-08-23)

The sign-off this document explicitly said it was not. Scope: the ingestion path (upload → storage
→ profiling → timing classification → quality report) plus `TASK-053`'s auth boundary, per
`agents/CODE_REVIEWER.md`, `SECURITY.md`, and this document. This is **not** `TASK-037` itself —
`TASK-037` stays `BLOCKED` on `TASK-057` (a real dataset) per `ADR-058`; this is the pre-customer-
safe portion `ADR-058` condition (2) asks Code Reviewer/Architect to scope, executed and recorded.

**Verified directly, not read off this document's claims:** re-read
`app.ingestion.storage`/`validation`, `app.datasets.routes`/`service`/`profiling`/`quality`,
`app.auth.dependencies`, `app.db.models`, `app.api.schemas`, and the `20260822_0009` migration.
Spun up a real ephemeral Postgres (`docker run postgres:16.4-alpine`, migrated with
`alembic upgrade head`) and ran `tests/api/test_datasets_upload.py` (6 passed, including
`test_upload_never_logs_the_filename` — `TASK-006`'s log-inspection guarantee reverified live, not
assumed to still hold), `tests/api/test_auth.py` + `tests/api/test_dataset_deletion.py` (17 passed),
and the full non-`blind_agent` suite (626 passed) against that database. Storage/logs/access
(narrow surface)/local-copies/deletion claims in this document's "What already exists" section are
all confirmed accurate. Backups and secret-manager posture are confirmed accurate by inspection of
`docs/operations/deployment.md` (no code path to verify — these are infrastructure-configuration
gaps, not code gaps, and are not re-litigated here beyond confirming the disclosure is current).

**Two new findings, both structural, both real access-control gaps within the reviewed surface —
not present in this document's original gap list:**

### Finding 1 (HIGH): Unauthenticated read of literal source-data content via the dataset API

- **Severity:** HIGH
- **File:** `apps/api/app/datasets/routes.py:29-36` (`list_datasets`/`get_dataset`, no
  `Depends(get_current_user)`); root cause in
  `packages/analytics/src/policy_analytics/profiling/schema_profiler.py:33-37,181-193`
  (`_examples`/`_SUPPRESSED_SEMANTIC_TYPES`).
- **Evidence:** `GET /api/v1/datasets` and `GET /api/v1/datasets/{id}` require no authentication
  (confirmed: only `DELETE /api/v1/datasets/{id}` carries `Depends(get_current_user)` in that
  router). Both return `DatasetRead.column_profiles`, which includes
  `DatasetColumnProfileRead.examples`/`suspicious_values` — up to 3 (or 5) **literal, unmodified
  values copied straight from the uploaded CSV's cells**, truncated only to 80 characters, per
  `schema_profiler.profile_column`. Suppression is not PII detection: it fires only when a column's
  *semantic-type guess* lands on `identifier`/`free_text` **and** cardinality exceeds 0.9 — the
  module's own docstring calls this "not a real PII detector," and `_guess_semantic_type` has no
  path that inspects value *content* for names, emails, phone numbers, or similar. A column with
  moderate cardinality (repeated values — e.g. a customer name column in a dataset with repeat
  customers, or any column whose name doesn't end in `_id`/hit a currency/rate/count-name hint) is
  classified `categorical` or `unclassified` and its literal values pass through unsuppressed.
- **Why it matters:** The moment `TASK-038` ingests a real customer dataset, any caller with network
  access to the API — no login, no token, nothing — can `GET /api/v1/datasets` and read literal
  cell values from that customer's raw data. `SECURITY.md` already discloses "most of the API still
  has no access control at all" as a general, deliberate MVP posture, but does not call out that the
  *specific* consequence of that posture, for this specific route, is direct exposure of raw
  source-data content gated only by a heuristic its own author disclaims as not a PII detector. This
  is the single most consequential gap this review found relative to `TASK-037`'s goal text
  ("review... access... before any real data enters the system").
- **How to reproduce:** Upload any CSV with a low-to-moderate-cardinality text column (e.g. a
  `customer_name` column with a handful of repeat names) via `POST /api/v1/datasets`. `GET
  /api/v1/datasets/{id}` with no `Cookie` header returns that column's literal names in
  `column_profiles[].examples`.
- **Recommended fix:** Not this review's call to make unilaterally (`agents/CODE_REVIEWER.md`:
  review first, recommend, don't auto-rewrite) — but the two live options are (a) require auth on
  `GET /api/v1/datasets`/`GET /api/v1/datasets/{id}` before `TASK-038`, extending `TASK-053`'s
  "deliberately narrow" surface the same way `TASK-055` extended it to deletion, or (b) keep reads
  open but strip `examples`/`suspicious_values` (or the whole `column_profiles` array) from the
  unauthenticated response shape and gate the literal-content fields behind auth specifically. Either
  is an `ARCHITECT`-owned design decision; this finding only establishes that one is needed before
  `TASK-038`, not which.

### Finding 2 (HIGH): Unauthenticated read of real customer names/comments via the finding-feedback API

- **Severity:** HIGH
- **File:** `apps/api/app/findings/routes.py:44-51` (`list_finding_feedback`, no
  `Depends(get_current_user)`); model at `apps/api/app/db/models.py:347-375`
  (`FindingFeedbackModel`).
- **Evidence:** `POST /api/v1/findings/{id}/feedback` (the write) requires auth — per `SECURITY.md`,
  specifically so a sensitive write can be attributed to the internal staff member who made it.
  `GET /api/v1/findings/{id}/feedback` (the read of the exact same data) requires nothing.
  `FindingFeedbackModel.customer_comment` is documented
  (`docs/product/finding-feedback-contract.md` §4: "the customer's own words, not a paraphrase")
  and `customer_owner` is documented (§4: "free text (name/role)... the person on the customer side
  who can actually approve acting on this finding") — both fields exist specifically to capture a
  real, named customer contact's verbatim reaction. `FindingFeedbackRead` returns both unfiltered.
- **Why it matters:** This table is empty today (no real findings/feedback exist yet), so nothing is
  exposed *right now* — but the write path's own justification for requiring auth (attributing a
  sensitive action) is defeated for reads: anyone can read a real customer contact's name and
  verbatim quoted comment about a specific finding the moment `TASK-042` (customer findings review)
  starts capturing real feedback, with no login required. This is a sharper instance of the same
  general "reads are unauthenticated" disclosure — sharper because the write side of this exact
  endpoint pair was deliberately hardened for a reason (`TASK-053`'s own stated goal) that the read
  side quietly undoes.
- **How to reproduce:** With any authenticated session, `POST
  /api/v1/findings/{id}/feedback` with a `customer_owner`/`customer_comment`. Then `GET
  /api/v1/findings/{id}/feedback` with no `Cookie` header returns it verbatim.
- **Recommended fix:** Same shape as Finding 1 — extend the auth boundary to the feedback read route
  (and/or `GET /api/v1/findings`, which returns `pattern`/`evidence`/`impact` — believed
  non-PII by `FindingPatternRead`/`FindingEvidenceRead`/`FindingImpactRead`'s own schemas, feature
  names and statistics only, not re-litigated here), an `ARCHITECT`-owned decision, before
  `TASK-042` produces real rows.

**Reconfirmed, not new — this document's existing gap list items 1–4 and 6–7 (no persistent disk,
no backup/PITR policy, unverified literal-content risk in `analysis_runs`/`candidate_patterns`/
`validation_reports`/`findings`/`policy_candidates`, no secret-manager decision, malware scanning is
a platform hook, no login rate-limiting) all still hold as stated.** One refinement to item 3: traced
`policy_analytics.discovery.engine._atoms` — a categorical column becomes an `eq` condition atom
(and can therefore appear as a literal value inside `candidate_patterns.conditions` /
`findings.pattern_snapshot`, both currently exposed read-only without auth via `GET
/api/v1/findings`) whenever it is classified `DECISION_TIME` and has at most
`max_categorical_levels` (default 12) distinct values — there is no check that such a column is
*not* PII-shaped (e.g. a low-cardinality field like a coarse demographic bucket). This does not
promote item 3 from "unverified assumption" to "confirmed leak" — whether any real dataset's
`DECISION_TIME` classification would actually select such a column is dataset-dependent and
unknown today — but it narrows the assumption: the *mechanism* has no guard against it, so item 3's
resolution cannot rely on "the code doesn't allow it" and must instead be a real audit against
whatever columns a real dataset's `TASK-008` classification admits.

**Verdict (as first written):** `SHIP_WITH_FIXES` on the reviewed surface, for `TASK-037`'s
pre-customer-safe purpose. Storage/logs/local-copies/deletion are solid — implemented as documented,
independently re-verified against a real database, not just claimed. Findings 1 and 2 are real,
structural, HIGH-severity access-control gaps that must close before `TASK-038` (Finding 1) and
`TASK-042` (Finding 2) respectively, or `TASK-037`'s own goal text ("before any real data enters the
system") is not met regardless of what this document's other sections already confirmed. Neither
finding blocks `TASK-055` or this prep pass itself — both were recommendations for `ARCHITECT` to
schedule, not fixes applied at review time (per `agents/CODE_REVIEWER.md`: review, then recommend,
don't auto-rewrite). `TASK-037` itself is correctly still `BLOCKED` on `TASK-057` and is **not**
being marked `DONE` by this entry — this is the prep work that makes the eventual real review fast,
per that task's own scope, not the review itself.

**Findings 1 and 2: fixed (2026-08-23, same session, on explicit instruction to apply the
recommended fix — option (a) from each finding's own list, not silently chosen).**

- `GET /api/v1/datasets`, `GET /api/v1/datasets/{id}`
  (`apps/api/app/datasets/routes.py::list_datasets`/`get_dataset`) and
  `GET /api/v1/findings/{id}/feedback` (`apps/api/app/findings/routes.py::list_finding_feedback`)
  now carry `Depends(get_current_user)`, extending `TASK-053`'s protected surface the same way
  `TASK-055` extended it to deletion. `GET /api/v1/findings`/`GET /api/v1/findings/{id}` remain
  unauthenticated, unchanged — believed non-PII per this document's own reconfirmation above, not
  re-litigated by this fix.
- Every existing call site in the test suite that hit these routes unauthenticated was updated to
  log in first (a new shared `login_as_staff` fixture in `tests/conftest.py`, replacing the need to
  hand-roll the create-user-then-log-in sequence per file); three new tests assert the 401 directly
  (`test_list_datasets_requires_authentication`, `test_get_dataset_requires_authentication`,
  `test_list_feedback_requires_authentication`). Full suite re-run against a real ephemeral Postgres:
  629 passed (was 626 before this fix; +3 new). `ruff` and project-scoped `pyright` clean.
- `apps/web/app/(app)/datasets/DatasetsView.tsx` — the one current frontend consumer of a now-gated
  route — updated to detect a `401 ApiError` and show a "log in to view datasets" prompt
  (`retryHref="/login?next=%2Fdatasets"`, matching `ReviewSessionView.tsx`'s existing pattern)
  instead of a generic error. `apps/web/app/(app)/findings/detail/FindingDetailView.tsx`'s feedback
  fetch was already wrapped in `.catch(() => [])` as a supplementary, non-fatal read (same treatment
  as policy candidates and provenance on that page) — an anonymous viewer now sees an empty feedback
  history rather than the real one, which is the correct data-exposure outcome; the page does not
  distinguish that from "no feedback yet" in its wording, a minor, low-priority polish item, not
  reopened here. `tsc --noEmit`, `eslint`, and `vitest run` (63 passed) all clean.
- `SECURITY.md`'s Access section updated to name the new protected surface accurately.
- Not touched: gap list items 1–7 (persistent disk, backup/PITR, the `analysis_runs`/
  `candidate_patterns`/etc. literal-content assumption, secret-manager decision, malware scanning,
  rate-limiting) — none of those are code-level access-control gaps this same fix shape applies to;
  they stand as recorded.

**Updated verdict:** `SHIP`. Findings 1 and 2 are closed, verified live against a real database and
the frontend, not just claimed. `TASK-037` itself remains correctly `BLOCKED` on `TASK-057` and is
**not** marked `DONE` by this entry.

---

## Independent re-verification, per `memory/HANDOFFS.md` HANDOFF-072 (2026-08-27, Code Reviewer)

Requested explicitly as a non-rubber-stamp check: re-verify every claim above and in
`docs/architecture/dataset-deletion-contract.md` directly, not on the strength of what was already
written. Re-read `apps/api/app/datasets/service.py`/`routes.py`,
`apps/api/app/ingestion/storage.py`, `apps/api/app/findings/routes.py`,
`packages/analytics/src/policy_analytics/profiling/schema_profiler.py`,
`packages/analytics/src/policy_analytics/discovery/engine.py`. Spun up a fresh real ephemeral
Postgres (`postgres:16.4-alpine`, not the one prior sessions used), ran `alembic upgrade head` on an
empty database, `alembic check`, a full `downgrade base`/`upgrade head` round-trip, and the full
repo suite (647 passed, up from 626 at `TASK-055`'s own original commit — the +21 are the two
findings' regression tests plus unrelated `TASK-068` work landed since). `pnpm --filter web
typecheck`/`lint`/`test` (63 passed) also re-run clean. Live-reproduced (not just read) that
unauthenticated `GET /api/v1/datasets` and `GET /api/v1/datasets/{id}` now correctly return `401` —
Findings 1 and 2's fix genuinely holds, not merely claimed.

**Everything in "What already exists" and the prior review's findings/fixes is confirmed accurate**
by this independent pass — storage (content-addressing, atomic write, `chmod`, dedup no-op), logs
(grepped every `logger.*` call site in the datasets/ingestion modules directly — IDs/counts/booleans
only), the narrow auth boundary, backups/secret-manager disclosure against
`docs/operations/deployment.md`, local-copies (traced `profile_dataset` — reads the stored file
directly via `pl.read_csv`, no second copy), and the `_examples`/`max_categorical_levels` code cited
for Finding 1 and the item-3 refinement all read exactly as described.

**Two new findings, neither present in this document, `docs/architecture/dataset-deletion-contract.md`,
or the prior review — found by testing the interaction between `TASK-055` and pre-existing `TASK-006`
logic directly, not by re-reading either document:**

### Finding R1 (HIGH): Deleting a dataset permanently blocks re-uploading identical content under the same name

- **Severity:** HIGH
- **File:** `apps/api/app/datasets/service.py:63-68` (`create_dataset_from_upload`'s `latest` query)
- **Evidence:** Reproduced live against a real Postgres: `POST /api/v1/datasets` (name=X,
  content=C) → `201`, version 1. `DELETE /api/v1/datasets/{id}` (authenticated) → `200`,
  `raw_bytes_purged: true`. `POST /api/v1/datasets` (name=X, content=C again) → `409 "identical
  content already exists as version 1"` — even though version 1 is tombstoned (invisible via `GET`,
  which now 404s per Finding 1's fix) and its bytes are physically gone from disk. Re-uploading
  *different* content under the same name after deletion works correctly (creates version 2,
  independently reproduced) — only the identical-content adjacency check is broken, because
  `latest` is fetched by `name`/`version` ordering alone, with no `DatasetModel.deleted_at.is_(None)`
  filter, so a deleted row still counts as "the same content already exists."
- **Why it matters:** This directly undermines `TASK-055`'s own purpose. Deleting a dataset and then
  re-supplying the identical file under the same name is one of the most likely real actions a real
  customer takes after a deletion request (e.g., "delete this, we'll re-send it"), and it is
  permanently blocked with a `409` referencing a version number that resolves nowhere else in the
  API. No test anywhere in the suite exercises this interaction, and it was missed by the review
  recorded immediately above this section — it is a gap in that review, not only in the code.
- **How to reproduce:** See Evidence — fully deterministic, 100% reproducible, no timing/concurrency
  required.
- **Recommended fix:** Not this review's call to make unilaterally (`agents/CODE_REVIEWER.md`:
  review, recommend, don't auto-rewrite). The shape is narrow: filter the adjacency query to
  `deleted_at.is_(None)` (or otherwise treat a deleted "latest" as no conflict) in
  `create_dataset_from_upload`. `ARCHITECT`-owned.

### Finding R2 (MEDIUM): Concurrent deletion of dedup-sharing datasets can orphan bytes permanently

- **Severity:** MEDIUM
- **File:** `apps/api/app/datasets/service.py:181-199` (`delete_dataset`'s
  `other_active_reference` check)
- **Evidence:** The dedup-sibling check is a plain `SELECT` under Postgres's default `READ
  COMMITTED` isolation — no `SELECT ... FOR UPDATE`, no advisory lock (grepped the whole
  `apps/api` tree for `isolation_level`/`FOR UPDATE`/`SERIALIZABLE`: no hits anywhere). If two
  datasets `A`/`B` share `checksum_sha256` and two `DELETE` requests for `A` and `B` run
  concurrently before either commits, each transaction's `SELECT` sees the other as still active
  (its `deleted_at` update is uncommitted), so both independently choose to retain bytes. The union
  outcome is "neither purges," even though after both commit, zero active datasets reference that
  content. No retention sweep exists anywhere in this codebase (`ADR-060`'s own deliberate choice)
  to reclaim it later.
- **Why it matters:** Narrow (requires genuine concurrent requests against dedup-sharing datasets)
  and fails in the safe direction — no wrong data exposure, no corruption, and the specific dataset
  each caller asked to delete is still correctly tombstoned either way. It is a storage-hygiene miss
  only: bytes nothing points to any more sit on disk forever. Not disclosed anywhere (not in this
  gap list, not in `docs/architecture/dataset-deletion-contract.md`'s "Known limitations"), and not
  exercised by any test (the existing suite is entirely sequential).
- **How to reproduce:** Requires two genuinely overlapping transactions; not demonstrated as an
  observed failure in this pass (the test suite is sequential) — established by direct code
  inspection of the missing locking primitive, not by triggering it live.
- **Recommended fix:** Not this review's call — options include `SELECT ... FOR UPDATE` on the
  checksum-sibling query, a Postgres advisory lock keyed by checksum, or accepting it as a disclosed
  limitation matching this document's own precedent (the already-accepted "unlink succeeds, commit
  fails" gap in `docs/architecture/dataset-deletion-contract.md`). `ARCHITECT`-owned.

**Gap list correction:** items 1–7 above are reconfirmed accurate as far as they go, but the list is
**not exhaustive** as it stood before this pass — it omitted both R1 and R2, both squarely inside
`TASK-037`'s "deletion" scope. Adding as item 8:

8. **R1 (re-upload-after-delete is permanently blocked for identical content) and R2 (concurrent
   dedup-deletion can orphan bytes)** — see above. R1 is a deterministic functional defect, not
   merely an unverified assumption like items 3/5; it should not be treated as an acceptable standing
   gap the way items 1–7 are. R2 is disclosable-and-acceptable in the same spirit as items 1–7, but
   was simply missing until now.

**Revised verdict:** `SHIP_WITH_FIXES`, superseding the `SHIP` verdict immediately above for the
reviewed surface as a whole. Findings 1/2 (access control) remain correctly closed. R1 must be
fixed (or, at minimum, explicitly accepted with a recorded decision updating this document and
`docs/architecture/dataset-deletion-contract.md`) before `TASK-055` can be considered to actually
satisfy its own goal text ("what happens to already-derived artifacts" implicitly assumes the
delete-then-redo path works). R2 should be recorded as an accepted limitation or fixed; either is
acceptable but silence is not. Routed to Architect: `HANDOFF-074`. `TASK-037` itself remains
`BLOCKED` on `TASK-057`, unaffected by this dispute either way.
