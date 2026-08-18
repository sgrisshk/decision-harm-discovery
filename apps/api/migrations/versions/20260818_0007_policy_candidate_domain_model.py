"""Policy Candidate domain model (TASK-030).

Extends `policy_candidates` from its intentionally-minimal skeleton (`id`, `finding_id`, `title`,
`rationale`, `rule_definition: JSONB`, `status: str`) to the real shape
`docs/product/policy-candidate-domain-model.md` §0-§12 defines. The table is confirmed empty in
every environment (`TASK-031`, the only thing that would ever populate it, does not exist yet), so
this is a straight drop/recreate rather than a staged nullable-then-backfill migration — same
precedent as `20260817_0003_finding_persistence.py`'s `findings` rebuild.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0007"
down_revision: str | None = "20260818_0006"
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


def _create_table() -> None:
    op.create_table(
        "policy_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("trigger_conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effective_population", sa.Text(), nullable=True),
        sa.Column(
            "scope_narrowing_features",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="SHADOW"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column(
            "expected_benefit_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("action_detail", sa.Text(), nullable=True),
        sa.Column("evidence_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("backtest_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("retirement_reason", sa.Text(), nullable=True),
        sa.Column(
            "blocked_by_source_lifecycle", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("policy_candidates", "scope_narrowing_features", server_default=None)
    op.alter_column("policy_candidates", "mode", server_default=None)
    op.alter_column("policy_candidates", "status", server_default=None)
    op.alter_column("policy_candidates", "blocked_by_source_lifecycle", server_default=None)
    op.create_index("ix_policy_candidates_finding_id", "policy_candidates", ["finding_id"])


def upgrade() -> None:
    op.drop_index("ix_policy_candidates_finding_id", table_name="policy_candidates")
    op.drop_table("policy_candidates")
    _create_table()


def downgrade() -> None:
    op.drop_index("ix_policy_candidates_finding_id", table_name="policy_candidates")
    op.drop_table("policy_candidates")

    # Restore the original minimal shape.
    op.create_table(
        "policy_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("rule_definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        *timestamps(),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("policy_candidates", "status", server_default=None)
    op.create_index("ix_policy_candidates_finding_id", "policy_candidates", ["finding_id"])
