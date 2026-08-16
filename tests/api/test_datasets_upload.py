from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def _upload(
    client: TestClient, name: str, filename: str, content: bytes, content_type: str = "text/csv"
):
    return client.post(
        "/api/v1/datasets",
        data={"name": name},
        files={"file": (filename, content, content_type)},
    )


@pytest.fixture
def small_storage(tmp_path: Path):
    """Point ingestion at a throwaway directory instead of the real data/raw/."""
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
    """A per-test-run unique dataset identity.

    These tests commit directly against `postgres_session` (see the `create_dataset_from_upload`
    service, which commits inside the request) so there is no transaction to roll back between
    runs. A fixed literal name would collide with rows a previous run left behind and get
    legitimately rejected as a duplicate — which is the feature under test working correctly, just
    aimed at the wrong target. Each test gets its own unguessable name instead.
    """
    return f"upload-test-{uuid.uuid4().hex}"


def test_upload_creates_version_one_with_manifest_fields(
    db_client: TestClient, small_storage: Path, dataset_name: str
) -> None:
    content = b"booking_id,discount\n1,0.1\n2,0.2\n"
    response = _upload(db_client, dataset_name, "bookings.csv", content)

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 1
    assert body["source_filename"] == "bookings.csv"
    assert body["checksum_sha256"] == hashlib.sha256(content).hexdigest()
    assert body["size_bytes"] == len(content)
    assert body["content_type"] == "text/csv"
    assert body["source_type"] == "csv_upload"
    assert body["status"] == "pending"
    assert body["columns"] == []
    assert "storage_path" not in body

    stored_files = list(small_storage.rglob("*.csv"))
    assert len(stored_files) == 1


def test_duplicate_content_upload_is_rejected_without_new_version(
    db_client: TestClient, small_storage: Path, dataset_name: str
) -> None:
    content = b"booking_id,discount\n1,0.1\n"
    first = _upload(db_client, dataset_name, "bookings.csv", content)
    assert first.status_code == 201

    second = _upload(db_client, dataset_name, "bookings-again.csv", content)
    assert second.status_code == 409

    listing = db_client.get("/api/v1/datasets").json()
    matching = [item for item in listing if item["name"] == dataset_name]
    assert len(matching) == 1
    assert matching[0]["version"] == 1


def test_differing_content_upload_creates_next_version(
    db_client: TestClient, small_storage: Path, dataset_name: str
) -> None:
    first = _upload(db_client, dataset_name, "v1.csv", b"booking_id,discount\n1,0.1\n")
    assert first.status_code == 201
    assert first.json()["version"] == 1

    second = _upload(db_client, dataset_name, "v2.csv", b"booking_id,discount\n1,0.2\n")
    assert second.status_code == 201
    assert second.json()["version"] == 2
    assert second.json()["checksum_sha256"] != first.json()["checksum_sha256"]


def test_oversized_upload_is_rejected(
    db_client: TestClient, tmp_path: Path, dataset_name: str
) -> None:
    original = get_settings()
    app.dependency_overrides[get_settings] = lambda: original.model_copy(
        update={"ingestion_storage_root": tmp_path, "max_upload_bytes": 10}
    )
    try:
        response = _upload(
            db_client, dataset_name, "bookings.csv", b"booking_id,discount\n1,0.1\n2,0.2\n"
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 413
    assert list(tmp_path.rglob("*.csv")) == []


def test_non_csv_extension_is_rejected(
    db_client: TestClient, small_storage: Path, dataset_name: str
) -> None:
    response = _upload(db_client, dataset_name, "bookings.txt", b"id,amount\n1,10\n")
    assert response.status_code == 400
    assert list(small_storage.rglob("*")) == []


def test_upload_never_logs_the_filename(
    db_client: TestClient,
    small_storage: Path,
    dataset_name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_filename = f"super-secret-customer-export-{uuid.uuid4().hex[:8]}.csv"
    with caplog.at_level(logging.DEBUG):
        response = _upload(db_client, dataset_name, secret_filename, b"id,amount\n1,10\n")
    assert response.status_code == 201
    for record in caplog.records:
        assert secret_filename not in record.getMessage()
        assert secret_filename not in str(record.__dict__.get("fields", ""))
