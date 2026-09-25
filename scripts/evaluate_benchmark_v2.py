"""CLI: score a frozen validation report against the v2 hidden ground truth (TASK-107 Phase 2a).

Adapter around the pure scorer core `policy_analytics.benchmark_v2_scoring`; the v1 scorer
(`scripts/evaluate_benchmark.py`) is untouched (its lineage helper is imported, not edited).
Phase 2a only builds and tests this scorer; no engine run on any v2 draw takes place in this phase.

Expected v2 ground truth (written in Phase 2c): `benchmark_id == "travel-v2"`, `benchmark_version`,
`patterns[]` with `id`, `stratum` in {core, challenge, declared_overlap, out_of_language}, `rule`
(ground-truth grammar), optional `canonical_in_language` (a rule string, or null when the target has
no engine-language form; default: the rule itself when it has at most three conditions and no `IN`),
and `affected_booking_ids`; `confounding_traps[]` as in v1.

The output never carries a bare `N/N` headline: every ratio is printed as
`N/M benchmark targets ...` inside a labelled sentence, per stratum, and strata are never blended
(ADR-106, ADR-107 D3/D6/D7).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

from evaluate_benchmark import (  # noqa: E402
    _parse_apparent_feature,  # pyright: ignore[reportPrivateUsage]
    _record_id_column,  # pyright: ignore[reportPrivateUsage]
    _verify_evaluation_lineage,  # pyright: ignore[reportPrivateUsage]
)
from policy_analytics import benchmark_v2_scoring as scoring  # noqa: E402
from policy_analytics.validation.apply import load_analytical_frame  # noqa: E402
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS  # noqa: E402

MAX_DEPTH = 3  # DiscoveryConfig.max_conditions


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPOSITORY))
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_targets_and_traps(
    ground_truth: dict[str, Any], space: scoring.RowSpace, index_of: dict[str, int]
) -> tuple[list[scoring.Target], list[scoring.Trap]]:
    targets: list[scoring.Target] = []
    for pattern in ground_truth["patterns"]:
        stratum = str(pattern["stratum"])
        if stratum not in scoring.STRATA:
            raise ValueError(f"pattern {pattern['id']}: unknown stratum {stratum!r}")
        conds = scoring.parse_rule(str(pattern["rule"]))
        if "canonical_in_language" in pattern:
            raw = pattern["canonical_in_language"]
            canonical = scoring.parse_rule(str(raw)) if raw is not None else None
        else:
            in_language = len(conds) <= MAX_DEPTH and all(c.operator != "in" for c in conds)
            canonical = conds if in_language else None
        targets.append(
            scoring.Target(
                target_id=str(pattern["id"]),
                stratum=stratum,
                conditions=conds,
                affected=space.ids_to_mask(index_of, pattern["affected_booking_ids"]),
                canonical_in_language=canonical,
            )
        )
    traps = [
        scoring.Trap(
            str(t["id"]), scoring.CondSpec(*_parse_apparent_feature(str(t["apparent_feature"])))
        )
        for t in ground_truth["confounding_traps"]
    ]
    return targets, traps


def _referenced_features(
    targets: list[scoring.Target], traps: list[scoring.Trap], candidates: list[scoring.Candidate]
) -> set[str]:
    conds = [c for t in targets for c in t.conditions]
    conds += [c for t in targets for c in (t.canonical_in_language or ())]
    conds += [tr.literal for tr in traps]
    conds += [c for cand in candidates for c in cand.conditions]
    return {c.feature for c in conds}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--benchmark-id", default=scoring.BENCHMARK_ID)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    output_path: Path = args.output.resolve()
    if output_path.exists() and not args.force:
        raise SystemExit(f"{output_path} exists and is a frozen result; refusing to overwrite it.")
    ground_truth_path: Path = args.ground_truth.resolve()
    ground_truth = json.loads(ground_truth_path.read_bytes())
    if ground_truth.get("benchmark_id") != args.benchmark_id:
        raise SystemExit(
            f"ground truth benchmark_id {ground_truth.get('benchmark_id')!r} != "
            f"--benchmark-id {args.benchmark_id!r}: results of different benchmark ids are never "
            "scored or compared together"
        )
    validation_path: Path = args.validation_report.resolve()
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    candidates_payload = json.loads(
        Path(validation["candidates_source"]).read_text(encoding="utf-8")
    )
    dataset_root: Path = args.dataset_root.resolve()
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    _verify_evaluation_lineage(manifest, validation, candidates_payload)

    frame = load_analytical_frame(dataset_root)
    ids: list[str] = frame[_record_id_column(manifest)].to_list()
    index_of = {b: i for i, b in enumerate(ids)}
    report_by_id = {c["candidate_id"]: c for c in validation["candidates"]}
    candidates: list[scoring.Candidate] = []
    for raw in candidates_payload["candidates"]:
        report = report_by_id[raw["candidate_id"]]["validation_report"]
        conds = tuple(
            scoring.CondSpec(str(c["feature"]), str(c["operator"]), c["value"])
            for c in raw["conditions"]
        )
        candidates.append(
            scoring.Candidate(
                candidate_id=str(raw["candidate_id"]),
                conditions=conds,
                evidence_level=report["evidence_level"],
                policy_readiness=str(report["policy_readiness"]),
            )
        )
    columns: dict[str, list[Any]] = {}
    dev_mask = 0
    for i, label in enumerate(frame["split_label"].to_list()):
        if label == "development":
            dev_mask |= 1 << i
    # Targets need the row space to build affected masks, so start with a minimal one and extend.
    placeholder = scoring.RowSpace({"_": [None] * len(ids)}, dev_mask)
    targets, traps = build_targets_and_traps(ground_truth, placeholder, index_of)
    for feature in sorted(_referenced_features(targets, traps, candidates)):
        if feature in frame.columns:
            columns[feature] = frame[feature].to_list()
        elif feature == "booking_month":
            columns[feature] = [
                date.fromisoformat(str(d)).month for d in frame["booking_date"].to_list()
            ]
        else:
            raise SystemExit(f"feature {feature!r} is not a column of the dataset")
    space = scoring.RowSpace(columns or {"_": [None] * len(ids)}, dev_mask)
    result = scoring.score(space, targets, traps, candidates)
    result["benchmark_version"] = ground_truth.get("benchmark_version")
    result["inputs"] = {
        "validation_report": _display_path(validation_path),
        "dataset_root": _display_path(dataset_root),
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "ground_truth": _display_path(ground_truth_path),
        "ground_truth_sha256": _sha256(ground_truth_path),
        "scorer_sha256": {
            "evaluate_benchmark_v2.py": _sha256(Path(__file__)),
            "benchmark_v2_scoring.py": _sha256(
                REPOSITORY / "packages/analytics/src/policy_analytics/benchmark_v2_scoring.py"
            ),
        },
        "engine_sha256": _sha256(
            REPOSITORY / "packages/analytics/src/policy_analytics/discovery/engine.py"
        ),
        "contract_version": DEFAULT_THRESHOLDS.version,
    }
    result["status"] = "FROZEN"
    result["frozen_at"] = datetime.now(UTC).isoformat()
    report_text = scoring.render_report(result, seed_label=_display_path(dataset_root))
    result["rendered_report"] = report_text
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {_display_path(output_path)}")
    print(report_text)


if __name__ == "__main__":
    main()
