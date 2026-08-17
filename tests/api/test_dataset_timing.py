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

# Ground truth for this fixture, independently derived from what each column actually means (not
# copied from the classifier under test): identifiers, realized/post-hoc columns, and the one
# realized-outcome-named "gross_margin" must never come back DECISION_TIME.
EXPECTED_TIMING = {
    "booking_id": "identifier",
    "booking_date": "decision_time",
    "travel_date": "decision_time",
    "destination": "decision_time",
    "supplier": "decision_time",
    "customer_price": "decision_time",
    "cost": "decision_time",
    "gross_margin": "outcome",
    "discount": "decision_time",
    "manager": "decision_time",
    "acquisition_channel": "decision_time",
    "customer_type": "decision_time",
    "party_size": "decision_time",
    "trip_duration": "decision_time",
    "booking_lead_time": "decision_time",
    "payment_method": "decision_time",
    "installments": "decision_time",
    "manual_exception": "decision_time",
    "cancellation": "outcome",
    "refund_amount": "outcome",
    "booking_changes": "post_decision",
    "support_cases": "post_decision",
    "additional_cost": "outcome",
    "repeat_purchase": "outcome",
}


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


def test_upload_classifies_feature_timing_for_every_column(
    db_client: TestClient, small_storage: Path
) -> None:
    name = f"timing-test-{uuid.uuid4().hex}"
    with FIXTURE_CSV.open("rb") as handle:
        response = db_client.post(
            "/api/v1/datasets",
            data={"name": name},
            files={"file": ("synthetic_travel_bookings.csv", handle, "text/csv")},
        )
    assert response.status_code == 201
    body = response.json()
    columns = {c["name"]: c for c in body["columns"]}

    assert set(columns) == set(EXPECTED_TIMING)
    mismatches = {
        col: (expected, columns[col]["timing"])
        for col, expected in EXPECTED_TIMING.items()
        if columns[col]["timing"] != expected
    }
    assert mismatches == {}

    # data_type comes from the TASK-007 profile, not guessed independently here.
    assert columns["booking_id"]["data_type"] == "string"
    assert columns["party_size"]["data_type"] == "integer"
    assert columns["booking_date"]["data_type"] == "date"
    assert columns["cancellation"]["data_type"] == "boolean"
    # This fixture's customer_price values happen to all be whole numbers, so the TASK-007
    # profiler correctly infers "integer", not "float" — not assumed from the column's name.
    assert columns["customer_price"]["data_type"] == "integer"

    # nullable reflects observed missingness in this exact upload, not a schema guess.
    assert columns["booking_id"]["nullable"] is False

    # Fetching the dataset again returns the same persisted classification.
    fetched = db_client.get(f"/api/v1/datasets/{body['id']}").json()
    assert {c["name"]: c["timing"] for c in fetched["columns"]} == {
        c["name"]: c["timing"] for c in body["columns"]
    }


def test_no_realized_or_identifying_column_is_ever_decision_time(
    db_client: TestClient, small_storage: Path
) -> None:
    """The safety property that matters more than exact-match: whatever bucket a non-decision-time
    column lands in, it must never be DECISION_TIME (engineering rules's anti-leakage invariant)."""
    name = f"timing-safety-{uuid.uuid4().hex}"
    with FIXTURE_CSV.open("rb") as handle:
        response = db_client.post(
            "/api/v1/datasets",
            data={"name": name},
            files={"file": ("synthetic_travel_bookings.csv", handle, "text/csv")},
        )
    assert response.status_code == 201
    columns = {c["name"]: c["timing"] for c in response.json()["columns"]}

    non_decision_time_columns = [
        col for col, expected in EXPECTED_TIMING.items() if expected != "decision_time"
    ]
    assert non_decision_time_columns  # sanity: the fixture does exercise this property
    for col in non_decision_time_columns:
        assert columns[col] != "decision_time", col


def test_unrecognized_column_name_persists_as_unknown_through_the_full_upload_path(
    db_client: TestClient, small_storage: Path
) -> None:
    """End-to-end version of the pure-classifier unit test with the same name: a column whose name
    matches no rule must persist as UNKNOWN, never fall back to DECISION_TIME, once it has gone
    through the real upload -> profile -> classify -> persist path, not just the pure function."""
    name = f"timing-unknown-{uuid.uuid4().hex}"
    response = db_client.post(
        "/api/v1/datasets",
        data={"name": name},
        files={"file": ("bookings.csv", b"only_col,booking_id\n1,A\n2,B\n", "text/csv")},
    )
    assert response.status_code == 201
    columns = {c["name"]: c["timing"] for c in response.json()["columns"]}
    assert columns == {"only_col": "unknown", "booking_id": "identifier"}
