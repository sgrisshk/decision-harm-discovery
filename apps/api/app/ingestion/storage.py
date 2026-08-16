"""Content-addressed, immutable raw-file storage.

Files are stored at ``{root}/{sha256[:2]}/{sha256}.csv``. Writes go to a temp file in
the destination directory, are fsync'd, then atomically renamed into place and made
read-only — immutable by construction rather than by convention. Re-storing bytes that
already exist on disk is a no-op dedup, not a rewrite.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.ingestion.validation import IngestionValidationError

_CHUNK_SIZE = 1024 * 1024
_READONLY_FILE = stat.S_IRUSR | stat.S_IRGRP


class UploadTooLargeError(IngestionValidationError):
    """Raised when an upload exceeds the configured byte ceiling."""


@dataclass(frozen=True, slots=True)
class StoredFile:
    sha256: str
    size_bytes: int
    storage_path: str


class _Readable(Protocol):
    def read(self, size: int = ..., /) -> bytes: ...


def read_bounded(stream: _Readable, max_bytes: int, chunk_size: int = _CHUNK_SIZE) -> bytes:
    """Read ``stream`` fully, aborting as soon as ``max_bytes`` is exceeded.

    Never buffers more than ``max_bytes + chunk_size`` before raising, regardless of
    whether the caller supplied an accurate ``Content-Length``.
    """
    buffer = bytearray()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise UploadTooLargeError(f"upload exceeds the maximum of {max_bytes} bytes")
    return bytes(buffer)


def store_immutable_csv(root: Path, data: bytes) -> StoredFile:
    """Content-address ``data`` under ``root`` and persist it immutably."""
    digest = hashlib.sha256(data).hexdigest()
    directory = root / digest[:2]
    target = directory / f"{digest}.csv"

    if target.exists():
        if target.stat().st_size != len(data):
            raise RuntimeError(
                f"storage integrity violation: {target} size does not match its own digest"
            )
    else:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".upload-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        target.chmod(_READONLY_FILE)

    return StoredFile(
        sha256=digest,
        size_bytes=len(data),
        storage_path=str(target.relative_to(root)),
    )


__all__ = ["StoredFile", "UploadTooLargeError", "read_bounded", "store_immutable_csv"]
