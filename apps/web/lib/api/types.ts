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

// apps/api/app/api/schemas.py: FindingRead
// This is intentionally the current minimal skeleton (TASK-002). Raw/adjusted
// effect, uncertainty, impact, stability, and confounder-check fields do not
// exist on the API yet (tracked by TASK-024/TASK-025); do not add them here
// ahead of the backend.
export type Finding = {
  id: string;
  dataset_id: string;
  analysis_run_id: string;
  title: string;
  pattern_definition: Record<string, unknown>;
  sample_size: number;
  evidence_level: EvidenceLevel;
  status: ResourceStatus;
  warnings: string[];
  created_at: string;
  updated_at: string;
};

// apps/api/app/api/schemas.py: HealthResponse
export type HealthStatus = {
  status: string;
};
