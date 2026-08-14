# apps/web — frontend conventions

Next.js App Router frontend. This document is the frontend-local conventions reference (referenced
as "frontend conventions" by task briefs); it describes patterns already in use here, not new
policy. Product/UX specs live in `docs/product/`; this only covers implementation shape.

## Routing

- `app/page.tsx` is the marketing/landing page at `/`, outside the application shell.
- `app/(app)/` is a route group (no URL segment) for product surfaces: `layout.tsx` provides the
  shared nav/header, distinct from the marketing page. New product routes go under this group.
- `app/(app)/dev/` is dev-only tooling (e.g. `/dev/status`), guarded with
  `if (process.env.NODE_ENV === "production") notFound();` in the page itself — never shipped as a
  reachable production route.
- A page whose content must reflect live backend state on every request needs
  `export const dynamic = "force-dynamic";` — without it, Next.js can statically prerender the page
  at build time (including a build-time API failure) and serve that frozen snapshot in production.
  See `app/(app)/datasets/page.tsx` / `app/(app)/findings/page.tsx` for the pattern.

## Server/client component boundaries

Default to server components. Pages that fetch data (`app/(app)/*/page.tsx`) are `async` server
components that call `lib/api/` directly and handle the error/empty branches inline — no client-side
data-fetching hook for the default read path. `"use client"` is reserved for:

- Next's `error.tsx` error-boundary convention (must be a client component per Next.js).
- Genuinely interactive widgets with local state (e.g. `app/(app)/dev/status/status-check.tsx`,
  which re-runs a check on a button click).

Before adding `"use client"` to something, check whether the interactivity can instead live in a
small leaf component while the page/layout around it stays a server component.

## API client layer

See `lib/api/README.md` — the full contract for `lib/api/`: typed `ApiError`, the `apiFetch`
wrapper, and why response types are a hand-mirrored copy of the backend's Pydantic schemas rather
than invented independently. `fetch()` must only ever be called from `lib/api/client.ts`; every
other module goes through `apiFetch`.

## Loading / error / empty states

Reusable primitives live in `components/states/` (`LoadingState`, `ErrorState`, `EmptyState`) and
must be reused, not reimplemented per page:

- `LoadingState` — `role="status"`, `aria-live="polite"`. Used automatically by Next's `loading.tsx`
  file convention for a route segment's pending state.
- `ErrorState` — `role="alert"`; takes an already-safe-to-render `message` (from
  `lib/api/display.ts`'s `toErrorDisplay(error)`), an optional `requestId`, and an optional
  `retryHref` (a real link, since a server component page can't take a client-side retry callback).
- `EmptyState` — a successful response with zero items. Never use it to soften an actual error, and
  never use `ErrorState` to represent "nothing here yet."

## Accessibility baseline

`eslint-config-next`'s `core-web-vitals` config includes `eslint-plugin-jsx-a11y` recommended rules
and runs as part of `pnpm lint` — most structural a11y issues (missing labels, invalid ARIA, etc.)
are caught automatically. Beyond the lint layer: interactive elements that navigate use `next/link`
(never a bare `<a href>` to an internal route — also enforced by
`@next/next/no-html-link-for-pages`); custom interactive elements (e.g. `.stateBlock-retry`) keep a
visible `:focus-visible` style; live-updating regions use `aria-live`/`role` rather than relying on
visual change alone.

## Testing

`vitest` + `@testing-library/react`/`jsdom`. Run with `pnpm --filter web test` (or `make test`,
which runs it alongside the backend suite). Config: `vitest.config.mts`; global setup
(`@testing-library/jest-dom` matchers): `vitest.setup.ts`. Test files live beside the source file
they cover (`foo.ts` → `foo.test.ts`), not in a separate mirrored tree.

What's covered today is infrastructure only, matching what actually exists behind it:
`lib/api/errors.test.ts` and `lib/api/client.test.ts` test the typed-error-handling contract
(network vs. HTTP `ApiError`, FastAPI string vs. validation-list `detail`), and
`components/states/*.test.tsx` test the loading/error/empty primitives' accessible roles and props.
There are intentionally no tests asserting specific Finding content — no validated Finding schema is
served by the API yet (`TASK-025`), and a test that encodes invented Finding data would be exactly
the kind of speculative-semantics UI this repository's role contract forbids building.

## What not to do here

- Don't add a new state primitive, badge style, or copy string for Finding/evidence content without
  a Product spec backing it (`docs/product/`) — that's a semantics decision, not a frontend one.
- Don't hand-invent a response type for an endpoint that doesn't exist yet, and don't loosen an
  existing type "to unblock" a screen — see `lib/api/README.md`'s sync discipline.
- Don't call `fetch` outside `lib/api/client.ts`.
