# Finding persistence contract preparation

**Scope:** TASK-024 preparation; no migration or route is activated by this document.

## Problem

The initial schema stores a minimal `Finding` directly under `AnalysisRun`. Discovery now emits
immutable candidates and Statistics defines a separate `ValidationReport`. Persisting a candidate
as a Finding before validation would erase this boundary and allow unvalidated associations onto
the product read path.

## Current architecture

- `analysis_runs` stores a dataset FK, integer source version, code version, arbitrary
  configuration, seed, and job status.
- `findings` stores a pattern, sample size, evidence string, warnings, and generic resource status.
- There is no candidate table, validation-report table, artifact lineage table, analytical dataset
  identity, outcome/contract versions, or promotion invariant.
- `ValidationReport` is the Statistics-owned executable validation output.
- TASK-023 has not delivered an executable economic-impact result yet.

## Proposed domain boundary

```text
AnalysisRun 1 ── * CandidatePattern 1 ── 0..1 ValidationReport 1 ── 0..1 Finding
     │                    │                       │                    │
     └──────────── immutable lineage artifact references ────────────┘
```

1. `AnalysisRun` is the reproducibility envelope for one discovery search. It pins source dataset
   ID/version, analytical dataset version and SHA-256 identity, code/methodology versions, outcome
   and validation contract versions, typed configuration, seed, evaluated-hypothesis count, and
   lineage artifacts.
2. `CandidatePattern` is an immutable discovery result. Conditions, fit split, rank inputs,
   per-split descriptive metrics, warnings, artifact hash, and persisted timestamp are append-only.
   Re-specifying a condition creates a new candidate; it never updates the existing row.
3. `ValidationReport` is an immutable snapshot of the Statistics-owned report. Revalidation under
   another contract creates another report row. Rejected reports (`evidence_level IS NULL`) remain
   auditable but cannot produce a Finding.
4. `Finding` is a promoted, validated candidate plus a TASK-023 economic-impact snapshot. It is
   created transactionally only when the referenced validation report has non-null evidence and
   the impact result is present. A database FK prevents a Finding without both source objects; the
   service enforces the semantic promotion checks.

## Database schema proposal

### Extend `analysis_runs`

- `analytical_dataset_version varchar(128) NOT NULL`
- `analytical_dataset_identity_sha256 char(64) NOT NULL`
- `discovery_methodology_version varchar(128) NOT NULL`
- `outcome_definition_version varchar(64) NOT NULL`
- `validation_contract_version varchar(64) NOT NULL`
- `evaluated_hypotheses integer NOT NULL CHECK (> 0)`
- retain `dataset_id`, source `dataset_version`, `code_version`, `configuration`, `random_seed`,
  and job-oriented `status`.

### New `candidate_patterns`

- UUID PK; `analysis_run_id` FK `RESTRICT`;
- `candidate_key varchar(128)` unique within a run;
- `conditions jsonb`, `fit_split`, rank/rank score/actionability;
- `metrics jsonb`, `warnings jsonb`;
- `artifact_sha256 char(64)`, `persisted_at timestamptz`;
- immutable after insert at the application/repository boundary.

### New `validation_reports`

- UUID PK; `candidate_pattern_id` FK `RESTRICT`;
- contract/outcome versions and `generated_at`;
- exposed/comparison counts and clustering key;
- raw and adjusted effects as typed JSON snapshots;
- adjusted p-value/family size;
- identification design, nullable evidence level, policy readiness;
- gate results, controlled variables, potential confounders, robustness tests, temporal stability,
  failure modes, recommended validation, warnings, permitted language;
- unique `(candidate_pattern_id, contract_version, outcome_definition_version)`.

The report remains JSON-heavy deliberately: gates and robustness diagnostics evolve as a versioned
document and are read as a unit. Frequently filtered identity/status/version fields remain scalar
columns with indexes/check constraints. Pydantic validates the JSON shape before persistence.

### Replace the minimal shape of `findings`

- retain UUID PK, `dataset_id`, `analysis_run_id`;
- add unique `candidate_pattern_id` and unique `validation_report_id`, both `RESTRICT` FKs;
- add `impact_snapshot jsonb NOT NULL`, `impact_contract_version`, `generated_at`;
- keep deterministic title/pattern summary fields only after Product supplies their template;
- replace generic `ResourceStatus` with the Product-owned finding lifecycle enum when resolved;
- evidence, warning, and lineage values are derived snapshots from the referenced validation report
  for safe reads, never independently authored inputs.

### New `lineage_artifacts` and owner joins

`lineage_artifacts(id, kind, uri, sha256, version, created_at)` has a uniqueness constraint on
`(kind, sha256)`. Explicit join tables (`analysis_run_lineage`, `candidate_lineage`,
`validation_report_lineage`, `finding_lineage`) retain real foreign keys; avoid a polymorphic
`owner_type/owner_id` pair without referential integrity. URIs point to immutable artifacts and
must not embed credentials, customer rows, or local secrets.

## Pydantic contracts

Preparation schemas live in `apps/api/app/findings/contracts.py`:

- `AnalysisRunPersistence`
- `CandidatePatternPersistence`
- `ValidationMetadataPersistence`
- `EconomicImpactPersistence`
- `FindingPromotion`
- typed effect, gate, condition, metric, and lineage submodels

They are frozen and reject extra fields. `FindingPromotion` rejects a report with no evidence
level; annualized impact is structurally forbidden unless `annualization_justified=true`.
`EconomicImpactPersistence` is a storage envelope only: Statistics still owns how every value is
computed and must replace the provisional impact contract version when TASK-023 is implemented.

## API and application boundaries

- Public API may create/read `AnalysisRun`; arbitrary candidate/finding creation is not exposed.
- Discovery writes through an internal candidate persistence service that verifies run identity,
  candidate artifact SHA-256, bundle receipt, dataset identity, and uniqueness in one transaction.
- Statistics writes through an internal validation persistence service accepting the sanctioned
  `ValidationReport` serialization. The service rehydrates/validates the executable report before
  insert; caller-provided evidence text alone is never trusted.
- A promotion service accepts candidate ID, validation report ID, and impact report. It locks the
  rows, verifies common run/dataset identity, non-null evidence, version compatibility and lineage,
  then inserts exactly one Finding transactionally.
- `GET /api/v1/findings` and detail endpoints query only `findings`, never candidates. Candidate and
  validation audit endpoints, if later needed, are separate and non-customer-facing.
- Evidence-bounded copy is selected in the service/serializer from the persisted evidence enum and
  `LANGUAGE_RULES`; the client never submits permitted wording.

## Migration plan

1. Add nullable run-envelope columns and create candidate, validation, lineage, and join tables.
2. Backfill existing analysis runs only where exact versions/hashes are known. No production
   Findings exist today; do not fabricate candidate or validation lineage for seed/test rows.
3. Add checks/indexes and make run-envelope columns non-null after backfill verification.
4. Add candidate/report FKs and new impact/lifecycle columns to `findings` as nullable.
5. Deploy dual-read code only if real legacy findings exist; current repository evidence says none.
6. After Product resolves lifecycle and TASK-023 fixes impact shape, migrate/verify any test data,
   make new Finding columns non-null, switch reads, then remove obsolete minimal columns in a later
   destructive migration with an explicit rollback/data-preservation review.

Every step is a committed Alembic revision. Destructive cleanup is deliberately separated from
additive deployment. Rollback of additive phases drops only new empty structures; rollback after
data migration requires exporting retained rows first.

## Security and privacy

- Store hashes and immutable URIs, not raw record evidence or customer rows.
- Do not log conditions containing values unless the canonical schema marks them safe; request logs
  remain metadata-only.
- JSON sizes receive application limits; database statements remain parameterized through
  SQLAlchemy.
- UUIDs do not provide authorization. Authentication/tenant isolation remain separate future
  boundaries and must be added before external multi-customer use.

## Dependency and migration impact

No new runtime dependency or infrastructure is proposed. PostgreSQL/JSONB and existing Pydantic,
SQLAlchemy, and Alembic are sufficient. API depends on approved analytics contracts for internal
ingestion but analytics never depends on API/ORM models.

## Alternatives considered

- Store candidates directly as draft Findings: rejected because it violates the validation gate.
- One JSON document for the whole run: rejected because identity, uniqueness, FK integrity, and
  candidate/report promotion become unenforceable.
- Fully normalize every gate/effect field: premature; reports are versioned immutable snapshots and
  currently read together.
- Event sourcing or another datastore: unnecessary infrastructure for current scale.

## Blockers before migration implementation

1. TASK-020 must produce classified validation reports for real candidates.
2. TASK-023 must finalize and implement the economic-impact result shape and version.
3. Product must approve the Finding lifecycle enum and deterministic summary/title behavior
   (`HANDOFF-017`).
4. Code Reviewer must review the eventual migration and promotion invariant before shipment.
