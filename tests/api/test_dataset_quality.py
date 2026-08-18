from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE_CSV = REPOSITORY / "tests/fixtures/synthetic_travel_bookings.csv"


@pytest.fixture
def small_storage(tmp_path: Path):
    original = get_settings()
    app.dependency_overrides[get_settings] = lambda: original.model_copy(
        update={"ingestion_storage_root": tmp_path}
    )
    try:
        yield tmp_path
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_upload_produces_a_quality_report_for_the_fixture_csv(
    db_client: TestClient, small_storage: Path
) -> None:
    name = f"quality-test-{uuid.uuid4().hex}"
    with FIXTURE_CSV.open("rb") as handle:
        response = db_client.post(
            "/api/v1/datasets",
            data={"name": name},
            files={"file": ("synthetic_travel_bookings.csv", handle, "text/csv")},
        )
    assert response.status_code == 201
    body = response.json()
    report = body["quality_report"]
    assert report is not None

    row_count = len(FIXTURE_CSV.read_text().splitlines()) - 1  # minus header
    assert report["row_count"] == row_count
    assert report["column_count"] == 24
    assert report["duplicate_row_count"] == 0

    assert "booking_id" not in report["usable_decision_variables"]
    assert "manager" in report["usable_decision_variables"]
    assert "cancellation" in report["available_outcomes"]
    excluded_names = {c["column_name"] for c in report["excluded_columns"]}
    assert "booking_id" in excluded_names
    assert "cancellation" in excluded_names
    assert "manager" not in excluded_names

    assert report["rating"] in ("ready", "ready_with_limitations", "not_ready")

    # Fetching the dataset again returns the same persisted report.
    fetched = db_client.get(f"/api/v1/datasets/{body['id']}").json()
    assert fetched["quality_report"] == report


def test_quality_report_rating_is_not_ready_below_the_row_floor(
    db_client: TestClient, small_storage: Path
) -> None:
    name = f"quality-tiny-{uuid.uuid4().hex}"
    content = b"destination,cancellation\nRome,True\nTokyo,False\n"
    response = db_client.post(
        "/api/v1/datasets",
        data={"name": name},
        files={"file": ("tiny.csv", content, "text/csv")},
    )
    assert response.status_code == 201
    report = response.json()["quality_report"]
    assert report["rating"] == "not_ready"
    assert any("rows" in reason for reason in report["rating_reasons"])
