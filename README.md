# Decision harm discovery

Discovers business decision patterns that are followed by economic harm, grades the evidence behind
each pattern, and turns credible findings into reviewable policy candidates. Every number comes from
deterministic, tested code. Discovery runs against frozen, hash-verified engines; benchmark runs are
pre-registered and blind.

The repository contains the full system: the discovery engine, the 17-gate validation contract,
synthetic benchmarks with planted ground truth, the API and web application, and the evidence
behind every reported result.

## Results

All results below come from the frozen engine `discovery-engine-v0.6.2` on benchmark v2: 11
oracle-qualified planted mechanisms, 20 targets planted together per draw, and 30 fresh evaluation
seeds.

| Question | Finding | Evidence |
|---|---|---|
| How much does the engine recover? | Covers 10.8 of 11 targets per seed but localises 2.9 (95% seed-bootstrap interval 2.6–3.2). Only 1 of 11 targets is localised on all 30 seeds. | [`task-109`](docs/benchmark/task-109-first-blind-engine-run-results.md) |
| Why is lenient recall misleading? | A rule matches a pattern if it covers half of the pattern's affected rows. Under that criterion one broad rule (`discount_rate >= 0.05 AND manual_exception = false`, 63% of bookings) is credited with all 11 targets at exposure Jaccard 0.113. | [`task-109` seed 4001](docs/benchmark/task-109-evidence/engine-raw/seed-4001.json), [`task-110`](docs/benchmark/task-110-specific-recovery-autopsy.md) |
| What causes the failures? | Each rule is compared with all other bookings, and that complement carries the other planted effects. With common random numbers, the share of true literals with the wrong sign rises from 5.8% (target planted alone) to 31.1% (composite), out of 840 literal-seed pairs. | [`complement-contamination-evidence`](docs/benchmark/complement-contamination-evidence/) |
| Where is the right rule lost? | It is always generated and scored, and then lost at final top-15 selection. Overriding that one step restores it on 119 of 127 target-seeds. | [`task-117`](docs/benchmark/task-117-trajectory-results.md) |
| Can the score's size exponent fix it? | No. Specific recovery peaks at the default α = 0.5 (2.83 of 11) and falls on both sides: noise pockets at small α, multi-target unions at large α. | [`complement-contamination-evidence`](docs/benchmark/complement-contamination-evidence/) |
| Can a gate tell interaction from proxy confounding? | Not from a rule and the data alone. Under pure confounding the false "interaction" rate rises from 0.07 (n = 300) to 1.00 (n = 2,400). | [`task-080`](docs/analytics/task-080-candidate-composition-safety-design.md) |
| Does it work on real data? | On the public Olist e-commerce data, 0 of 53 graded candidates rose above descriptive observation. | [`task-100`](docs/benchmark/task-100-sample-size-detectability-results.md) |

Each `docs/benchmark/task-*` result has a matching `*-evidence/` directory or `*-raw.json` file with
the scripts and raw outputs that produced it.

## Architecture

A modular monolith. A Next.js web app calls a FastAPI API backed by PostgreSQL. API routes delegate
to services, and persistence and API contracts are separate. Deterministic analytics (ingestion,
profiling, discovery, validation, ranking, benchmarks) live in an independent Python package. See
[ARCHITECTURE.md](ARCHITECTURE.md).

```text
apps/api                    FastAPI application, persistence, migrations
apps/web                    Next.js application
packages/analytics          discovery engine, validation contract, benchmark generators and scorers
packages/schemas            shared domain types
tools/blind_agent, blind/   isolated, signed blind-evaluation runner
scripts                     reproducible pipeline and diagnostic entry points
synthetic_data*             frozen synthetic benchmarks (no real customer data)
docs                        contracts, protocols and results (see docs/README.md)
tests                       unit, integration and benchmark tests
infra                       container images
```

## Running locally

Requirements: Docker with Compose, or Python 3.12+ with `uv`, Node.js 22+ and pnpm 10+.

```sh
make setup      # creates .env from .env.example and installs locked dependencies
make dev        # web on :3000, API/OpenAPI on :8000/docs, PostgreSQL on :5432
make test
make lint
make typecheck
```

For host processes, point `DATABASE_URL` at `localhost`, run `cd apps/api && uv run alembic upgrade head`,
then `PYTHONPATH=apps/api:packages/schemas/src:packages/analytics/src uv run uvicorn app.main:app --reload`
and `pnpm --filter web dev`. Schema changes go through committed Alembic migrations only
(`make db-migrate m=<name>`).

## Reproducing a result

Evidence scripts import the frozen engine directly. The blind-run and trajectory scripts also refuse
to run if `engine.py` does not match its recorded SHA-256. For example:

```sh
cd packages/analytics
uv run python ../../docs/benchmark/task-117-evidence/trajectory.py seed --seed 4001 --out /tmp/seed-4001.json
uv run python ../../docs/benchmark/complement-contamination-evidence/contamination.py run --seeds 4001 4030 --out /tmp/crn.json
```

## Notes on this repository

The history preserves every original commit and its date. Internal planning material is not
included: the task registry, decision log, role definitions, working notes, and business and customer
documents. Some result documents therefore cite task (`TASK-…`), decision (`ADR-…`) or handoff
(`HANDOFF-…`) identifiers that have no file here. Absolute local paths in committed evidence were
normalised to `<repo>` and `<scratch>`, and the hashes recorded for the affected scripts were
updated to match.
