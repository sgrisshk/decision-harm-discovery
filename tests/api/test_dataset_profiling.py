from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.db.models import UserModel
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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


def test_upload_triggers_real_profiling_of_the_fixture_csv(
    db_client: TestClient,
    small_storage: Path,
    postgres_session: Session,
    login_as_staff: Callable[[TestClient, Session], UserModel],
) -> None:
    name = f"profiling-test-{uuid.uuid4().hex}"
    with FIXTURE_CSV.open("rb") as handle:
        response = db_client.post(
            "/api/v1/datasets",
            data={"name": name},
            files={"file": ("synthetic_travel_bookings.csv", handle, "text/csv")},
        )
    assert response.status_code == 201
    body = response.json()
    profiles = {p["column_name"]: p for p in body["column_profiles"]}

    # Every column in the fixture's real header got profiled.
    header = FIXTURE_CSV.read_text().splitlines()[0].split(",")
    assert set(profiles) == set(header)

    assert profiles["booking_id"]["inferred_type"] == "string"
    assert profiles["booking_id"]["semantic_type_guess"] == "identifier"
    assert profiles["booking_id"]["examples_suppressed"] is True
    assert profiles["booking_id"]["distinct_count"] == 200

    assert profiles["booking_date"]["inferred_type"] == "date"
    assert profiles["booking_date"]["semantic_type_guess"] == "date"
    assert profiles["booking_date"]["min_value"] is not None

    for boolean_column in ("manual_exception", "cancellation"):
        assert profiles[boolean_column]["inferred_type"] == "boolean", boolean_column
        assert profiles[boolean_column]["semantic_type_guess"] == "boolean_flag", boolean_column

    # booking_changes is a real 0-3 change count in this fixture, not a boolean, despite what its
    # name might suggest — verified against the actual data rather than assumed from the name.
    assert profiles["booking_changes"]["inferred_type"] == "integer"
    assert profiles["booking_changes"]["semantic_type_guess"] == "count_or_quantity"

    assert profiles["discount"]["inferred_type"] == "float"
    assert profiles["customer_price"]["semantic_type_guess"] == "currency_amount"
    assert profiles["gross_margin"]["semantic_type_guess"] == "currency_amount"

    assert profiles["manager"]["inferred_type"] == "string"
    assert profiles["manager"]["semantic_type_guess"] == "categorical"
    assert profiles["manager"]["examples_suppressed"] is False
    assert len(profiles["manager"]["examples"]) > 0

    # Fetching the dataset again (a fresh GET) returns the same persisted profiles. Requires
    # authentication (TASK-037 Code Reviewer finding 1) — these profiles carry literal source-data
    # examples, which is exactly what that finding is about.
    login_as_staff(db_client, postgres_session)
    fetched = db_client.get(f"/api/v1/datasets/{body['id']}").json()
    assert {p["column_name"] for p in fetched["column_profiles"]} == set(header)


def test_upload_still_succeeds_even_though_profiling_ran(
    db_client: TestClient, small_storage: Path
) -> None:
    """A profiling failure must not fail the upload (see service.py's comment) — this just
    confirms the happy path doesn't regress the upload response shape/status."""
    name = f"profiling-smoke-{uuid.uuid4().hex}"
    response = db_client.post(
        "/api/v1/datasets",
        data={"name": name},
        files={"file": ("bookings.csv", b"a,b\n1,2\n3,4\n", "text/csv")},
    )
    assert response.status_code == 201
    body = response.json()
    assert {p["column_name"] for p in body["column_profiles"]} == {"a", "b"}
