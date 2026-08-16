"""Structural upload validation.

Deliberately shallow: extension/character/size/encoding sanity only. Column-level
schema and type profiling belongs to TASK-007, not here.
"""

from __future__ import annotations

import re

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_FILENAME_LENGTH = 255


class IngestionValidationError(ValueError):
    """Raised when an uploaded file fails structural validation."""


def sanitize_filename(raw: str) -> str:
    """Reduce a client-supplied filename to a safe basename.

    Rejects path separators, traversal, hidden/dot-only names, unsafe characters,
    excessive length, and anything not ending in ``.csv``.
    """
    name = raw.strip()
    if not name:
        raise IngestionValidationError("filename must not be empty")
    if "/" in name or "\\" in name:
        raise IngestionValidationError("filename must not contain path separators")
    if name in {".", ".."} or name.startswith("."):
        raise IngestionValidationError("filename must not be a hidden or relative name")
    if len(name) > _MAX_FILENAME_LENGTH:
        raise IngestionValidationError("filename exceeds maximum length")
    if not name.lower().endswith(".csv"):
        raise IngestionValidationError("only .csv uploads are accepted")
    if not _SAFE_FILENAME.fullmatch(name):
        raise IngestionValidationError("filename contains unsupported characters")
    return name


def validate_csv_content(data: bytes) -> None:
    """Sniff-check that ``data`` is plausibly a non-empty, text CSV body."""
    if not data:
        raise IngestionValidationError("uploaded file is empty")
    if b"\x00" in data:
        raise IngestionValidationError("uploaded file contains binary data")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionValidationError("uploaded file is not valid UTF-8 text") from exc
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if not any(delimiter in first_line for delimiter in (",", ";", "\t")):
        raise IngestionValidationError("uploaded file has no recognizable CSV header")
