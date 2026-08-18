"""Policy backtest runs (TASK-034).

New `policy_backtest_runs` table — one row per triggered run against a Policy Candidate's trigger
condition (`HANDOFF-050`'s job-status answer: reuses `ResourceStatus`, same shape as
`AnalysisRunModel.status`). Computed synchronously inside the request that creates it, so a row is
only ever inserted already resolved to `completed`/`failed` — never `pending`/`running`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0008"
down_revision: str | None = "20260818_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_backtest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cost_per_review_eur", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("backtest_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["policy_candidate_id"], ["policy_candidates.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_backtest_runs_policy_candidate_id",
        "policy_backtest_runs",
        ["policy_candidate_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_policy_backtest_runs_policy_candidate_id", table_name="policy_backtest_runs"
    )
    op.drop_table("policy_backtest_runs")
