"""Dataset deletion workflow (TASK-055): datasets.deleted_at tombstone + dataset_deletions audit
table.

Additive only — no existing column or table is altered. `deleted_at` defaults to `NULL` (every
existing dataset stays active); `dataset_deletions` is append-only and starts empty. See
`docs/architecture/dataset-deletion-contract.md`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_0009"
down_revision: str | None = "20260818_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "dataset_deletions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("raw_bytes_purged", sa.Boolean(), nullable=False),
        sa.Column("raw_bytes_retained_reason", sa.Text(), nullable=True),
        sa.Column("redacted_column_profile_count", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataset_deletions_dataset_id", "dataset_deletions", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_dataset_deletions_dataset_id", table_name="dataset_deletions")
    op.drop_table("dataset_deletions")
    op.drop_column("datasets", "deleted_at")
