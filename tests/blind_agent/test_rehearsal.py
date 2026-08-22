from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tools.blind_agent import rehearsal


def test_rehearsal_uses_deterministic_networkless_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = tmp_path / "run"
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def fake_resolve_image(image: str) -> dict[str, str]:
        return {"image": image}

    monkeypatch.setattr(rehearsal, "resolve_image", fake_resolve_image)

    def fake_prepare(*args: Any, **kwargs: Any) -> Path:
        calls.append(("prepare", args, kwargs))
        return run_root

    def fake_launch(*args: Any, **kwargs: Any) -> list[str]:
        calls.append(("launch", args, kwargs))
        return []

    def fake_freeze(*args: Any, **kwargs: Any) -> Path:
        calls.append(("freeze", args, kwargs))
        return run_root / "frozen"

    monkeypatch.setattr(rehearsal, "prepare", fake_prepare)
    monkeypatch.setattr(rehearsal, "launch", fake_launch)
    monkeypatch.setattr(rehearsal, "freeze", fake_freeze)

    rehearsal.rehearse("actor@sha256:" + "a" * 64, "travel")

    assert [name for name, _, _ in calls] == ["prepare", "launch", "freeze"]
    assert calls[0][1][-3:] == ("deterministic", None, "travel")
    assert calls[1][1][2] == "deterministic"
    assert calls[1][2]["provider_network"] is False
    assert calls[1][2]["dataset_selector"] == "travel"
