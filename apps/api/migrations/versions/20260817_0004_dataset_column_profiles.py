"""Add dataset_column_profiles (TASK-007: schema profiler)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0004"
down_revision: str | None = "20260817_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dataset_column_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("column_name", sa.String(length=128), nullable=False),
        sa.Column("inferred_type", sa.String(length=16), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("missingness", sa.Float(), nullable=False),
        sa.Column("distinct_count", sa.Integer(), nullable=False),
        sa.Column("min_value", sa.String(length=64), nullable=True),
        sa.Column("max_value", sa.String(length=64), nullable=True),
        sa.Column("semantic_type_guess", sa.String(length=32), nullable=False),
        sa.Column("examples", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("examples_suppressed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("suspicious_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("suspicious_count", sa.Integer(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id", "column_name", name="uq_dataset_column_profiles_dataset_column"
        ),
    )
    op.create_index(
        "ix_dataset_column_profiles_dataset_id", "dataset_column_profiles", ["dataset_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dataset_column_profiles_dataset_id", table_name="dataset_column_profiles"
    )
    op.drop_table("dataset_column_profiles")
