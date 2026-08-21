# Deployment interface

## API backend: Render + Neon, free tier (decided, 2026-08-21)

Chosen specifically to cost **$0** pre-customer — Fly.io was considered first but no longer has a genuine free tier (usage-based billing, card required). `render.yaml` (repo root, Render's Blueprint format) builds `infra/docker/api.Dockerfile` directly — the same image CI already builds and verifies in the `images` job, no second Dockerfile. Postgres is **not** Render's own (its free Postgres is deleted after 30 days) — it's [Neon](https://neon.tech), a separately-provisioned free serverless Postgres with no forced expiry.

**Free-tier trade-offs, disclosed, not hidden:**
- Render's free web service **spins down after ~15 minutes idle** and takes roughly a minute to wake on the next request. Acceptable for a pre-customer demo; not acceptable once `TASK-057` produces a live customer conversation happening in real time — upgrade the plan first.
- Render's free plan has **no persistent disk** — `INGESTION_STORAGE_ROOT`'s uploaded raw files do **not** survive a restart or redeploy. Fine now (no real data at stake); a real blocker for `TASK-038` (real customer data) — either a paid plan with a persistent disk, or move raw storage to object storage (Cloudflare R2 has a free tier too, and the founder already has a Cloudflare account) before that task.
- No autoscaling, one instance only — irrelevant at current traffic (zero).

**Still real decisions/actions, not yet made — this is the config, not the account:**
- Neon project itself — not provisioned by this commit; needs a free Neon account.
- Secrets (`DATABASE_URL`, `CORS_ORIGINS`) — set in the Render dashboard (or `render env:set`), never committed.
- `autoDeploy` is `false` in `render.yaml` on purpose — deploy stays a manual, reviewed action for now rather than firing on every push to `main`, since a bad migration would hit the same database every time. Revisit once there's a staging/production split worth the complexity.

**First deploy, manual (needs free accounts on both services):**
```sh
# 1. Neon: neon.tech -> new project -> copy the connection string (use the "pooled" one).
#    Driver prefix must match Settings.require_postgres: postgresql+psycopg://...

# 2. Render: render.com -> New -> Blueprint -> point at this repo (reads render.yaml).
#    Before first deploy, set in the dashboard's Environment tab:
#      DATABASE_URL      = <the Neon connection string, postgresql+psycopg:// prefix>
#      CORS_ORIGINS      = ["https://app.grisshk.work"]

# 3. First deploy, then run the migration once via Render's Shell tab (or a one-off Job):
cd apps/api && uv run alembic check && uv run alembic upgrade head

# 4. Smoke check:
curl https://<service-name>.onrender.com/health
curl https://<service-name>.onrender.com/ready
```
Then point the frontend at it: set the `NEXT_PUBLIC_API_URL` GitHub Actions repository variable (currently the `https://api.grisshk.work` placeholder, `.github/workflows/pages.yml`) to the real Render URL, then re-run the Pages workflow (`output: "export"` bakes the URL in at build time, so the site must rebuild, not just the API redeploy). A custom `api.grisshk.work` domain pointed at Render via Cloudflare DNS works too, once the free-tier wake-up latency is judged acceptable for that URL.

Deploy order once both are live: migration (`alembic check && upgrade head`, run manually per above) → API redeploy → web rebuild → smoke checks (`.../health`, `.../ready`, then a real page load). Rollback: Render's dashboard keeps prior deploys one click away; forward-fix schema when a migration is not safely reversible, per the general rule below.

**Still undecided, unaffected by this choice:** secret manager beyond Render's own env vars, log/metric destination beyond Render's built-in dashboard, regional/data-residency constraints (picked Frankfurt only as a default near the founder, not a considered residency decision), backups/PITR policy on the Neon project.

Deploy order: backup/readiness checks → backward-compatible migration job → API → web → smoke checks. Rollback application images independently; forward-fix schema when a migration is not safely reversible.

## Web frontend: GitHub Pages (decided)

Unlike the API, `apps/web` *is* deployed — as a static export (`output: "export"` in `next.config.ts`) to GitHub Pages via `.github/workflows/pages.yml`, on every push to `main` that touches it. This was possible without picking a server host because the app was already architected to read all live data client-side against `NEXT_PUBLIC_API_URL` (see `lib/api/config.ts`) rather than server-rendering it — the httpOnly-cookie auth flow was already client-only for the same reason (`components/nav-user.tsx`).

Two routes that used to be server-rendered (`force-dynamic`) were converted to client components fetching in a `useEffect`, standard SPA-on-static-host pattern: `app/(app)/findings/page.tsx` and `app/(app)/datasets/page.tsx`. The finding detail route stopped being a `[id]` dynamic segment — static export requires every dynamic-segment value to be known via `generateStaticParams()` at build time, which an arbitrary finding ID can't be — and became `app/(app)/findings/detail/page.tsx`, reading `?id=` instead of a path segment.

Custom domain: `app.grisshk.work` (`apps/web/public/CNAME`, DNS on Cloudflare, registrar Spaceship). `NEXT_PUBLIC_API_URL` is a GitHub Actions repository variable, currently a placeholder (`https://api.grisshk.work`) since the API isn't hosted anywhere yet — the deployed site renders, but every data-fetching view shows a network error until that variable points at a real, CORS-enabled, publicly reachable API. Update the variable in place once the API decision above is made; no code or workflow change needed.
