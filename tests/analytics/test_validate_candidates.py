"""Regression test for `scripts/validate_candidates.py`'s default (travel) CLI behavior.

`HANDOFF-065` changed `main()` to bind its outcome via `outcome_definition_from_manifest` instead of
a hardcoded `primary_outcome()` import. `manifest_binding`'s own pass-through guarantee is unit-
tested directly (`test_manifest_binding.py`); this test instead exercises the actual wiring in
`main()` — the risk `HANDOFF-065` introduced was a CLI-level regression (e.g. accidentally binding
travel to a provisional path), not the underlying binding function, which is already covered.

Marked `slow`: a full default run takes ~20s (15 candidates x the full G01-G11 gate pipeline).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "scripts"))
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.outcomes.contract import (  # noqa: E402
    DATASET_VERSION,
    OUTCOME_CONTRACT_VERSION,
    primary_outcome,
)
from policy_analytics.validation.contract import CONTRACT_VERSION  # noqa: E402
from validate_candidates import DEFAULT_CANDIDATES_PATH, DEFAULT_DATASET_ROOT, main  # noqa: E402

pytestmark = [pytest.mark.analytics, pytest.mark.slow]


def test_default_run_binds_travel_to_its_real_non_provisional_outcome(tmp_path: Path) -> None:
    output_path = tmp_path / "regression-check.json"

    main(["--output", str(output_path)])
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    # The exact identity check that matters: HANDOFF-065's manifest-binding wiring must resolve
    # travel to the real, Product-reviewed primary_outcome() -- never a provisional derivation --
    # and record its real contract version, not some other dataset's.
    assert payload["outcome_id"] == primary_outcome().outcome_id
    assert payload["outcome_contract_version"] == OUTCOME_CONTRACT_VERSION
    assert payload["dataset_version"] == DATASET_VERSION
    assert payload["validation_contract_version"] == CONTRACT_VERSION
    assert payload["hidden_ground_truth_opened"] is False
    assert payload["candidates_source"] == str(DEFAULT_CANDIDATES_PATH)

    manifest = json.loads((DEFAULT_DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert payload["dataset_identity_sha256"] == manifest["dataset_identity_sha256"]

    # Every persisted candidate got a verdict; none were silently dropped by the outcome rewiring.
    candidates_payload = json.loads(DEFAULT_CANDIDATES_PATH.read_text(encoding="utf-8"))
    assert len(payload["candidates"]) == len(candidates_payload["candidates"])
    assert sum(payload["verdict_counts"].values()) == len(candidates_payload["candidates"])


def test_full_non_travel_cli_runs_on_public_b2b_analytical_artifacts(tmp_path: Path) -> None:
    dataset_root = (
        REPOSITORY / "synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0"
    )
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    candidate = {
        "candidate_id": "PUBLIC-PORTABILITY-001",
        "conditions": [{"feature": "competitor_involved", "operator": "eq", "value": True}],
        "outcome": "net_deal_contribution_usd",
    }
    candidates_path = tmp_path / "public-candidates.json"
    candidates_path.write_text(
        json.dumps(
            {
                "status": "PERSISTED",
                "dataset_version": manifest["dataset_version"],
                "dataset_identity_sha256": manifest["dataset_identity_sha256"],
                "outcome_contract_version": manifest["outcome_contract"]["version"],
                "search": {"evaluated_hypotheses": 10},
                "candidates": [
                    {**candidate, "candidate_id": f"PUBLIC-PORTABILITY-{index:03d}"}
                    for index in range(1, 11)
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "b2b-validation.json"
    main(
        [
            "--dataset-root",
            str(dataset_root),
            "--candidates",
            str(candidates_path),
            "--output",
            str(output),
            "--analysis-run-id",
            "public-b2b-portability",
            "--no-blind-compliant",
            "--no-founder-block-lifted",
        ]
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["hidden_ground_truth_opened"] is False
    assert payload["dataset_version"] == "b2b_sales-analytical-v1.0.0"
    assert len(payload["candidates"]) == 10
    assert payload["run_manifest"]["clustering_column"] == "account_id"
    assert payload["run_manifest"]["seasonality_column"] == "deal_created_date"
