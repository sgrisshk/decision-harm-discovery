"""Real Finding persistence: candidate patterns, validation reports, promoted findings.

TASK-024. Extends `analysis_runs` with the reproducibility envelope
(`docs/architecture/finding-persistence-contract.md`); adds `candidate_patterns` and
`validation_reports`; replaces the TASK-002 minimal `findings` skeleton with the real,
read-optimized shape. No production Finding data exists yet (`ARCHITECTURE.md`), so this is a
straight drop/recreate rather than a staged nullable-then-backfill migration.

`policy_candidates.finding_id` FKs to `findings.id`; since that table is also confirmed empty, it
is dropped and recreated identically around the `findings` rebuild rather than juggling constraint
drop/add order.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0003"
down_revision: str | None = "20260816_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _create_policy_candidates() -> None:
    op.create_table(
        "policy_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("rule_definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_candidates_finding_id", "policy_candidates", ["finding_id"])


def upgrade() -> None:
    # --- analysis_runs: reproducibility envelope -------------------------------------------
    op.add_column(
        "analysis_runs",
        sa.Column("analytical_dataset_version", sa.String(length=128), nullable=False),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("analytical_dataset_identity_sha256", sa.String(length=64), nullable=False),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("discovery_methodology_version", sa.String(length=128), nullable=False),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("outcome_definition_version", sa.String(length=64), nullable=False),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("validation_contract_version", sa.String(length=64), nullable=False),
    )
    op.add_column(
        "analysis_runs", sa.Column("evaluated_hypotheses", sa.Integer(), nullable=False)
    )
    op.add_column(
        "analysis_runs",
        sa.Column(
            "lineage",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.alter_column("analysis_runs", "lineage", server_default=None)

    # --- drop policy_candidates, findings (both confirmed empty) ---------------------------
    op.drop_index("ix_policy_candidates_finding_id", table_name="policy_candidates")
    op.drop_table("policy_candidates")
    op.drop_index("ix_findings_analysis_run_id", table_name="findings")
    op.drop_index("ix_findings_dataset_id", table_name="findings")
    op.drop_table("findings")

    # --- candidate_patterns ------------------------------------------------------------------
    op.create_table(
        "candidate_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_key", sa.String(length=128), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fit_split", sa.String(length=32), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("rank_score", sa.Float(), nullable=False),
        sa.Column("actionability", sa.String(length=64), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("persisted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lineage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"], ["analysis_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_run_id", "candidate_key", name="uq_candidate_patterns_run_key"
        ),
    )
    op.create_index(
        "ix_candidate_patterns_analysis_run_id", "candidate_patterns", ["analysis_run_id"]
    )

    # --- validation_reports --------------------------------------------------------------------
    op.create_table(
        "validation_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_pattern_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column("outcome_definition_version", sa.String(length=64), nullable=False),
        sa.Column("outcome_definition", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exposed_records", sa.Integer(), nullable=False),
        sa.Column("comparison_records", sa.Integer(), nullable=False),
        sa.Column("clustering_key", sa.String(length=128), nullable=False),
        sa.Column("raw_effect", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("adjusted_effect", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("adjusted_p_value", sa.Float(), nullable=True),
        sa.Column("family_size", sa.Integer(), nullable=True),
        sa.Column(
            "controlled_variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "potential_confounders", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("robustness_tests", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("temporal_stability", sa.Text(), nullable=False),
        sa.Column("identification_design", sa.String(length=32), nullable=False),
        sa.Column("gate_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_level", sa.String(length=64), nullable=True),
        sa.Column("policy_readiness", sa.String(length=32), nullable=False),
        sa.Column("failure_modes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recommended_validation", sa.Text(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("permitted_language", sa.Text(), nullable=False),
        sa.Column("lineage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["candidate_pattern_id"], ["candidate_patterns.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_pattern_id",
            "contract_version",
            "outcome_definition_version",
            name="uq_validation_reports_candidate_contract_outcome",
        ),
    )
    op.create_index(
        "ix_validation_reports_candidate_pattern_id",
        "validation_reports",
        ["candidate_pattern_id"],
    )

    # --- findings: real shape ------------------------------------------------------------------
    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_pattern_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("validation_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("title_template_version", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pattern_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exposed_records", sa.Integer(), nullable=False),
        sa.Column("comparison_records", sa.Integer(), nullable=False),
        sa.Column("clustering_key", sa.String(length=128), nullable=False),
        sa.Column("evidence_level", sa.String(length=64), nullable=False),
        sa.Column("identification_design", sa.String(length=32), nullable=False),
        sa.Column(
            "validation_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("impact_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("impact_contract_version", sa.String(length=64), nullable=False),
        sa.Column("policy_readiness", sa.String(length=32), nullable=False),
        sa.Column(
            "lifecycle_status", sa.String(length=16), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("superseded_by_finding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("withdrawal_reason", sa.Text(), nullable=True),
        sa.Column("lineage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["candidate_pattern_id"], ["candidate_patterns.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["validation_report_id"], ["validation_reports.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_finding_id"], ["findings.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_pattern_id", name="uq_findings_candidate_pattern_id"),
        sa.UniqueConstraint("validation_report_id", name="uq_findings_validation_report_id"),
    )
    op.alter_column("findings", "lifecycle_status", server_default=None)
    op.create_index("ix_findings_dataset_id", "findings", ["dataset_id"])
    op.create_index("ix_findings_analysis_run_id", "findings", ["analysis_run_id"])

    _create_policy_candidates()


def downgrade() -> None:
    op.drop_index("ix_policy_candidates_finding_id", table_name="policy_candidates")
    op.drop_table("policy_candidates")

    op.drop_index("ix_findings_analysis_run_id", table_name="findings")
    op.drop_index("ix_findings_dataset_id", table_name="findings")
    op.drop_table("findings")

    op.drop_index(
        "ix_validation_reports_candidate_pattern_id", table_name="validation_reports"
    )
    op.drop_table("validation_reports")

    op.drop_index("ix_candidate_patterns_analysis_run_id", table_name="candidate_patterns")
    op.drop_table("candidate_patterns")

    # restore the original minimal findings shape
    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("pattern_definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("evidence_level", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_findings_analysis_run_id", "findings", ["analysis_run_id"])
    op.create_index("ix_findings_dataset_id", "findings", ["dataset_id"])

    _create_policy_candidates()

    op.drop_column("analysis_runs", "lineage")
    op.drop_column("analysis_runs", "evaluated_hypotheses")
    op.drop_column("analysis_runs", "validation_contract_version")
    op.drop_column("analysis_runs", "outcome_definition_version")
    op.drop_column("analysis_runs", "discovery_methodology_version")
    op.drop_column("analysis_runs", "analytical_dataset_identity_sha256")
    op.drop_column("analysis_runs", "analytical_dataset_version")
