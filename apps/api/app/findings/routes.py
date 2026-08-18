from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.schemas import FindingFeedbackRead, FindingRead
from app.auth.dependencies import get_current_user
from app.db.models import UserModel
from app.db.session import get_db
from app.findings import feedback_service, service
from app.findings.feedback_contracts import FeedbackCreate

router = APIRouter(prefix="/findings", tags=["findings"])


@router.get("", response_model=list[FindingRead])
def list_findings(
    dataset_id: UUID | None = None, session: Session = Depends(get_db)
) -> list[FindingRead]:
    return [FindingRead.model_validate(item) for item in service.list_findings(session, dataset_id)]


@router.get("/{finding_id}", response_model=FindingRead)
def get_finding(finding_id: UUID, session: Session = Depends(get_db)) -> FindingRead:
    return FindingRead.model_validate(service.get_finding(session, finding_id))


@router.post(
    "/{finding_id}/feedback",
    response_model=FindingFeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
def create_finding_feedback(
    finding_id: UUID,
    payload: FeedbackCreate,
    current_user: UserModel = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> FindingFeedbackRead:
    model = feedback_service.create_feedback(session, finding_id, current_user.id, payload)
    session.commit()
    return FindingFeedbackRead.model_validate(model)


@router.get("/{finding_id}/feedback", response_model=list[FindingFeedbackRead])
def list_finding_feedback(
    finding_id: UUID, session: Session = Depends(get_db)
) -> list[FindingFeedbackRead]:
    return [
        FindingFeedbackRead.model_validate(item)
        for item in feedback_service.list_feedback(session, finding_id)
    ]
