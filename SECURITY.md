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

Auth is a documented future boundary, not a placeholder that implies protection. Do not expose this MVP to untrusted networks before authentication and authorization are implemented.

