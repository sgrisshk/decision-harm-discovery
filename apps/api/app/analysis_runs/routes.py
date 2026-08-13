from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.analysis_runs import service
from app.api.schemas import AnalysisRunCreate, AnalysisRunRead
from app.db.session import get_db

router = APIRouter(prefix="/analysis-runs", tags=["analysis-runs"])


@router.post("", response_model=AnalysisRunRead, status_code=status.HTTP_201_CREATED)
def create_analysis_run(
    payload: AnalysisRunCreate, session: Session = Depends(get_db)
) -> AnalysisRunRead:
    return AnalysisRunRead.model_validate(service.create_analysis_run(session, payload))


@router.get("/{run_id}", response_model=AnalysisRunRead)
def get_analysis_run(run_id: UUID, session: Session = Depends(get_db)) -> AnalysisRunRead:
    return AnalysisRunRead.model_validate(service.get_analysis_run(session, run_id))
