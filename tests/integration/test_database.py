from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_database_connection(postgres_session: Session) -> None:
    assert postgres_session.scalar(text("SELECT 1")) == 1


def test_create_and_get_dataset(db_client: TestClient) -> None:
    payload = {
        "name": "Synthetic travel bookings",
        "source_filename": "travel_bookings.csv",
        "columns": [
            {"name": "booking_id", "data_type": "string", "timing": "identifier"},
            {"name": "discount", "data_type": "float", "timing": "decision_time"},
            {"name": "gross_margin", "data_type": "float", "timing": "outcome"},
        ],
    }
    created = db_client.post("/api/v1/datasets", json=payload)
    assert created.status_code == 201
    dataset_id = created.json()["id"]

    fetched = db_client.get(f"/api/v1/datasets/{dataset_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == payload["name"]
