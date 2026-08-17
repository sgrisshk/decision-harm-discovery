"""Internal candidate/validation-report/Finding persistence services (TASK-024).

Not exposed as public routes — matches `docs/architecture/finding-persistence-contract.md`'s API
boundary: discovery writes through an internal candidate persistence service, Statistics writes
through an internal validation persistence service, and a promotion service accepts a candidate
and a validation report and inserts exactly one Finding transactionally. The only caller today is
`scripts/promote_findings.py`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import CandidatePatternModel, FindingModel, ValidationReportModel
from app.findings.contracts import (
    CandidatePatternPersistence,
    EconomicImpactPersistence,
    LineageReference,
    PatternCondition,
    ValidationMetadataPersistence,
)
from app.findings.summary import TITLE_TEMPLATE_VERSION, generate_summary, generate_title


def persist_candidate_pattern(
    session: Session, payload: CandidatePatternPersistence
) -> CandidatePatternModel:
    """Append-only: a new row every call, never an update to an existing one."""
    model = CandidatePatternModel(
        id=payload.id,
        analysis_run_id=payload.analysis_run_id,
        candidate_key=payload.candidate_key,
        conditions=[condition.model_dump(mode="json") for condition in payload.conditions],
        fit_split=payload.fit_split,
        rank=payload.rank,
        rank_score=payload.rank_score,
        actionability=payload.actionability,
        metrics=[metric.model_dump(mode="json") for metric in payload.metrics],
        warnings=list(payload.warnings),
        artifact_sha256=payload.artifact_sha256,
        persisted_at=payload.persisted_at,
        lineage=[reference.model_dump(mode="json") for reference in payload.lineage],
    )
    session.add(model)
    session.flush()
    return model


def persist_validation_report(
    session: Session,
    candidate_pattern_id: UUID,
    payload: ValidationMetadataPersistence,
    generated_at: datetime,
    lineage: tuple[LineageReference, ...] = (),
) -> ValidationReportModel:
    """Append-only. A rejected report (`evidence_level is None`) is still persisted — for audit —
    but `promote_finding` refuses to build a Finding from one."""
    model = ValidationReportModel(
        candidate_pattern_id=candidate_pattern_id,
        contract_version=payload.contract_version,
        outcome_definition_version=payload.outcome_definition_version,
        outcome_definition=payload.outcome_definition,
        generated_at=generated_at,
        exposed_records=payload.exposed_records,
        comparison_records=payload.comparison_records,
        clustering_key=payload.clustering_key,
        raw_effect=payload.raw_effect.model_dump(mode="json"),
        adjusted_effect=(
            payload.adjusted_effect.model_dump(mode="json") if payload.adjusted_effect else None
        ),
        adjusted_p_value=payload.adjusted_p_value,
        family_size=payload.family_size,
        controlled_variables=list(payload.controlled_variables),
        potential_confounders=list(payload.potential_confounders),
        robustness_tests=list(payload.robustness_tests),
        temporal_stability=payload.temporal_stability,
        identification_design=payload.identification_design.value,
        gate_results=[gate.model_dump(mode="json") for gate in payload.gate_results],
        evidence_level=payload.evidence_level.value if payload.evidence_level else None,
        policy_readiness=payload.policy_readiness.value,
        failure_modes=list(payload.failure_modes),
        recommended_validation=payload.recommended_validation,
        warnings=list(payload.warnings),
        permitted_language=payload.permitted_language,
        lineage=[reference.model_dump(mode="json") for reference in lineage],
    )
    session.add(model)
    session.flush()
    return model


class PromotionError(ValueError):
    """A candidate/report pair fails the promotion invariant."""


def promote_finding(
    session: Session,
    *,
    dataset_id: UUID,
    analysis_run_id: UUID,
    candidate: CandidatePatternModel,
    report: ValidationReportModel,
    validation: ValidationMetadataPersistence,
    impact: EconomicImpactPersistence,
    harm_direction_phrase: str,
    generated_at: datetime,
    lineage: tuple[LineageReference, ...] = (),
) -> FindingModel:
    """Insert exactly one Finding, transactionally, or raise `PromotionError`.

    Mirrors `FindingPromotion`'s invariant: a candidate whose report has no evidence level (never
    graded, or graded and rejected) cannot become a Finding. `validation`/`impact` are the same
    already-validated Pydantic objects `report`/nothing else were built from — passed alongside the
    ORM rows rather than re-derived from them, so this never re-interprets what Statistics already
    computed.
    """
    evidence_level = report.evidence_level
    if evidence_level is None:
        raise PromotionError(
            f"candidate {candidate.candidate_key!r} has no evidence_level and cannot be promoted"
        )
    conditions = tuple(validation_conditions(candidate))
    title = generate_title(harm_direction_phrase, conditions)
    summary = generate_summary(harm_direction_phrase, conditions)
    model = FindingModel(
        dataset_id=dataset_id,
        analysis_run_id=analysis_run_id,
        candidate_pattern_id=candidate.id,
        validation_report_id=report.id,
        title=title,
        summary=summary,
        title_template_version=TITLE_TEMPLATE_VERSION,
        generated_at=generated_at,
        pattern_snapshot={
            "candidate_key": candidate.candidate_key,
            "conditions": candidate.conditions,
            "fit_split": candidate.fit_split,
            "rank": candidate.rank,
            "rank_score": candidate.rank_score,
            "actionability": candidate.actionability,
        },
        exposed_records=validation.exposed_records,
        comparison_records=validation.comparison_records,
        clustering_key=validation.clustering_key,
        evidence_level=evidence_level,
        identification_design=report.identification_design,
        validation_snapshot={
            "raw_effect": report.raw_effect,
            "adjusted_effect": report.adjusted_effect,
            "controlled_variables": report.controlled_variables,
            "potential_confounders": report.potential_confounders,
            "robustness_tests": report.robustness_tests,
            "temporal_stability": report.temporal_stability,
            # Full gate_results table is deliberately not duplicated into the Finding's
            # read-optimized snapshot (product contract §2 "Optional later" — full 16-gate detail
            # is an audit panel, not required-for-MVP); it stays queryable on `validation_reports`
            # via `validation_report_id`.
            "failure_modes": report.failure_modes,
            "recommended_validation": report.recommended_validation,
            "warnings": report.warnings,
            "permitted_language": report.permitted_language,
        },
        impact_snapshot=impact.model_dump(mode="json"),
        impact_contract_version=impact.impact_contract_version,
        policy_readiness=report.policy_readiness,
        lineage=[reference.model_dump(mode="json") for reference in lineage],
    )
    session.add(model)
    session.flush()
    return model


def validation_conditions(candidate: CandidatePatternModel) -> list[PatternCondition]:
    """`candidate.conditions` is already-persisted JSONB; re-parsed into `PatternCondition` for the
    title/summary generator, which only needs `feature`/`operator`/`value`."""
    return [PatternCondition.model_validate(condition) for condition in candidate.conditions]
