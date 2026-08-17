from uuid import UUID

from fastapi import HTTPException, status
from policy_schemas.domain import FindingLifecycleStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FindingModel


def list_findings(session: Session, dataset_id: UUID | None = None) -> list[FindingModel]:
    """Only `ACTIVE` findings, matching `docs/product/finding-product-contract.md` §12.1:
    "default and only status shown in the findings list and full detail view." `SUPERSEDED`/
    `WITHDRAWN` findings are retrievable by direct ID (`get_finding`) for audit, never listed."""
    statement = (
        select(FindingModel)
        .where(FindingModel.lifecycle_status == FindingLifecycleStatus.ACTIVE.value)
        .order_by(FindingModel.created_at.desc())
    )
    if dataset_id is not None:
        statement = statement.where(FindingModel.dataset_id == dataset_id)
    return list(session.scalars(statement))


def get_finding(session: Session, finding_id: UUID) -> FindingModel:
    finding = session.get(FindingModel, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return finding
