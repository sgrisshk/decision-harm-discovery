"""TASK-115 shared helpers: wires `discover_candidates`'s new `refine_with_validation` callback
(`discovery-engine-v0.6.4`, `ADR-116`) to the real, frozen `run_validation` (contract 1.3.0),
batched once per `discover_candidates()` call, exactly as `TASK-114`'s own precedent for probe
validation (`docs/benchmark/task-114-evidence/step4_validate_chains.py`: "these rules are
additional probes within the same real search family, not a new search" -- the probe candidates
here reuse the real seed's own already-computed `evaluated_hypotheses` family size for the same
reason, not a fresh multiplicity family).

Never imported by `packages/analytics/src/policy_analytics/discovery/engine.py` itself -- engine.py
only accepts a plain callback; this module is the evidence-script-side wiring, kept entirely in
`docs/benchmark/`, matching the project's existing discipline of not giving `discovery/` any import
of `validation/`.
"""
from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path
from typing import Any, cast


def make_refinement_validator(
    mods: dict[str, Any],
    draw: Any,
    validation_outcome: Any,
    outcome_version: str,
    run_id_prefix: str,
) -> Any:
    """Returns the `refine_with_validation` callback `discover_candidates` calls at most once per
    invocation, with the full batch of admissible one-literal descendants it wants checked plus
    this search's own real `evaluated_hypotheses` count (passed by the engine itself -- see
    `RefinementValidator`'s docstring in `engine.py`).
    """
    engine = mods["engine"]
    validation_mod = importlib.import_module("policy_analytics.validation.apply")
    counter = {"n": 0}

    def validator(rules: list[tuple[Any, ...]], family_size: int) -> set[tuple[Any, ...]]:
        counter["n"] += 1
        probe_id = f"{run_id_prefix}-refineprobe{counter['n']:02d}"
        with tempfile.TemporaryDirectory(prefix=f"task115-{probe_id}-") as tmp:
            candidate_docs: list[dict[str, Any]] = []
            for i, rule in enumerate(rules, start=1):
                candidate_docs.append(
                    {
                        "candidate_id": f"REFINEPROBE-{i:04d}",
                        "conditions": [
                            {"feature": c.feature, "operator": c.operator, "value": c.value}
                            for c in rule
                        ],
                    }
                )
            doc = {
                "methodology_version": engine.DISCOVERY_METHOD_VERSION,
                "search": {"evaluated_hypotheses": family_size},
                "candidate_count": len(candidate_docs),
                "candidates": candidate_docs,
                "status": "PERSISTED",
                "run_id": probe_id,
            }
            cpath = Path(tmp) / "candidates.json"
            cpath.write_text(json.dumps(doc, default=str), encoding="utf-8")
            validations, summary = validation_mod.run_validation(
                dataset_root=draw.root,
                candidates_path=cpath,
                outcome=validation_outcome,
                dataset_version=str(draw.manifest["dataset_version"]),
                outcome_definition_version=outcome_version,
                analysis_run_id=probe_id,
            )
            if int(summary["family_size"]) != family_size:
                raise SystemExit(f"{probe_id}: refinement-probe family size mismatch")
        passed: set[tuple[Any, ...]] = set()
        for rule, validation in zip(rules, validations, strict=True):
            if validation.verdict != "REJECT":  # PASS or DOWNGRADE both count -- TASK-114 §6
                passed.add(rule)
        return passed

    return validator
