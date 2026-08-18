"""One-shot promotion of a frozen, validated blind run into persisted Findings (TASK-024).

Reads four real frozen artifacts for a given run (discovery candidates, TASK-016 ranking, TASK-019
validation report, and the discovery-metrics document), persists one `AnalysisRun` and all
`CandidatePattern`/`ValidationReport` rows, and promotes every candidate whose report has a
non-null `evidence_level` to `Finding`.

Per `docs/product/finding-product-contract.md` §0, a "Finding" is any graded candidate output
(evidence + impact) — not only a `PASS`-verdict/`SHADOW_POLICY` one. The `PASS`/`DOWNGRADE`
distinction lives in `evidence_level`/`policy_readiness` on each Finding, not in whether it exists
at all.

**Paths are parametrized (`--candidates`/`--metrics`/`--ranking`/`--validation-report`), not
hardcoded to one run** — mirrors `scripts/evaluate_benchmark.py`/`scripts/rank_candidates.py`'s own
CLI convention. The defaults point at `task-058-remediation-20260817-001`, the current PROMISING-
verdict closing run (`ADR-025`); the original `task-015-official-20260816-015` predates that
remediation and graded FAILED overall (`ADR-019`) — pass its paths explicitly if that historical
run is ever needed again, never rely on stale defaults.

Internal script, not a public API — matches
`docs/architecture/finding-persistence-contract.md`'s boundary. Not idempotent: this is a one-shot
demo entrypoint against a fresh (or already-seeded-once) database, not a repeatable pipeline stage
— rerunning against the same database inserts a second `AnalysisRun`/duplicate `Finding` set rather
than upserting.

Usage:
  uv run python scripts/promote_findings.py
  uv run python scripts/promote_findings.py \\
      --candidates artifacts/blind/task-015-official-20260816-015.candidates.json \\
      --metrics artifacts/blind/task-015-official-20260816-015.discovery_metrics.json \\
      --ranking \\
        artifacts/discovery/task-016-candidate-ranking-task-015-official-20260816-015.json \\
      --validation-report artifacts/validation/task-019-official-20260816-015.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "apps/api"))
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402
from app.db.models import AnalysisRunModel, DatasetModel  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.findings.contracts import (  # noqa: E402
    CandidateMetric,
    CandidatePatternPersistence,
    EconomicImpactPersistence,
    LineageReference,
    PatternCondition,
    ValidationMetadataPersistence,
)
from app.findings.persistence import (  # noqa: E402
    PromotionError,
    persist_candidate_pattern,
    persist_validation_report,
    promote_finding,
)
from policy_analytics.discovery.actionability import actionability_label  # noqa: E402
from policy_analytics.outcomes.contract import (  # noqa: E402
    DATASET_IDENTITY_SHA256,
    DATASET_VERSION,
    OutcomeDefinition,
    primary_outcome,
)
from policy_analytics.validation.apply import (  # noqa: E402
    Condition,
    Operator,
    load_analytical_frame,
    rule_expr,
    split_stats,
)
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

_DEFAULT_RUN_ID = "task-058-remediation-20260817-001"
DEFAULT_CANDIDATES_PATH = REPOSITORY / f"artifacts/blind/{_DEFAULT_RUN_ID}.candidates.json"
DEFAULT_METRICS_PATH = REPOSITORY / f"artifacts/blind/{_DEFAULT_RUN_ID}.discovery_metrics.json"
DEFAULT_RANKING_PATH = (
    REPOSITORY / f"artifacts/discovery/task-016-candidate-ranking-{_DEFAULT_RUN_ID}.json"
)
DEFAULT_VALIDATION_PATH = (
    REPOSITORY / "artifacts/validation/task-019-official-20260817-task-058-remediation-001.json"
)
ANALYTICAL_DATASET_DIR = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
SPLITS = ("development", "validation", "future_holdout")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote a frozen, validated blind run's candidates into persisted Findings."
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--ranking", type=Path, default=DEFAULT_RANKING_PATH)
    parser.add_argument("--validation-report", type=Path, default=DEFAULT_VALIDATION_PATH)
    return parser.parse_args()


# The fields ValidationReport.to_dict() emits that ValidationMetadataPersistence (deliberately)
# does not model — request/run identity lives on CandidatePattern/AnalysisRun instead.
_VALIDATION_REPORT_EXTRA_KEYS = frozenset(
    {"analysis_run_id", "candidate_id", "dataset_version", "pattern_definition"}
)

# The real closing run only ever uses this subset (verified against the frozen artifact); the
# split-metric recomputation below only needs to handle what apply.py's own Condition/Operator
# supports.
_SPLIT_METRIC_OPERATORS = frozenset({"eq", "ge", "lt"})


def _sha256_of(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _directory_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _to_apply_operator(operator: str) -> Operator:
    if operator not in _SPLIT_METRIC_OPERATORS:
        raise ValueError(f"unsupported operator for split-metric recomputation: {operator!r}")
    return cast(Operator, operator)


def _ensure_analytical_dataset(session: Session) -> DatasetModel:
    """The analytical dataset is a 3-file directory (features/outcomes/metadata), not a single
    CSV — forcing it through TASK-006's single-file upload contract would be a worse fit than a
    direct, honestly-labeled row (see plan scope notes)."""
    existing = session.scalars(
        select(DatasetModel).where(DatasetModel.checksum_sha256 == DATASET_IDENTITY_SHA256)
    ).first()
    if existing is not None:
        return existing
    dataset = DatasetModel(
        name="travel-bookings-analytical",
        source_filename="travel-bookings-analytical-v1.0.0/",
        version=1,
        status="completed",
        checksum_sha256=DATASET_IDENTITY_SHA256,
        size_bytes=_directory_size(ANALYTICAL_DATASET_DIR),
        content_type="application/x-directory+csv",
        source_type="synthetic_benchmark_analytical",
        storage_path=str(ANALYTICAL_DATASET_DIR.relative_to(REPOSITORY)),
    )
    session.add(dataset)
    session.flush()
    return dataset


def _build_analysis_run(
    session: Session,
    dataset: DatasetModel,
    candidates_doc: dict[str, Any],
    metrics_doc: dict[str, Any],
    validation_doc: dict[str, Any],
    ranking_doc: dict[str, Any],
    lineage: tuple[LineageReference, ...],
) -> AnalysisRunModel:
    run = AnalysisRunModel(
        dataset_id=dataset.id,
        dataset_version=dataset.version,
        analytical_dataset_version=str(candidates_doc["dataset_version"]),
        analytical_dataset_identity_sha256=str(candidates_doc["dataset_identity_sha256"]),
        code_version=str(candidates_doc["discovery_method_version"]),
        discovery_methodology_version=str(candidates_doc["discovery_method_version"]),
        outcome_definition_version=str(validation_doc["outcome_contract_version"]),
        validation_contract_version=str(validation_doc["validation_contract_version"]),
        configuration={
            "run_id": candidates_doc["run_id"],
            "ranking_method_version": ranking_doc["ranking_method_version"],
            "ranking_weights": ranking_doc["weights"],
        },
        random_seed=int(metrics_doc["random_seed"]),
        evaluated_hypotheses=int(metrics_doc["evaluated_hypotheses"]),
        status="completed",
        lineage=[reference.model_dump(mode="json") for reference in lineage],
    )
    session.add(run)
    session.flush()
    return run


def _compute_metrics(
    frame: pl.DataFrame, conditions: tuple[Condition, ...], outcome: OutcomeDefinition
) -> tuple[CandidateMetric, ...]:
    metrics: list[CandidateMetric] = []
    full_mask = frame.select(rule_expr(conditions).alias("m"))["m"]
    for split in SPLITS:
        split_frame = frame.filter(frame["split_label"] == split)  # pyright: ignore[reportUnknownMemberType]
        split_mask = full_mask.filter(frame["split_label"] == split)  # pyright: ignore[reportUnknownMemberType]
        stats = split_stats(split_frame, split_mask, outcome, split)
        if stats is None:
            continue
        metrics.append(
            CandidateMetric(
                split=cast(Any, split),
                n_population=stats.n_population,
                n_exposed=stats.n_exposed,
                support=stats.n_exposed / stats.n_population,
                exposed_mean=stats.exposed_mean,
                comparison_mean=stats.comparison_mean,
                raw_difference=stats.raw_difference,
                harm_per_booking=stats.harm_per_booking,
                historical_exposure=stats.harm_per_booking * stats.n_exposed,
            )
        )
    if not metrics:
        raise RuntimeError("no split produced usable metrics for a candidate")
    return tuple(metrics)


def _promote_one(
    session: Session,
    *,
    dataset: DatasetModel,
    run: AnalysisRunModel,
    frame: pl.DataFrame,
    outcome: OutcomeDefinition,
    raw_candidate: dict[str, Any],
    ranking_by_id: dict[str, Any],
    validation_by_id: dict[str, Any],
    candidates_path: Path,
    validation_path: Path,
    candidates_sha256: str,
    validation_sha256: str,
    validation_frozen_at: datetime,
) -> bool:
    """Persists the candidate pattern and validation report unconditionally; promotes to a
    Finding only if the report has a non-null evidence level. Returns whether it was promoted."""
    candidate_id = cast(str, raw_candidate["candidate_id"])
    conditions = tuple(
        PatternCondition.model_validate(c) for c in cast(list[Any], raw_candidate["conditions"])
    )
    apply_conditions = tuple(
        Condition(c.feature, _to_apply_operator(c.operator), c.value) for c in conditions
    )
    metrics = _compute_metrics(frame, apply_conditions, outcome)
    candidate_payload = CandidatePatternPersistence(
        id=uuid4(),
        analysis_run_id=run.id,
        candidate_key=candidate_id,
        conditions=conditions,
        fit_split="development",
        rank=ranking_by_id[candidate_id]["rank"],
        rank_score=ranking_by_id[candidate_id]["rank_score"],
        actionability=actionability_label(list(apply_conditions)),
        metrics=metrics,
        warnings=tuple(raw_candidate.get("warnings", ())),
        artifact_sha256=_sha256_of(raw_candidate),
        persisted_at=datetime.now(UTC),
        lineage=(
            LineageReference(
                kind="candidate_artifact",
                uri=f"{candidates_path}#{candidate_id}",
                sha256=candidates_sha256,
            ),
        ),
    )
    candidate_row = persist_candidate_pattern(session, candidate_payload)

    raw_report = dict(cast(dict[str, Any], validation_by_id[candidate_id]["validation_report"]))
    for key in _VALIDATION_REPORT_EXTRA_KEYS:
        raw_report.pop(key, None)
    validation_payload = ValidationMetadataPersistence.model_validate(raw_report)
    report_row = persist_validation_report(
        session,
        candidate_row.id,
        validation_payload,
        generated_at=validation_frozen_at,
        lineage=(
            LineageReference(
                kind="validation_report",
                uri=f"{validation_path}#{candidate_id}",
                sha256=validation_sha256,
            ),
        ),
    )

    if validation_payload.evidence_level is None:
        return False

    raw_impact = validation_by_id[candidate_id]["economic_impact"]
    impact_payload = EconomicImpactPersistence.model_validate(raw_impact)
    try:
        promote_finding(
            session,
            dataset_id=dataset.id,
            analysis_run_id=run.id,
            candidate=candidate_row,
            report=report_row,
            validation=validation_payload,
            impact=impact_payload,
            harm_direction_phrase=outcome.harm_direction_phrase,
            generated_at=validation_frozen_at,
            lineage=(
                LineageReference(
                    kind="impact_report",
                    uri=f"{validation_path}#{candidate_id}",
                    sha256=validation_sha256,
                ),
            ),
        )
    except PromotionError as exc:  # pragma: no cover - defense in depth
        raise RuntimeError(f"unexpected promotion failure for {candidate_id}") from exc
    return True


def main() -> None:
    args = parse_args()
    candidates_path: Path = args.candidates.resolve()
    validation_path: Path = args.validation_report.resolve()

    candidates_doc = _load_json(candidates_path)
    metrics_doc = _load_json(args.metrics.resolve())
    ranking_doc = _load_json(args.ranking.resolve())
    validation_doc = _load_json(validation_path)
    assert candidates_doc["dataset_identity_sha256"] == DATASET_IDENTITY_SHA256
    assert candidates_doc["dataset_version"] == DATASET_VERSION

    outcome = primary_outcome()
    frame = load_analytical_frame(ANALYTICAL_DATASET_DIR)
    ranking_by_id = {c["candidate_id"]: c for c in cast(list[Any], ranking_doc["candidates"])}
    validation_by_id = {c["candidate_id"]: c for c in cast(list[Any], validation_doc["candidates"])}
    validation_frozen_at = datetime.fromisoformat(str(validation_doc["frozen_at"]))

    candidates_sha256 = _sha256_of(candidates_doc)
    validation_sha256 = _sha256_of(validation_doc)
    run_lineage = (
        LineageReference(
            kind="candidate_artifact", uri=str(candidates_path), sha256=candidates_sha256
        ),
        LineageReference(
            kind="validation_report", uri=str(validation_path), sha256=validation_sha256
        ),
    )

    session = SessionLocal()
    try:
        dataset = _ensure_analytical_dataset(session)
        run = _build_analysis_run(
            session, dataset, candidates_doc, metrics_doc, validation_doc, ranking_doc, run_lineage
        )

        promoted = 0
        for raw_candidate in cast(list[dict[str, Any]], candidates_doc["candidates"]):
            if _promote_one(
                session,
                dataset=dataset,
                run=run,
                frame=frame,
                outcome=outcome,
                raw_candidate=raw_candidate,
                ranking_by_id=ranking_by_id,
                validation_by_id=validation_by_id,
                candidates_path=candidates_path,
                validation_path=validation_path,
                candidates_sha256=candidates_sha256,
                validation_sha256=validation_sha256,
                validation_frozen_at=validation_frozen_at,
            ):
                promoted += 1

        session.commit()
        total = len(cast(list[Any], candidates_doc["candidates"]))
        print(
            f"Persisted analysis_run={run.id} ({args.candidates.name}) with "
            f"{total} candidate_patterns/validation_reports, promoted {promoted} findings."
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
