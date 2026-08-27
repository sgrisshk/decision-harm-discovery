from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from app.auth.security import hash_password
from app.core.config import get_settings
from app.datasets.service import delete_dataset
from app.db.models import DatasetColumnProfileModel, UserModel
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
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


def test_delete_then_reupload_identical_content_succeeds(
    db_client: TestClient, small_storage: Path, dataset_name: str, postgres_session: Session
) -> None:
    """TASK-055 R1 (`HANDOFF-074`): the adjacency-dedup check in `create_dataset_from_upload`
    must not treat a *tombstoned* "latest" version as a conflict. Before the fix, deleting a
    dataset and then re-uploading the exact same content under the same name -- one of the most
    plausible real actions a customer takes after a deletion request ("delete this, we'll
    re-send it") -- was permanently blocked with a `409` referencing a version number that
    resolves nowhere else in the API."""
    content = b"booking_id,discount,run_id\n1,0.1," + _unique_run_id() + b"\n2,0.2,x\n"
    uploaded = _upload(db_client, dataset_name, "bookings.csv", content)
    assert uploaded.status_code == 201
    dataset_id = uploaded.json()["id"]
    _seed_and_login(db_client, postgres_session)

    deleted = _delete(db_client, dataset_id, "customer requested erasure")
    assert deleted.status_code == 200
    assert deleted.json()["raw_bytes_purged"] is True

    reuploaded = _upload(db_client, dataset_name, "bookings-again.csv", content)

    assert reuploaded.status_code == 201
    assert reuploaded.json()["checksum_sha256"] == uploaded.json()["checksum_sha256"]
    # Version numbering still counts the tombstoned version -- only the conflict check changes
    # (matches the already-correct behavior for *differing* content after a delete).
    assert reuploaded.json()["version"] == 2


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


def test_concurrent_delete_of_dedup_siblings_serializes_instead_of_orphaning_bytes(
    db_client: TestClient, small_storage: Path, postgres_session: Session
) -> None:
    """TASK-055 R2 (`HANDOFF-074`): `delete_dataset`'s dedup-sibling check must not run as a
    plain, unlocked `SELECT` under READ COMMITTED, or two concurrent deletes of datasets sharing
    content-addressed bytes can each independently -- and incorrectly -- conclude "the other one
    is still active" and both retain, permanently orphaning the file once both commit.

    Proves the row lock is real, not just present in the diff: a second, independent connection
    holds a plain row lock on dataset A *only* (never touching its `deleted_at`, so the
    pre-existing "update the row you're actually deleting" write path -- unrelated to this fix --
    cannot be what blocks), standing in for "another delete of a dedup-sibling already in flight,
    already past this same lock acquisition." A genuine `delete_dataset` call for sibling B, with
    a short `lock_timeout` so blocking is observable instead of hanging the test, must then fail
    to proceed until A's lock is released -- proving `delete_dataset` itself now reaches into A's
    row before deciding B's disposition, not merely that *some* unrelated statement happens to
    collide. Once released, it must correctly re-evaluate and purge, leaving zero orphaned files.
    """
    content = b"booking_id,discount,run_id\n1,0.1," + _unique_run_id() + b"\n2,0.2,x\n"
    name_a = f"deletion-lock-a-{uuid.uuid4().hex}"
    name_b = f"deletion-lock-b-{uuid.uuid4().hex}"
    dataset_a = _upload(db_client, name_a, "a.csv", content).json()
    dataset_b = _upload(db_client, name_b, "b.csv", content).json()
    assert dataset_a["checksum_sha256"] == dataset_b["checksum_sha256"]
    assert len(list(small_storage.rglob("*.csv"))) == 1
    user = _seed_and_login(db_client, postgres_session)
    settings = get_settings().model_copy(update={"ingestion_storage_root": small_storage})

    database_url = os.environ["TEST_DATABASE_URL"]
    blocker_engine = create_engine(database_url)
    with blocker_engine.connect() as blocker_conn:
        # Locks *only* dataset A's row -- deliberately not the whole checksum group -- so the
        # only way `delete_dataset(B, ...)` can collide is by itself reaching for A's row, not by
        # the unrelated, pre-existing autoflush of B's own `deleted_at` update.
        blocker_conn.execute(text("BEGIN"))
        blocker_conn.execute(
            text("SELECT id FROM datasets WHERE id = :dataset_id FOR UPDATE"),
            {"dataset_id": dataset_a["id"]},
        )
        try:
            postgres_session.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(OperationalError):
                delete_dataset(
                    postgres_session, uuid.UUID(dataset_b["id"]), user.id, "cleanup", settings
                )
        finally:
            postgres_session.rollback()  # required: Postgres aborts the whole transaction on error
            blocker_conn.execute(text("ROLLBACK"))
    blocker_engine.dispose()

    # The blocking transaction is gone; the same delete now proceeds and, since dataset A was
    # never actually tombstoned by the (rolled-back) blocker, correctly retains the bytes A still
    # references -- then deleting A afterward correctly finds no other active reference and
    # purges. Either order, the union outcome must be exactly one purge, never zero and never an
    # orphan.
    first = _delete(db_client, dataset_b["id"], "cleanup")
    assert first.status_code == 200
    second = _delete(db_client, dataset_a["id"], "cleanup")
    assert second.status_code == 200
    assert {first.json()["raw_bytes_purged"], second.json()["raw_bytes_purged"]} == {False, True}
    assert list(small_storage.rglob("*.csv")) == []


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
    _seed_and_login(db_client, postgres_session)
    before = db_client.get(f"/api/v1/datasets/{dataset_id}").json()
    status_profile = next(p for p in before["column_profiles"] if p["column_name"] == "status")
    assert status_profile["examples"] != []
    assert status_profile["examples_suppressed"] is False

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
