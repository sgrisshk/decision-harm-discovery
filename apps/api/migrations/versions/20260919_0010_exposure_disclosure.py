"""Exposure disclosure fields on validation_reports (TASK-091, TASK-085 §5.3, TASK-086).

Additive only — two nullable `Text` columns. Every row persisted before this migration reads
back with both `NULL`, which the API/frontend already treat as "not present," not an error
(`ValidationMetadataPersistence`/`FindingEvidenceRead` both default these fields to `None`).
`non_identifiability_statement` is non-`NULL` for every real candidate promoted going forward;
`g16_caveat` stays legitimately `NULL` whenever `k == 1` (`G16` did not run for that candidate),
by design, not a migration artifact.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_0010"
down_revision: str | None = "20260822_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "validation_reports",
        sa.Column("non_identifiability_statement", sa.Text(), nullable=True),
    )
    op.add_column(
        "validation_reports",
        sa.Column("g16_caveat", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("validation_reports", "g16_caveat")
    op.drop_column("validation_reports", "non_identifiability_statement")
