from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.schemas import DatasetCreate, DatasetRead
from app.datasets import service
from app.db.session import get_db

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
def create_dataset(payload: DatasetCreate, session: Session = Depends(get_db)) -> DatasetRead:
    return DatasetRead.model_validate(service.create_dataset(session, payload))


@router.get("", response_model=list[DatasetRead])
def list_datasets(session: Session = Depends(get_db)) -> list[DatasetRead]:
    return [DatasetRead.model_validate(item) for item in service.list_datasets(session)]


@router.get("/{dataset_id}", response_model=DatasetRead)
def get_dataset(dataset_id: UUID, session: Session = Depends(get_db)) -> DatasetRead:
    return DatasetRead.model_validate(service.get_dataset(session, dataset_id))
