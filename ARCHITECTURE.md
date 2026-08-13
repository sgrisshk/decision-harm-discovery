# Architecture

## Shape and dependency direction

The deployable system is deliberately a modular monolith: Next.js → FastAPI → application services → repositories/SQLAlchemy → PostgreSQL. API routes contain transport concerns only. `packages/analytics` contains deterministic transformations and may depend on shared domain definitions, never on FastAPI or ORM models. API Pydantic schemas and database models are separate. `packages/schemas` stays small and contains only genuinely shared domain concepts.

## Data lifecycle and invariants

1. **Raw data is immutable.** Customer uploads are content-addressed/versioned and never edited. The reproducible path is raw → normalized → analytical dataset. Every transformation records its inputs, configuration, and code version.
2. **No analytical logic in routes.** Routes validate requests, call a service, and serialize responses. Cleaning, features, statistics, discovery, and impact logic live outside the transport layer.
3. **Deterministic analytics.** Every analysis run records dataset ID/version, code/model version, typed configuration, random seed, timestamp, findings, and validation metrics. Randomized code must accept a seed.
4. **Anti-leakage boundary.** Columns are classified as decision-time features, post-decision events, outcomes, identifiers, or metadata. Anything first observed after the decision timestamp is excluded from explanatory features unless an explicit, reviewed analysis says otherwise.
5. **generative model boundary.** generative models may assist semantic mapping, interpretation, explanations, and hypotheses. They are never the source of truth for arithmetic, statistics, causal estimates, financial calculations, eligibility, or policy backtests. Every number originates in deterministic code.
6. **Findings are first-class.** The model supports pattern definition, sample/support, raw and adjusted effects, uncertainty, estimated impact, evidence level, stability, warnings, status, and lineage/evidence references. The bootstrap stores a minimal subset without pre-empting the validation design.
7. **No causal overclaiming.** Evidence vocabulary is: descriptive observation, predictive association, adjusted observational association, quasi-causal evidence, experimental evidence. Association is never automatically called causal.
8. **Traceability.** A finding must be linkable to the run, dataset version, configuration, and supporting record references. Detailed evidence storage will be designed before discovery is implemented.
9. **Configuration over constants.** Operational and analytical thresholds use typed settings/configuration, never scattered magic numbers.
10. **Simple deployment first.** Next.js + FastAPI + PostgreSQL remains the default until measured needs justify another component.

## Domain and persistence

`Dataset`, `DatasetColumn`, `AnalysisRun`, `Finding`, and `PolicyCandidate` are domain/API primitives. The initial database tables are datasets, analysis_runs, findings, and policy_candidates; dataset column metadata is stored as validated JSON until its query/access requirements justify a table. UUID primary keys and timezone-aware timestamps are mandatory. Schema changes happen only through committed Alembic migrations. Production migrations should be backward-compatible; destructive changes require separate review and an explicit rollback/data-preservation plan.

## Security and errors

Configuration comes from environment variables or a secret manager. Production refuses missing/unsafe critical configuration. CORS is explicit, debug is off, request logs contain metadata—not payloads—and unhandled errors return a request ID without internals. Authentication has a future dependency boundary at the route/application edge; no fake auth is included.

## Agent collaboration and memory boundary

Repository knowledge has distinct sources of truth:

- `PROJECT_CONTEXT.md` contains stable product thesis, scope, and terminology.
- `ARCHITECTURE.md` contains current technical boundaries and invariants.
- `DECISIONS.md` is the append-only record of deliberate durable choices.
- `TASKS.md` contains actionable work and ownership.
- `agents/` defines specialist authority and mandatory handoff boundaries.
- `memory/` contains compact durable state, experiments, validated findings, open questions, and cross-role handoffs.

Conversation transcripts, debugging notes, generated claims, and implementation details obvious from code do not belong in memory. Memory never overrides the source-of-truth hierarchy in `engineering rules` and must never contain secrets, PII, or customer rows.
