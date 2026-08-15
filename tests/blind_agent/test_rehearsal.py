from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from tools.blind_agent import rehearsal


def test_rehearsal_fixture_creates_schema_valid_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rehearsal.prepare_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)

    runpy.run_path(str(tmp_path / "public" / "rehearsal.py"))

    rehearsal.validate_outputs(tmp_path / "output")
    candidates = json.loads((tmp_path / "output" / "candidates.json").read_text())
    assert len(candidates["candidates"]) == 10
    assert "CREATE_REHEARSAL_OUTPUTS" in (tmp_path / "public" / "rehearsal.py").read_text()
