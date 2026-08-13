from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import DatasetCreate
from app.db.models import DatasetModel


def create_dataset(session: Session, payload: DatasetCreate) -> DatasetModel:
    dataset = DatasetModel(
        name=payload.name,
        source_filename=payload.source_filename,
        columns=[column.model_dump(mode="json") for column in payload.columns],
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset


def list_datasets(session: Session) -> list[DatasetModel]:
    return list(session.scalars(select(DatasetModel).order_by(DatasetModel.created_at.desc())))


def get_dataset(session: Session, dataset_id: UUID) -> DatasetModel:
    dataset = session.get(DatasetModel, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset
