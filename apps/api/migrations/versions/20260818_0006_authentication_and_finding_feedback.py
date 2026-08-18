"""Basic authentication (TASK-053) and finding feedback (TASK-035).

`users`/`sessions` are new: internal-staff accounts (no self-serve signup — rows are created by
`scripts/create_user.py`) and DB-backed opaque session tokens (real, immediate revocation on
logout, no signing secret). `finding_feedback` is new and append-only
(`docs/product/finding-feedback-contract.md`): it FKs to both `findings` (which finding this is
about) and `users` (which internal reviewer captured it) — bundled into one migration since the
feedback table depends on the auth table existing first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0006"
down_revision: str | None = "20260817_0005"
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


def upgrade() -> None:
    # --- users -------------------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # --- sessions ------------------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # --- finding_feedback ------------------------------------------------------------------------
    op.create_table(
        "finding_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_session", sa.String(length=256), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("novelty", sa.String(length=16), nullable=True),
        sa.Column("actionability", sa.String(length=16), nullable=True),
        sa.Column(
            "tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.Column("customer_comment", sa.Text(), nullable=True),
        sa.Column("customer_certainty", sa.String(length=16), nullable=True),
        sa.Column("intended_action", sa.Text(), nullable=True),
        sa.Column("commitment_strength", sa.String(length=32), nullable=True),
        sa.Column("customer_owner", sa.String(length=200), nullable=True),
        sa.Column("internal_follow_up_owner", sa.String(length=200), nullable=True),
        sa.Column("follow_up_date", sa.Date(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("finding_feedback", "tags", server_default=None)
    op.create_index("ix_finding_feedback_finding_id", "finding_feedback", ["finding_id"])


def downgrade() -> None:
    op.drop_index("ix_finding_feedback_finding_id", table_name="finding_feedback")
    op.drop_table("finding_feedback")

    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_table("users")
