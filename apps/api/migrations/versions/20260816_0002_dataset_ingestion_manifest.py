"""Add ingestion manifest columns to datasets (TASK-005/TASK-006)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_0002"
down_revision: str | None = "20260813_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("checksum_sha256", sa.String(length=64), nullable=False))
    op.add_column("datasets", sa.Column("size_bytes", sa.BigInteger(), nullable=False))
    op.add_column("datasets", sa.Column("content_type", sa.String(length=100), nullable=False))
    op.add_column("datasets", sa.Column("source_type", sa.String(length=32), nullable=False))
    op.add_column("datasets", sa.Column("storage_path", sa.String(length=512), nullable=False))
    op.create_unique_constraint("uq_datasets_name_version", "datasets", ["name", "version"])


def downgrade() -> None:
    op.drop_constraint("uq_datasets_name_version", "datasets", type_="unique")
    op.drop_column("datasets", "storage_path")
    op.drop_column("datasets", "source_type")
    op.drop_column("datasets", "content_type")
    op.drop_column("datasets", "size_bytes")
    op.drop_column("datasets", "checksum_sha256")
