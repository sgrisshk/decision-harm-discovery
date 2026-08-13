from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import AnalysisRunCreate
from app.datasets.service import get_dataset
from app.db.models import AnalysisRunModel


def create_analysis_run(session: Session, payload: AnalysisRunCreate) -> AnalysisRunModel:
    dataset = get_dataset(session, payload.dataset_id)
    run = AnalysisRunModel(
        dataset_id=dataset.id,
        dataset_version=dataset.version,
        code_version=payload.code_version,
        configuration=payload.configuration,
        random_seed=payload.random_seed,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_analysis_run(session: Session, run_id: UUID) -> AnalysisRunModel:
    run = session.get(AnalysisRunModel, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    return run
