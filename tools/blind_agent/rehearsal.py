from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from tools.blind_agent.models import CandidatesDocument, MetricsDocument

OUTPUT_NAMES = {"candidates.json", "discovery_metrics.json", "run_report.md"}


def _fixture_program() -> str:
    candidates = [
        {
            "candidate_id": f"rehearsal-{number:02d}",
            "conditions": [{"feature": "fixture_group", "operator": "eq", "value": number}],
            "outcome": "fixture_outcome",
            "sample_size": 10,
            "support": 0.1,
            "raw_effect": float(number) / 100,
            "economic_exposure": float(number),
            "discovery_method": "rehearsal-only",
            "description": f"Non-causal infrastructure rehearsal candidate {number}",
            "warnings": ["Synthetic rehearsal output; not analytical evidence."],
        }
        for number in range(1, 11)
    ]
    candidate_document = {
        "schema_version": "1.1.0",
        "run_id": "blind-infrastructure-rehearsal",
        "status": "PERSISTED",
        "blind_bundle_id": "a" * 64,
        "run_contract_version": "rehearsal-1",
        "dataset_version": "rehearsal-1",
        "dataset_identity_sha256": "b" * 64,
        "outcome_contract_version": "rehearsal-1",
        "discovery_contract_version": "rehearsal-1",
        "discovery_method_version": "rehearsal-1",
        "search_fit_split": "fixture",
        "diagnostic_only_splits": [],
        "selection_used_only_fit_split": True,
        "input_provenance_hashes": {"public/rehearsal.py": "c" * 64},
        "feature_timing_classes": {"fixture_group": "decision_time"},
        "insufficiency_reason": None,
        "candidates": candidates,
    }
    metrics_document = {
        "schema_version": "1.1.0",
        "run_id": "blind-infrastructure-rehearsal",
        "evaluated_hypotheses": 10,
        "random_seed": 0,
        "run_contract_version": "rehearsal-1",
        "dataset_identity_sha256": "b" * 64,
        "discovery_method_version": "rehearsal-1",
        "search_fit_split": "fixture",
        "selection_used_only_fit_split": True,
    }
    program = f'''# CREATE_REHEARSAL_OUTPUTS
from pathlib import Path
import json

output = Path("output")
output.mkdir(exist_ok=True)
candidates = {candidate_document!r}
metrics = {metrics_document!r}
(output / "candidates.json").write_text(json.dumps(candidates), encoding="utf-8")
(output / "discovery_metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
(output / "run_report.md").write_text(
    "# Blind actor infrastructure rehearsal\\n\\n"
    "This is schema validation test data, not discovery evidence.\\n",
    encoding="utf-8",
)
'''
    padding = "\n".join(f"# bounded pagination fixture line {number}" for number in range(1, 301))
    return f"{program}\n{padding}\n"


def prepare_fixture(root: Path) -> None:
    public = root / "public"
    output = root / "output"
    agents = root / "agents"
    public.mkdir(parents=True)
    output.mkdir()
    agents.mkdir()
    (public / "rehearsal.py").write_text(_fixture_program(), encoding="utf-8")
    (agents / "ML_DISCOVERY_BLIND.md").write_text(
        "Infrastructure rehearsal only. Follow the actor system instructions.\n",
        encoding="utf-8",
    )
    (root / "BLIND_MANIFEST.json").write_text(
        json.dumps({"run_id": "blind-infrastructure-rehearsal", "private_truth": False}),
        encoding="utf-8",
    )
    root.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    output.chmod(stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)


def validate_outputs(output: Path) -> None:
    actual = {path.name for path in output.iterdir() if path.is_file()}
    if actual != OUTPUT_NAMES:
        raise RuntimeError(f"rehearsal outputs mismatch: {sorted(actual)}")
    CandidatesDocument.model_validate_json((output / "candidates.json").read_text())
    MetricsDocument.model_validate_json((output / "discovery_metrics.json").read_text())
    if not (output / "run_report.md").read_text().strip():
        raise RuntimeError("rehearsal run_report.md is empty")


def rehearse(image: str, model: str) -> None:
    if "@sha256:" not in image:
        raise RuntimeError("rehearsal requires an immutable image digest")
    if not os.environ.get("PROVIDER_API_KEY"):
        raise RuntimeError("PROVIDER_API_KEY is required")
    with tempfile.TemporaryDirectory(prefix="policy-blind-rehearsal-") as raw_root:
        root = Path(raw_root)
        prepare_fixture(root)
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network=bridge",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m",
                "-e",
                "HOME=/tmp",
                "-e",
                "PROVIDER_API_KEY",
                "--mount",
                f"type=bind,src={root},dst=/workspace,readonly",
                "--mount",
                f"type=bind,src={root / 'output'},dst=/workspace/output",
                image,
                "python",
                "/opt/blind/provider_actor.py",
                "--model",
                model,
                "--rehearsal",
            ],
            check=True,
            env=os.environ.copy(),
        )
        validate_outputs(root / "output")
    print("BLIND_REHEARSAL_VALID")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    rehearse(args.image, args.model)


if __name__ == "__main__":
    main()
