from __future__ import annotations

import io
from pathlib import Path

import pytest
from app.ingestion.storage import UploadTooLargeError, read_bounded, store_immutable_csv
from app.ingestion.validation import (
    IngestionValidationError,
    sanitize_filename,
    validate_csv_content,
)

# --- sanitize_filename -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "../secret.csv",
        "a/b.csv",
        "a\\b.csv",
        ".",
        "..",
        ".hidden.csv",
        "no-extension",
        "data.CSV.exe",
        "a" * 252 + ".csv",  # 256 chars total, over the cap
        "bad name!.csv",
        "sneaky;rm -rf.csv",
    ],
)
def test_sanitize_filename_rejects_unsafe_names(raw: str) -> None:
    with pytest.raises(IngestionValidationError):
        sanitize_filename(raw)


@pytest.mark.parametrize(
    "raw",
    ["bookings.csv", "Bookings.CSV", "travel-data_v2.csv", "a.csv"],
)
def test_sanitize_filename_accepts_safe_names(raw: str) -> None:
    assert sanitize_filename(raw) == raw.strip()


# --- validate_csv_content -----------------------------------------------------------


def test_validate_csv_content_accepts_plausible_csv() -> None:
    validate_csv_content(b"id,amount\n1,10.5\n2,20.0\n")


def test_validate_csv_content_rejects_empty() -> None:
    with pytest.raises(IngestionValidationError, match="empty"):
        validate_csv_content(b"")


def test_validate_csv_content_rejects_binary() -> None:
    with pytest.raises(IngestionValidationError, match="binary"):
        validate_csv_content(b"id,amount\x00\n1,10\n")


def test_validate_csv_content_rejects_non_utf8() -> None:
    with pytest.raises(IngestionValidationError, match="UTF-8"):
        validate_csv_content(b"\xff\xfe\xfd\xfc")


def test_validate_csv_content_rejects_no_header_delimiter() -> None:
    with pytest.raises(IngestionValidationError, match="header"):
        validate_csv_content(b"just one column with no delimiter\nrow\n")


# --- read_bounded --------------------------------------------------------------------


def test_read_bounded_returns_full_content_under_limit() -> None:
    assert read_bounded(io.BytesIO(b"hello world"), max_bytes=1024) == b"hello world"


def test_read_bounded_aborts_over_limit() -> None:
    with pytest.raises(UploadTooLargeError):
        read_bounded(io.BytesIO(b"x" * 100), max_bytes=10, chunk_size=4)


def test_read_bounded_never_buffers_much_past_the_limit() -> None:
    # A 1 MiB body against a 10-byte limit with small chunks must not silently succeed,
    # and must fail fast rather than reading the whole stream first.
    stream = io.BytesIO(b"y" * (1024 * 1024))
    with pytest.raises(UploadTooLargeError):
        read_bounded(stream, max_bytes=10, chunk_size=16)
    assert stream.tell() < 1024 * 1024


# --- store_immutable_csv ---------------------------------------------------------------


def test_store_immutable_csv_is_content_addressed_and_deterministic(tmp_path: Path) -> None:
    data = b"id,amount\n1,10\n"
    first = store_immutable_csv(tmp_path, data)
    second = store_immutable_csv(tmp_path, data)

    assert first == second
    target = tmp_path / first.storage_path
    assert target.is_file()
    assert target.read_bytes() == data


def test_store_immutable_csv_is_read_only_after_write(tmp_path: Path) -> None:
    stored = store_immutable_csv(tmp_path, b"id,amount\n1,10\n")
    target = tmp_path / stored.storage_path

    with pytest.raises(PermissionError):
        target.write_bytes(b"tampered")


def test_store_immutable_csv_different_content_gets_different_paths(tmp_path: Path) -> None:
    first = store_immutable_csv(tmp_path, b"id,amount\n1,10\n")
    second = store_immutable_csv(tmp_path, b"id,amount\n2,20\n")

    assert first.sha256 != second.sha256
    assert first.storage_path != second.storage_path


def test_store_immutable_csv_leaves_no_temp_files_behind(tmp_path: Path) -> None:
    stored = store_immutable_csv(tmp_path, b"id,amount\n1,10\n")
    directory = (tmp_path / stored.storage_path).parent
    leftovers = [path for path in directory.iterdir() if path.name != f"{stored.sha256}.csv"]
    assert leftovers == []
