from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FindingFeedbackModel, FindingModel
from app.findings.feedback_contracts import FeedbackCreate


def create_feedback(
    session: Session, finding_id: UUID, created_by_user_id: UUID, payload: FeedbackCreate
) -> FindingFeedbackModel:
    """Append-only: always a new row, never an update to a prior submission for the same finding
    (`docs/product/finding-feedback-contract.md` §5). Never touches `FindingModel` (§7)."""
    if session.get(FindingModel, finding_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")

    model = FindingFeedbackModel(
        id=uuid4(),
        finding_id=finding_id,
        created_by_user_id=created_by_user_id,
        review_session=payload.review_session,
        captured_at=datetime.now(UTC),
        novelty=payload.novelty,
        actionability=payload.actionability,
        tags=[tag.value for tag in payload.tags],
        customer_comment=payload.customer_comment,
        customer_certainty=payload.customer_certainty,
        intended_action=payload.intended_action,
        commitment_strength=payload.commitment_strength,
        customer_owner=payload.customer_owner,
        internal_follow_up_owner=payload.internal_follow_up_owner,
        follow_up_date=payload.follow_up_date,
    )
    session.add(model)
    session.flush()
    return model


def list_feedback(session: Session, finding_id: UUID) -> list[FindingFeedbackModel]:
    if session.get(FindingModel, finding_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    statement = (
        select(FindingFeedbackModel)
        .where(FindingFeedbackModel.finding_id == finding_id)
        .order_by(FindingFeedbackModel.captured_at.desc())
    )
    return list(session.scalars(statement))
