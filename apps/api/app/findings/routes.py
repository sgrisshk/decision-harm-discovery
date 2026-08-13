from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import FindingRead
from app.db.session import get_db
from app.findings import service

router = APIRouter(prefix="/findings", tags=["findings"])


@router.get("", response_model=list[FindingRead])
def list_findings(
    dataset_id: UUID | None = None, session: Session = Depends(get_db)
) -> list[FindingRead]:
    return [FindingRead.model_validate(item) for item in service.list_findings(session, dataset_id)]


@router.get("/{finding_id}", response_model=FindingRead)
def get_finding(finding_id: UUID, session: Session = Depends(get_db)) -> FindingRead:
    return FindingRead.model_validate(service.get_finding(session, finding_id))
