# Outcome-driven policy discovery

A production-oriented monorepo foundation for discovering harmful business decision patterns from historical decisions and downstream economic outcomes. Numerical and statistical truth remains deterministic; explainability and future generative model assistance sit outside calculations.

## Architecture

The MVP is a modular monolith: a Next.js web app calls a FastAPI API backed by PostgreSQL. API routes delegate to services; persistence and API contracts are separate; deterministic analytics live in an independent Python package. See [ARCHITECTURE.md](ARCHITECTURE.md) and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

## Requirements

- Docker Desktop/Engine with Compose (recommended local path)
- Or Python 3.12+, `uv`, Node.js 22+, and pnpm 10+

## Setup and local run

```sh
make setup
make dev
```

`make setup` creates `.env` from the documented example if absent and installs locked dependencies. Compose exposes web at http://localhost:3000, API/OpenAPI at http://localhost:8000/docs, and PostgreSQL at localhost:5432. The API container applies migrations before starting.

For host processes, point `DATABASE_URL` at `localhost` instead of Compose service `postgres`, then run `cd apps/api && uv run alembic upgrade head`, `PYTHONPATH=apps/api:packages/schemas/src:packages/analytics/src uv run uvicorn app.main:app --reload`, and `pnpm --filter web dev` from the repository root.

## Quality and tests

```sh
make test
make lint
make typecheck
make format
pnpm --filter web build
make docker-build
```

Fast unit/API tests use dependency overrides; PostgreSQL integration tests run when `TEST_DATABASE_URL` is set. CI supplies it. Heavy future analytics tests must use separate markers/jobs.

## Database migrations

```sh
make db-upgrade
make db-migrate m=add_column_name
```

Only committed Alembic migrations may change schema. Never edit a production database manually.

## Environment

Copy `.env.example` to `.env`. `DATABASE_URL`, `APP_ENV`, `LOG_LEVEL`, `API_HOST`, `API_PORT`, `CORS_ORIGINS`, `MAX_UPLOAD_BYTES`, and `NEXT_PUBLIC_API_URL` are documented there. Local credentials are disposable defaults only. Production requires an explicit non-default database URL, HTTPS CORS origins, and externally managed secrets.

## Repository map

```text
apps/api       FastAPI application, persistence, migrations
apps/web       Next.js application
packages/      deterministic analytics and shared domain types
agents         specialist role contracts and authority boundaries
memory         durable state, handoffs, experiments, findings, open questions
infra/docker   production-capable images
tests          backend tests and synthetic fixtures
docs           domain-grouped architecture, analytics, benchmark, customer, product, strategy, and operations documents
scripts        reproducible developer utilities
data           ignored local data (never customer data in Git)
```

Read `engineering rules` before agent-assisted changes, then the applicable role contract and current memory. `DECISIONS.md` records durable choices. See `CONTRIBUTING.md` for the PR workflow and `SECURITY.md` before handling enterprise data.
