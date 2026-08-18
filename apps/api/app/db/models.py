import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DatasetModel(TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_datasets_name_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: TASK-009. Single JSONB document
    #: (`policy_analytics.profiling.quality_report.DataQualityReport` via `dataclasses.asdict`)
    #: rather than a relational table — it is read/written as one unit,
    #: never queried column-by-column, matching `ValidationReportModel`'s own precedent for
    #: versioned diagnostic documents. `NULL` means profiling/classification did not complete for
    #: this dataset version (upload still succeeded — see `TASK-006`'s guarantee).
    quality_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    analysis_runs: Mapped[list["AnalysisRunModel"]] = relationship(back_populates="dataset")
    column_profiles: Mapped[list["DatasetColumnProfileModel"]] = relationship(
        back_populates="dataset"
    )


class DatasetColumnProfileModel(TimestampMixin, Base):
    """One row per profiled column (TASK-007). Deliberately separate from `DatasetModel.columns`
    (`DatasetColumn`: name/data_type/timing/nullable) — that JSONB field is TASK-008's eventual
    feature-timing-classification output, a different pipeline stage. Written once per dataset
    version, never updated (`policy_analytics.profiling.schema_profiler` is the pure computation).
    """

    __tablename__ = "dataset_column_profiles"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "column_name", name="uq_dataset_column_profiles_dataset_column"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    column_name: Mapped[str] = mapped_column(String(128), nullable=False)
    inferred_type: Mapped[str] = mapped_column(String(16), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missingness: Mapped[float] = mapped_column(Float, nullable=False)
    distinct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    min_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    semantic_type_guess: Mapped[str] = mapped_column(String(32), nullable=False)
    examples: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    examples_suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suspicious_values: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    suspicious_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    dataset: Mapped[DatasetModel] = relationship(back_populates="column_profiles")


class AnalysisRunModel(TimestampMixin, Base):
    """The reproducibility envelope for one discovery search.

    See `docs/architecture/finding-persistence-contract.md`. `lineage` is a JSONB list of
    `LineageReference`-shaped objects (v0 simplification: no separate relational lineage table,
    see `TASK-024` scope notes).
    """

    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    analytical_dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    analytical_dataset_identity_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    code_version: Mapped[str] = mapped_column(String(100), nullable=False)
    discovery_methodology_version: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome_definition_version: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_hypotheses: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    lineage: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    dataset: Mapped[DatasetModel] = relationship(back_populates="analysis_runs")
    candidate_patterns: Mapped[list["CandidatePatternModel"]] = relationship(
        back_populates="analysis_run"
    )
    findings: Mapped[list["FindingModel"]] = relationship(back_populates="analysis_run")


class CandidatePatternModel(TimestampMixin, Base):
    """An immutable discovery result. Append-only: re-specifying a condition creates a new row."""

    __tablename__ = "candidate_patterns"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "candidate_key", name="uq_candidate_patterns_run_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    candidate_key: Mapped[str] = mapped_column(String(128), nullable=False)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    fit_split: Mapped[str] = mapped_column(String(32), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    rank_score: Mapped[float] = mapped_column(Float, nullable=False)
    actionability: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    persisted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lineage: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    analysis_run: Mapped[AnalysisRunModel] = relationship(back_populates="candidate_patterns")
    validation_reports: Mapped[list["ValidationReportModel"]] = relationship(
        back_populates="candidate_pattern"
    )


class ValidationReportModel(TimestampMixin, Base):
    """An immutable snapshot of the Statistics-owned validation report. Revalidation under another
    contract creates another row; a rejected report (`evidence_level IS NULL`) cannot promote."""

    __tablename__ = "validation_reports"
    __table_args__ = (
        UniqueConstraint(
            "candidate_pattern_id",
            "contract_version",
            "outcome_definition_version",
            name="uq_validation_reports_candidate_contract_outcome",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_pattern_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_patterns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_definition_version: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_definition: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exposed_records: Mapped[int] = mapped_column(Integer, nullable=False)
    comparison_records: Mapped[int] = mapped_column(Integer, nullable=False)
    clustering_key: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_effect: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    adjusted_effect: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    adjusted_p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    family_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    controlled_variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    potential_confounders: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    robustness_tests: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    temporal_stability: Mapped[str] = mapped_column(Text, nullable=False, default="")
    identification_design: Mapped[str] = mapped_column(String(32), nullable=False)
    gate_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    evidence_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_readiness: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_modes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    recommended_validation: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    permitted_language: Mapped[str] = mapped_column(Text, nullable=False)
    lineage: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    candidate_pattern: Mapped[CandidatePatternModel] = relationship(
        back_populates="validation_reports"
    )


class FindingModel(TimestampMixin, Base):
    """A promoted, validated candidate plus its economic-impact snapshot.

    Read-optimized by design: `pattern_snapshot`/`validation_snapshot`/`impact_snapshot` are
    derived, immutable copies from the referenced candidate/report at promotion time
    (`docs/architecture/finding-persistence-contract.md`: "derived snapshots ... for safe reads,
    never independently authored inputs") so `GET /api/v1/findings` never needs a 3-table join.
    """

    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    candidate_pattern_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_patterns.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    validation_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_reports.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    title_template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pattern_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    exposed_records: Mapped[int] = mapped_column(Integer, nullable=False)
    comparison_records: Mapped[int] = mapped_column(Integer, nullable=False)
    clustering_key: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(64), nullable=False)
    identification_design: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    impact_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    impact_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_readiness: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    superseded_by_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True
    )
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    lineage: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    analysis_run: Mapped[AnalysisRunModel] = relationship(back_populates="findings")


class PolicyCandidateModel(TimestampMixin, Base):
    __tablename__ = "policy_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    rule_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")


class UserModel(TimestampMixin, Base):
    """Internal staff account (`TASK-053`) — not a customer account, not multi-tenant.

    No self-serve signup: rows are created only via `scripts/create_user.py`.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)


class SessionModel(Base):
    """A DB-backed opaque session — real, immediate revocation on logout, no signing secret.

    No `TimestampMixin`: a session is never updated after creation, only deleted.
    """

    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FindingFeedbackModel(TimestampMixin, Base):
    """A single append-only reviewer capture.

    `TASK-035`, `docs/product/finding-feedback-contract.md`. Never updated after insert (§5);
    never a write path to `FindingModel.evidence_level`/
    `policy_readiness` (§7) — this table has no code path that touches `findings` at all.
    """

    __tablename__ = "finding_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    review_session: Mapped[str] = mapped_column(String(256), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    novelty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actionability: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    customer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_certainty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    intended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    commitment_strength: Mapped[str | None] = mapped_column(String(32), nullable=True)
    customer_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    internal_follow_up_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
