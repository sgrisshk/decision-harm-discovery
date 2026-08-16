# Immutable ingestion contract

**Scope:** `TASK-005`/`TASK-006`, resolving `HANDOFF-001`. Backend/storage only — a dataset upload
UI is separate Product-approved work (`apps/web/lib/api/README.md`), not this document.

## Problem

`ARCHITECTURE.md` requires raw data to be immutable and content-addressed/versioned, with a
reproducible raw → normalized → analytical path. Before this change, `POST /api/v1/datasets` was a
`TASK-002` placeholder: it accepted a JSON body with client-declared `columns` and never touched
file bytes. There was no upload, no checksum, no immutable storage, and no way to prevent an
accidental re-upload from silently duplicating a dataset.

## Answering HANDOFF-001

**What typed ingestion manifest is required?** Not a separate sidecar file. The manifest is
realized as columns on the `datasets` row: `checksum_sha256`, `size_bytes`, `content_type`,
`source_type`, plus the existing `name`/`source_filename`/`version`/`created_at`. Postgres already
gives this durability and queryability; a floating JSON manifest next to the blob would just be a
second, driftable source of truth.

**What validation stages?** Structural only — schema/type/feature-timing profiling is `TASK-007`
onward and stays out of scope here:

1. **Filename sanitization** (`app/ingestion/validation.py::sanitize_filename`) — basename only,
   `[A-Za-z0-9._-]`, must end in `.csv`, length-capped, rejects traversal/hidden/relative names.
2. **Bounded read** (`app/ingestion/storage.py::read_bounded`) — streams in 1 MiB chunks, aborts
   with `413` the moment `MAX_UPLOAD_BYTES` is exceeded, regardless of what `Content-Length`
   claimed.
3. **Content sniff** (`validation.py::validate_csv_content`) — rejects empty bodies, binary
   content (NUL bytes), non-UTF-8 text, and bodies with no delimiter-bearing first line. This is a
   sanity check, not CSV grammar/schema validation.
4. **Content-address + immutable persist** (`storage.py::store_immutable_csv`) — SHA-256 over the
   full body; stored at `{root}/{sha256[:2]}/{sha256}.csv`; write-to-temp + `fsync` +
   `os.replace` + `chmod 0o440`. Re-storing identical bytes is a dedup no-op, never a rewrite.
5. **Identity/version resolution** — see below.

**What lineage identifiers?** `id` (row), `name` (identity), `version` (monotonic per name),
`checksum_sha256` (content identity), `storage_path` (internal-only, not returned by the API —
keeps the physical layout free to change, e.g. a future move to S3-compatible storage, without an
API break).

**What data-quality output?** None yet — that is `TASK-009`, downstream of the `TASK-007` profiler.
Ingestion only proves the bytes are safe to store and are structurally CSV-shaped.

## Identity and versioning

`name` is the dataset identity. On upload:

- Look up the latest row for that `name` (`ORDER BY version DESC LIMIT 1`).
- If it exists and its `checksum_sha256` matches the new upload → reject `409`, no new row. This is
  the "prevent silent overwrite" rule: re-uploading the same file twice is a no-op error, not a
  meaningless new version.
- Otherwise insert a new row at `version = latest + 1` (or `1` if none exists).
- `UNIQUE(name, version)` in the database is the safety net under races: if two uploads for a new
  name (or the same next version) commit concurrently, the second `INSERT` fails the constraint and
  is mapped to `409` rather than corrupting version ordering.

Only adjacency (vs. the *latest* version) is deduplicated. Re-uploading an old version's exact
bytes again later creates a new version rather than being detected as a historical duplicate — full
historical dedup is out of scope for v0.

## Retention

Indefinite by default; no automatic expiry or deletion. Deletion is `TASK-055` (`BLOCKED`) and is
explicitly not built here.

## Storage backend

Local filesystem under `ingestion_storage_root` (default `data/raw/`, already gitignored via
`data/*`). No object-store service exists in `docker-compose.yml` yet, so this is the only real
option at this stage. The storage module (`app/ingestion/storage.py`) has no FastAPI/DB import, so
swapping to S3-compatible storage later only means reimplementing that module against the same
`StoredFile` return contract, not the API or the manifest columns.

## Logging boundary

No code path in the ingestion/dataset modules logs the filename or file content — only IDs,
checksum, and size ever reach a log statement, matching `SECURITY.md`'s "logs must not contain
uploaded rows... or PII." `RequestLoggingMiddleware` (unchanged) already only logs
path/method/status/duration.
