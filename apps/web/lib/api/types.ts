/**
 * Types in this file are a hand-mirrored copy of the backend's Pydantic API
 * schemas (`apps/api/app/api/schemas.py`) and shared domain enums
 * (`packages/schemas/src/policy_schemas/domain.py`). There is no generated
 * client, so any change to those Python sources must be reflected here by
 * hand — see `apps/web/lib/api/README.md`.
 *
 * Do not add fields the backend does not send, and do not weaken a field's
 * type "just in case" — both hide real API contract drift instead of
 * surfacing it.
 */

// packages/schemas/src/policy_schemas/domain.py: FeatureTiming
export type FeatureTiming =
  | "identifier"
  | "decision_time"
  | "post_decision"
  | "outcome"
  | "metadata";

// packages/schemas/src/policy_schemas/domain.py: EvidenceLevel
// Fixed by ADR-005 — never rename, reorder, or invent a stronger-sounding
// label for these on the frontend.
export type EvidenceLevel =
  | "descriptive_observation"
  | "predictive_association"
  | "adjusted_observational_association"
  | "quasi_causal_evidence"
  | "experimental_evidence";

// packages/schemas/src/policy_schemas/domain.py: ResourceStatus
export type ResourceStatus = "pending" | "running" | "completed" | "failed" | "draft";

// packages/schemas/src/policy_schemas/domain.py: FindingLifecycleStatus
// Forward-only: ACTIVE -> SUPERSEDED, ACTIVE -> WITHDRAWN. Resolves HANDOFF-024.
export type FindingLifecycleStatus = "ACTIVE" | "SUPERSEDED" | "WITHDRAWN";

// packages/analytics/.../validation/contract.py: IdentificationDesign
export type IdentificationDesign =
  | "observational"
  | "quasi_experimental"
  | "randomized_prospective";

// packages/analytics/.../validation/contract.py: PolicyReadiness
export type PolicyReadiness = "not_ready" | "experiment_only" | "shadow_policy" | "high_confidence";

// packages/schemas/src/policy_schemas/domain.py: DatasetColumn
export type DatasetColumn = {
  name: string;
  data_type: string;
  timing: FeatureTiming;
  nullable: boolean;
};

// apps/api/app/api/schemas.py: DatasetRead
export type Dataset = {
  id: string;
  name: string;
  source_filename: string;
  version: number;
  status: ResourceStatus;
  checksum_sha256: string;
  size_bytes: number;
  content_type: string;
  source_type: string;
  columns: DatasetColumn[];
  created_at: string;
  updated_at: string;
};

// apps/api/app/api/schemas.py: EffectEstimateRead
// The four fields must never be displayed apart from each other — see
// docs/product/finding-product-contract.md §3/§5.
export type EffectEstimate = {
  value: number;
  ci_low: number;
  ci_high: number;
  confidence_level: number;
  method: string;
  unit: string;
};

// apps/api/app/api/schemas.py: FindingPatternRead
export type FindingPattern = {
  candidate_key: string;
  conditions: Record<string, unknown>[];
  fit_split: string;
  rank: number;
  rank_score: number;
  actionability: string;
};

// apps/api/app/api/schemas.py: FindingEvidenceRead
// raw_effect has no interval by construction — must always render with its
// "descriptive, unadjusted, no interval" qualifier, never styled as validated.
export type FindingEvidence = {
  raw_effect: EffectEstimate;
  adjusted_effect: EffectEstimate | null;
  controlled_variables: string[];
  potential_confounders: string[];
  robustness_tests: string[];
  temporal_stability: string;
  warnings: string[];
  failure_modes: string[];
  recommended_validation: string;
  permitted_language: string;
};

// apps/api/app/api/schemas.py: FindingImpactRead
// materiality_pass is pass/fail only — the underlying threshold is never
// exposed (still a Statistics/Customer-Discovery-owned placeholder, §3).
export type FindingImpact = {
  impact_contract_version: string;
  outcome_name: string;
  outcome_unit: string;
  affected_records: number;
  per_record_effect: EffectEstimate;
  historical_impact: EffectEstimate;
  annualized_impact: EffectEstimate | null;
  annualization_justified: boolean;
  materiality_pass: boolean;
};

// apps/api/app/api/schemas.py: FindingRead
export type Finding = {
  id: string;
  dataset_id: string;
  analysis_run_id: string;
  candidate_pattern_id: string;
  validation_report_id: string;
  title: string;
  summary: string;
  title_template_version: string;
  generated_at: string;
  pattern: FindingPattern;
  exposed_records: number;
  comparison_records: number;
  clustering_key: string;
  evidence_level: EvidenceLevel;
  identification_design: IdentificationDesign;
  evidence: FindingEvidence;
  impact: FindingImpact;
  policy_readiness: PolicyReadiness;
  lifecycle_status: FindingLifecycleStatus;
  created_at: string;
  updated_at: string;
};

// apps/api/app/api/schemas.py: HealthResponse
export type HealthStatus = {
  status: string;
};
