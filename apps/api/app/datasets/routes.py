from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.schemas import DatasetDeletionRead, DatasetDeletionRequest, DatasetRead
from app.auth.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.datasets import service
from app.db.models import UserModel
from app.db.session import get_db

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
def create_dataset(
    name: Annotated[str, Form(min_length=1, max_length=200)],
    file: UploadFile,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DatasetRead:
    return DatasetRead.model_validate(
        service.create_dataset_from_upload(session, name, file, settings)
    )


@router.get("", response_model=list[DatasetRead])
def list_datasets(
    current_user: UserModel = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[DatasetRead]:
    return [DatasetRead.model_validate(item) for item in service.list_datasets(session)]


@router.get("/{dataset_id}", response_model=DatasetRead)
def get_dataset(
    dataset_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DatasetRead:
    return DatasetRead.model_validate(service.get_dataset(session, dataset_id))


@router.delete("/{dataset_id}", response_model=DatasetDeletionRead)
def delete_dataset(
    dataset_id: UUID,
    payload: DatasetDeletionRequest,
    current_user: UserModel = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DatasetDeletionRead:
    return DatasetDeletionRead.model_validate(
        service.delete_dataset(session, dataset_id, current_user.id, payload.reason, settings)
    )
