# API client layer

Thin, typed access to the FastAPI backend (`apps/api`). There is no code
generator wired up yet, so this layer is a hand-maintained mirror of the
backend's Pydantic schemas — see "Keeping this in sync" below.

## Files

| File | Responsibility |
|---|---|
| `config.ts` | Resolves the API base URL from `NEXT_PUBLIC_API_URL` (see "Environment configuration"). |
| `errors.ts` | `ApiError` — the one error type every client call can throw — plus the FastAPI error-body shape it normalizes. |
| `client.ts` | `apiFetch<T>(path, init)` — the single fetch wrapper. Always throws `ApiError`, never a raw `Error`/`TypeError`. Always `cache: "no-store"`. |
| `types.ts` | Hand-mirrored TypeScript types for every response shape the backend sends (`apps/api/app/api/schemas.py`) and shared enums (`packages/schemas/src/policy_schemas/domain.py`). |
| `datasets.ts`, `findings.ts`, `health.ts` | One typed function per backend endpoint actually in use, grouped by resource. |

## Environment configuration

`NEXT_PUBLIC_API_URL` (see `.env.example`) is the API base URL, e.g.
`http://localhost:8000` in development. It must be set at build time because
Next.js inlines `NEXT_PUBLIC_*` variables into the client bundle.

- **Development:** falls back to `http://localhost:8000` if unset.
- **Production:** `getApiBaseUrl()` throws instead of silently assuming a
  default, matching the backend's own refusal to start with unsafe defaults
  outside development (`apps/api/app/core/config.py`).

## Error handling contract

FastAPI's default error envelope is `{ "detail": ... }`: a string for
`HTTPException`s (e.g. 404 "Dataset not found") or a list of validation-error
objects for 422s. Every call through `apiFetch` normalizes both into a single
`ApiError`:

```ts
try {
  const dataset = await getDataset(id);
} catch (error) {
  if (error instanceof ApiError) {
    error.kind;      // "network" | "http"
    error.status;     // HTTP status, when kind === "http"
    error.message;    // human-readable, safe to show as-is
    error.requestId;  // backend's x-request-id, when present, for support/debugging
  }
}
```

UI code should not need to branch on `error.kind`/`error.status` beyond
deciding whether to offer a retry — `error.message` is already a reasonable
string to render inside `<ErrorState />` (`apps/web/components/states/`).

## Keeping this in sync

`types.ts` has no runtime validation (no `zod`/schema library is part of this
project yet) — it is a compile-time-only mirror. When a backend response
shape changes:

1. Update the corresponding type in `types.ts` to match
   `apps/api/app/api/schemas.py` / `packages/schemas/src/policy_schemas/domain.py`
   exactly — do not add fields the backend doesn't send, and do not guess at
   fields it will send later.
2. Add/update the endpoint function in the relevant resource module.

Do not invent a new shape for something the backend already defines (e.g. a
looser or renamed `Finding` type "for convenience") — that reintroduces the
duplicate-contract problem this layer exists to avoid. If the backend is
missing a field or endpoint a page needs, that is an Architect handoff
(`memory/HANDOFFS.md`), not something to work around here.

## What is intentionally not here yet

- **Write operations** (`POST /api/v1/datasets`, dataset upload): the backend
  route exists, but no upload UX has been approved by Product, so no client
  function or form is wired up. Add it alongside that UX work, not before.
- **Finding detail fields** (raw/adjusted effect, uncertainty, impact,
  stability, confounder checks): not in the backend response yet
  (`TASK-024`/`TASK-025`). `Finding` in `types.ts` only has what
  `FindingRead` currently returns. See `docs/product/finding-detail-screen.md`
  for the approved UX spec this will need to satisfy once the backend exists.
