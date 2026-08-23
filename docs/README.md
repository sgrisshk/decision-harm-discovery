# Documentation Map

The repository root is reserved for documents every contributor or agent must discover immediately. All scoped documents belong under `docs/` by domain.

## Root documents

Only these Markdown files should normally live at repository root:

- `README.md` — project entry point and local setup;
- `engineering rules` — mandatory agent operating rules;
- `PROJECT_CONTEXT.md` — stable product context;
- `ARCHITECTURE.md` — current architecture and invariants;
- `DECISIONS.md` — append-only durable decisions;
- `TASKS.md` — task registry;
- `CONTRIBUTING.md` — contribution workflow;
- `SECURITY.md` — security policy.

Adding another root Markdown file requires an explicit reason and Architect review.

## Placement rules

| Directory | Content |
|---|---|
| `docs/architecture/` | Persistence contracts, technical component boundaries, architecture-specific specifications |
| `docs/analytics/` | Outcome, discovery, validation, feature, impact, and statistical methodology contracts |
| `docs/benchmark/` | Synthetic benchmark protocols, simulation reports, evaluation criteria, decision gates |
| `docs/customer/` | Customer acquisition, pipeline, interviews, review protocols, prospect research |
| `docs/product/` | Finding/policy contracts, UX specifications, screen behavior and copy rules |
| `docs/strategy/` | Validation plans, company-level operating plans, scoped strategic documents |
| `docs/operations/` | Deployment, runbooks, observability, backup/restore, operational procedures |

Role definitions belong in `agents/`. Durable working memory belongs in `memory/`. Dataset-local documentation stays next to the corresponding synthetic/test dataset. Package-specific documentation may stay inside that package when it explains only that package.

## Naming

Use lowercase kebab-case for new files under `docs/`; an analytics contract should follow the pattern `docs/analytics/<topic>-contract.md`. Prefer one authoritative document over suffixed copies such as `FINAL`, `NEW`, or `v2`; version the contract in its contents and decision log.

When moving or renaming a document, update all code, task, decision, handoff, memory, and Markdown references in the same change. Do not leave compatibility copies in the root because they recreate two apparent sources of truth.

## Current index

### Architecture

- `docs/architecture/canonical-schema-contract.md`
- `docs/architecture/finding-persistence-contract.md`
- `docs/architecture/ingestion-contract.md`

### Analytics

- `docs/analytics/discovery-design.md`
- `docs/analytics/discovery-engine-v0.md`
- `docs/analytics/outcome-contract.md`
- `docs/analytics/validation-contract.md`

### Benchmark

- `docs/benchmark/blind-benchmark-protocol.md`
- `docs/benchmark/decision-gate.md`
- `docs/benchmark/difficulty-presets.md`
- `docs/benchmark/multi-domain-benchmarks.md`
- `docs/benchmark/simulation-report.md`
- `docs/benchmark/task-068-ecommerce-preregistration.md`

### Customer

- `docs/customer/acquisition-sprint-7day.md`
- `docs/customer/data-acquisition-plan.md`
- `docs/customer/findings-review-protocol.md`
- `docs/customer/pipeline.md`
- `docs/customer/prospect-target-list.md`

### Product

- `docs/product/finding-detail-screen.md`
- `docs/product/finding-product-contract.md`
- `docs/product/findings-list-screen.md`

### Strategy

- `docs/strategy/30-day-validation-plan.md`
- `docs/strategy/founder-narrative.md`

### Operations

- `docs/operations/deployment.md`
