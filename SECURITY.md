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

**This does not mean the MVP is locked down.** Auth exists specifically to attribute *who* records
customer finding feedback (`POST /api/v1/findings/{id}/feedback`, `TASK-035`) — that is the only
route that currently requires it. Every other route, including dataset upload, remains
unauthenticated by design. Login rate-limiting and bot protection are not implemented. **Do not
expose this MVP to untrusted networks** — most of the API still has no access control at all.

