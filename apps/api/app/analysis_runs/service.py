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
        analytical_dataset_version=payload.analytical_dataset_version,
        analytical_dataset_identity_sha256=payload.analytical_dataset_identity_sha256,
        code_version=payload.code_version,
        discovery_methodology_version=payload.discovery_methodology_version,
        outcome_definition_version=payload.outcome_definition_version,
        validation_contract_version=payload.validation_contract_version,
        configuration=payload.configuration,
        random_seed=payload.random_seed,
        evaluated_hypotheses=payload.evaluated_hypotheses,
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
