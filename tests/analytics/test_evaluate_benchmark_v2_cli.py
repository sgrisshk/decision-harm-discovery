"""TASK-107 Phase 2a: end-to-end test of `scripts/evaluate_benchmark_v2.py` on tracked files only.

The v1 ground truth is re-labelled `travel-v2` with test-only strata; the committed TASK-103 run1
validation and candidates (v0.6.2, 15 broad candidates) are the input. No engine is run.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "scripts"))

import evaluate_benchmark_v2 as cli  # noqa: E402

pytestmark = pytest.mark.analytics

V1_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
V1_GT = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
STRATA = {
    "P01": "core",
    "P08": "core",
    "P07": "core",
    "P02": "out_of_language",
    "P09": "out_of_language",
    "P03": "declared_overlap",
    "P04": "declared_overlap",
    "P05": "declared_overlap",
    "P06": "declared_overlap",
}


def _inputs(tmp_path: Path, benchmark_id: str = "travel-v2") -> tuple[Path, Path]:
    gt: dict[str, Any] = json.loads(V1_GT.read_text(encoding="utf-8"))
    gt["benchmark_id"] = benchmark_id
    gt["benchmark_version"] = "2.0.0-test"
    for p in gt["patterns"]:
        p["stratum"] = STRATA[p["id"]]
    gt_path = tmp_path / "gt.json"
    gt_path.write_text(json.dumps(gt), encoding="utf-8")
    base = REPOSITORY / "docs/benchmark/task-103-evidence/run1"
    validation = json.loads((base / "validation.json").read_text(encoding="utf-8"))
    validation["candidates_source"] = str(base / "candidates.json")
    report = tmp_path / "validation.json"
    report.write_text(json.dumps(validation), encoding="utf-8")
    return gt_path, report


def _argv(gt: Path, report: Path, out: Path, *extra: str) -> list[str]:
    return [
        "--validation-report",
        str(report),
        "--dataset-root",
        str(V1_ROOT),
        "--ground-truth",
        str(gt),
        "--output",
        str(out),
        *extra,
    ]


def test_end_to_end_on_v062_run1_reports_no_specific_recovery_and_no_bare_ratio(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gt, report = _inputs(tmp_path)
    out = tmp_path / "eval.json"
    cli.main(_argv(gt, report, out))
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["benchmark_id"] == "travel-v2"
    assert result["comparable_to_other_benchmark_ids"] is False
    assert result["status"] == "FROZEN"
    assert result["inputs"]["contract_version"] == "1.3.0"
    assert set(result["inputs"]["scorer_sha256"]) == {
        "evaluate_benchmark_v2.py",
        "benchmark_v2_scoring.py",
    }
    for name, stratum in result["strata"].items():
        assert stratum["specific_targets"]["0.50"] == [], name
    text = result["rendered_report"]
    assert "reached predictive_association under the v2 recovery contract" in text
    for ratio in re.finditer(r"\d+/\d+", text):
        assert text[ratio.end() :].startswith(" benchmark targets")
    assert capsys.readouterr().out.strip().endswith(text.splitlines()[-1])


def test_refuses_a_ground_truth_of_another_benchmark_id(tmp_path: Path) -> None:
    gt, report = _inputs(tmp_path, benchmark_id="travel-v1")
    with pytest.raises(SystemExit, match="benchmark_id"):
        cli.main(_argv(gt, report, tmp_path / "eval.json"))


def test_refuses_to_overwrite_a_frozen_result(tmp_path: Path) -> None:
    gt, report = _inputs(tmp_path)
    out = tmp_path / "eval.json"
    cli.main(_argv(gt, report, out))
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        cli.main(_argv(gt, report, out))
    cli.main(_argv(gt, report, out, "--force"))


def test_unknown_stratum_is_rejected(tmp_path: Path) -> None:
    gt_path, report = _inputs(tmp_path)
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    gt["patterns"][0]["stratum"] = "primary"
    gt_path.write_text(json.dumps(gt), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown stratum"):
        cli.main(_argv(gt_path, report, tmp_path / "eval.json"))
