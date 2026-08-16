import uuid
from pathlib import Path

from app.core.config import get_settings
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_database_connection(postgres_session: Session) -> None:
    assert postgres_session.scalar(text("SELECT 1")) == 1


def test_create_and_get_dataset(db_client: TestClient, tmp_path: Path) -> None:
    original = get_settings()
    app.dependency_overrides[get_settings] = lambda: original.model_copy(
        update={"ingestion_storage_root": tmp_path}
    )
    try:
        created = db_client.post(
            "/api/v1/datasets",
            data={"name": f"integration-test-{uuid.uuid4().hex}"},
            files={"file": ("travel_bookings.csv", b"booking_id,discount\n1,0.1\n", "text/csv")},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert created.status_code == 201
    dataset_id = created.json()["id"]

    fetched = db_client.get(f"/api/v1/datasets/{dataset_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == dataset_id
