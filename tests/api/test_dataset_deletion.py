from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from app.auth.security import hash_password
from app.core.config import get_settings
from app.db.models import DatasetColumnProfileModel, UserModel
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _upload(client: TestClient, name: str, filename: str, content: bytes):
    return client.post(
        "/api/v1/datasets",
        data={"name": name},
        files={"file": (filename, content, "text/csv")},
    )


def _delete(client: TestClient, dataset_id: str, reason: str):
    # `TestClient.delete()` does not accept a `json=` body in this httpx version.
    return client.request("DELETE", f"/api/v1/datasets/{dataset_id}", json={"reason": reason})


@pytest.fixture
def small_storage(tmp_path: Path):
    """Point ingestion at a throwaway directory instead of the real data/raw/ (mirrors
    `tests/api/test_datasets_upload.py`)."""
    original = get_settings()
    app.dependency_overrides[get_settings] = lambda: original.model_copy(
        update={"ingestion_storage_root": tmp_path}
    )
    try:
        yield tmp_path
    finally:
        app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def dataset_name() -> str:
    return f"deletion-test-{uuid.uuid4().hex}"


def _unique_run_id() -> bytes:
    """A per-invocation token embedded in every test's CSV body.

    Content-addressed storage means two tests (or two runs of the same test against the
    long-lived Postgres instance the `postgres_session` fixture points at — uploads commit
    directly, so there is no per-test transaction to roll back, matching
    `tests/api/test_datasets_upload.py`'s `dataset_name` fixture doing the same for names) that
    upload byte-identical CSVs get the *same* `checksum_sha256` and therefore the *same* dedup
    disposition on delete. Tests that specifically assert `raw_bytes_purged` need every run's
    bytes to be genuinely unique, not just its dataset name.
    """
    return uuid.uuid4().hex.encode()


def _seed_and_login(db_client: TestClient, session: Session) -> UserModel:
    user = UserModel(
        email=f"deleter-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("dataset deleter password"),
        display_name="Dataset Deleter",
    )
    session.add(user)
    session.commit()
    login_response = db_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "dataset deleter password"},
    )
    assert login_response.status_code == 200
    return user


def test_delete_requires_authentication(
    db_client: TestClient, small_storage: Path, dataset_name: str
) -> None:
    uploaded = _upload(db_client, dataset_name, "bookings.csv", b"booking_id,discount\n1,0.1\n")
    dataset_id = uploaded.json()["id"]

    response = _delete(db_client, dataset_id, "no longer needed")

    assert response.status_code == 401


def test_delete_requires_a_nonempty_reason(
    db_client: TestClient, small_storage: Path, dataset_name: str, postgres_session: Session
) -> None:
    uploaded = _upload(db_client, dataset_name, "bookings.csv", b"booking_id,discount\n1,0.1\n")
    dataset_id = uploaded.json()["id"]
    _seed_and_login(db_client, postgres_session)

    response = _delete(db_client, dataset_id, "  ")

    assert response.status_code == 400


def test_delete_unknown_dataset_404s(db_client: TestClient, postgres_session: Session) -> None:
    _seed_and_login(db_client, postgres_session)

    response = _delete(db_client, str(uuid.uuid4()), "cleanup")

    assert response.status_code == 404


def test_delete_twice_is_a_conflict_not_a_silent_success(
    db_client: TestClient, small_storage: Path, dataset_name: str, postgres_session: Session
) -> None:
    uploaded = _upload(db_client, dataset_name, "bookings.csv", b"booking_id,discount\n1,0.1\n")
    dataset_id = uploaded.json()["id"]
    _seed_and_login(db_client, postgres_session)

    first = _delete(db_client, dataset_id, "customer requested erasure")
    assert first.status_code == 200

    second = _delete(db_client, dataset_id, "customer requested erasure")
    assert second.status_code == 409


def test_delete_hides_dataset_from_list_and_get_but_purges_unreferenced_bytes(
    db_client: TestClient, small_storage: Path, dataset_name: str, postgres_session: Session
) -> None:
    content = b"booking_id,discount,run_id\n1,0.1," + _unique_run_id() + b"\n2,0.2,x\n"
    uploaded = _upload(db_client, dataset_name, "bookings.csv", content)
    dataset_id = uploaded.json()["id"]
    assert list(small_storage.rglob("*.csv")) != []
    _seed_and_login(db_client, postgres_session)

    response = _delete(db_client, dataset_id, "customer requested erasure")

    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] == dataset_id
    assert body["reason"] == "customer requested erasure"
    assert body["raw_bytes_purged"] is True
    assert body["raw_bytes_retained_reason"] is None

    # Gone from every read surface.
    assert db_client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404
    listing = db_client.get("/api/v1/datasets").json()
    assert all(item["id"] != dataset_id for item in listing)

    # And the raw bytes are actually gone from disk, not just hidden.
    assert list(small_storage.rglob("*.csv")) == []


def test_delete_retains_bytes_when_another_active_dataset_shares_the_same_content(
    db_client: TestClient, small_storage: Path, postgres_session: Session
) -> None:
    content = b"booking_id,discount,run_id\n1,0.1," + _unique_run_id() + b"\n2,0.2,x\n"
    name_a = f"deletion-test-a-{uuid.uuid4().hex}"
    name_b = f"deletion-test-b-{uuid.uuid4().hex}"
    # Content-addressed storage dedups identical bytes across different dataset names.
    dataset_a = _upload(db_client, name_a, "a.csv", content).json()
    dataset_b = _upload(db_client, name_b, "b.csv", content).json()
    assert dataset_a["checksum_sha256"] == dataset_b["checksum_sha256"]
    assert len(list(small_storage.rglob("*.csv"))) == 1

    _seed_and_login(db_client, postgres_session)

    response = _delete(db_client, dataset_a["id"], "duplicate upload cleanup")

    assert response.status_code == 200
    body = response.json()
    assert body["raw_bytes_purged"] is False
    assert body["raw_bytes_retained_reason"] is not None

    # The bytes are still on disk, still readable through the surviving dataset.
    assert list(small_storage.rglob("*.csv")) != []
    assert db_client.get(f"/api/v1/datasets/{dataset_b['id']}").status_code == 200
    # But the deleted one is still gone from every read surface.
    assert db_client.get(f"/api/v1/datasets/{dataset_a['id']}").status_code == 404


def test_delete_redacts_literal_column_profile_content(
    db_client: TestClient, small_storage: Path, dataset_name: str, postgres_session: Session
) -> None:
    # A low-cardinality text column so the schema profiler does not itself already suppress
    # examples (see `policy_analytics.profiling.schema_profiler`) — this test needs a real,
    # non-suppressed example on record before deletion so redaction is actually exercised.
    content = (
        b"booking_id,status\n1,confirmed\n2,confirmed\n3,cancelled\n4,confirmed\n5,cancelled\n"
    )
    uploaded = _upload(db_client, dataset_name, "bookings.csv", content)
    dataset_id = uploaded.json()["id"]
    before = db_client.get(f"/api/v1/datasets/{dataset_id}").json()
    status_profile = next(p for p in before["column_profiles"] if p["column_name"] == "status")
    assert status_profile["examples"] != []
    assert status_profile["examples_suppressed"] is False

    _seed_and_login(db_client, postgres_session)
    deletion = _delete(db_client, dataset_id, "customer requested erasure").json()
    assert deletion["redacted_column_profile_count"] == len(before["column_profiles"])

    # The dataset itself is gone from the read API now, so inspect the redaction directly via
    # the ORM session rather than a route that would 404.
    profiles = (
        postgres_session.query(DatasetColumnProfileModel)
        .filter(DatasetColumnProfileModel.dataset_id == uuid.UUID(dataset_id))
        .all()
    )
    assert profiles
    for profile in profiles:
        assert profile.examples == []
        assert profile.examples_suppressed is True
        assert profile.suspicious_values == []
        # Aggregate stats are not literal source content and are deliberately left intact.
        assert profile.row_count == 5
