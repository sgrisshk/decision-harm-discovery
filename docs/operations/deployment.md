# Deployment interface

The **API's** provider is intentionally undecided. CI builds and verifies both images with immutable `${GITHUB_SHA}` tags. Once a registry/host is selected, staging deployment from `main` must consume those exact digests; production promotion is a manual protected-environment action that promotes the same digest rather than rebuilding it.

Provider decisions still required: registry, managed PostgreSQL, object storage, secret manager, migration runner, log/metric destination, backups, regional/data-residency constraints, and rollback mechanism. Do not add credentials or pretend deploy steps until those decisions are made.

Deploy order: backup/readiness checks → backward-compatible migration job → API → web → smoke checks. Rollback application images independently; forward-fix schema when a migration is not safely reversible.

## Web frontend: GitHub Pages (decided)

Unlike the API, `apps/web` *is* deployed — as a static export (`output: "export"` in `next.config.ts`) to GitHub Pages via `.github/workflows/pages.yml`, on every push to `main` that touches it. This was possible without picking a server host because the app was already architected to read all live data client-side against `NEXT_PUBLIC_API_URL` (see `lib/api/config.ts`) rather than server-rendering it — the httpOnly-cookie auth flow was already client-only for the same reason (`components/nav-user.tsx`).

Two routes that used to be server-rendered (`force-dynamic`) were converted to client components fetching in a `useEffect`, standard SPA-on-static-host pattern: `app/(app)/findings/page.tsx` and `app/(app)/datasets/page.tsx`. The finding detail route stopped being a `[id]` dynamic segment — static export requires every dynamic-segment value to be known via `generateStaticParams()` at build time, which an arbitrary finding ID can't be — and became `app/(app)/findings/detail/page.tsx`, reading `?id=` instead of a path segment.

Custom domain: `app.grisshk.work` (`apps/web/public/CNAME`, DNS on Cloudflare, registrar Spaceship). `NEXT_PUBLIC_API_URL` is a GitHub Actions repository variable, currently a placeholder (`https://api.grisshk.work`) since the API isn't hosted anywhere yet — the deployed site renders, but every data-fetching view shows a network error until that variable points at a real, CORS-enabled, publicly reachable API. Update the variable in place once the API decision above is made; no code or workflow change needed.
