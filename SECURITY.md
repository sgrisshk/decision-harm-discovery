# Security policy

Report vulnerabilities privately to the repository owners; do not open a public issue with exploit details.

## Baseline

- Secrets live in environment variables locally and a secret manager when deployed. `.env` files are ignored.
- Real customer exports, local databases, and analysis artifacts must never enter Git.
- Logs must not contain uploaded rows, credentials, tokens, or PII. Request IDs are safe correlation keys.
- Upload handlers must validate extension and MIME/content, sanitize filenames, enforce `MAX_UPLOAD_BYTES`, store immutable raw bytes outside the web root, and scan where the deployment platform supports it. See `docs/architecture/ingestion-contract.md` for the implemented contract (`TASK-005`/`TASK-006`); malware scanning is a deployment-platform hook, not implemented locally.
- Database credentials are server-only. Browser bundles receive only `NEXT_PUBLIC_API_URL`.
- CORS allowlists are explicit. Production debug mode is disabled and API errors hide internals.
- Dependencies and lockfiles are reviewed and scanned in CI.
- Security response headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, a strict Content-Security-Policy, Permissions-Policy) are set on every response by `SecurityHeadersMiddleware`.
- HSTS/forced HTTPS is intentionally not set — TLS termination is an undecided deployment-provider choice (`docs/operations/deployment.md`); hardcoding it now would break local/Docker dev and risks pinning it wrong behind a future misconfigured proxy.

## Authentication — real, but narrow (`TASK-053`, `ADR-027`)

Internal-staff login exists (`apps/api/app/auth/`): bcrypt-hashed passwords, DB-backed session
cookies (httpOnly, `SameSite=Lax`, real revocation on logout — no JWT). Accounts are created only
via `scripts/create_user.py`; there is no self-serve signup endpoint.

**This does not mean the MVP is locked down.** Auth exists to attribute *who* performs a small set
of sensitive writes — customer finding feedback (`POST /api/v1/findings/{id}/feedback`, `TASK-035`)
and dataset deletion (`DELETE /api/v1/datasets/{id}`, `TASK-055`,
`docs/architecture/dataset-deletion-contract.md`) — and, since `TASK-037`'s pre-customer-safe review
(2026-08-23, `docs/security/task-037-pre-customer-review-prep.md` findings 1/2), to gate reads that
carry literal source content: `GET /api/v1/datasets`, `GET /api/v1/datasets/{id}`
(`dataset_column_profiles.examples`/`suspicious_values` are literal, unmodified values copied from
uploaded rows, suppressed only by a cardinality heuristic that is explicitly not a real PII
detector — see `packages/analytics/src/policy_analytics/profiling/schema_profiler.py`'s module
docstring) and `GET /api/v1/findings/{id}/feedback` (`customer_owner`/`customer_comment` are a real
customer contact's name and verbatim words — the write side already required auth for exactly this
reason; the read side did not, until now). Dataset upload, `GET /api/v1/findings`, and
`GET /api/v1/findings/{id}` (feature names/thresholds/statistics only, not raw customer rows) remain
unauthenticated by design. Login rate-limiting and bot protection are not implemented. **Do not
expose this MVP to untrusted networks** — most of the API still has no access control at all.

## Dataset deletion (`TASK-055`)

`DELETE /api/v1/datasets/{id}` requires authentication, a non-empty disclosed reason, and produces
an append-only audit row (`dataset_deletions`) recording who, when, why, and the exact disposition
of the raw bytes (purged, or retained because another active dataset shares the same
content-addressed hash). See `docs/architecture/dataset-deletion-contract.md` for the full contract,
including what happens to derived artifacts and the disclosed open questions flagged to Founder
Strategy in `memory/HANDOFFS.md`.

