from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunState(StrEnum):
    CREATED = "CREATED"
    PREPARED = "PREPARED"
    VERIFIED = "VERIFIED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FROZEN = "FROZEN"
    EVALUATED = "EVALUATED"
    FAILED = "FAILED"


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    conditions: list[dict[str, Any]]
    outcome: str
    sample_size: int = Field(ge=1)
    support: float = Field(ge=0, le=1)
    raw_effect: float
    economic_exposure: float
    discovery_method: str
    warnings: list[str] = []


class CandidatesDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    run_id: str
    candidates: list[Candidate]


class MetricsDocument(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: str
    run_id: str
    evaluated_hypotheses: int = Field(ge=0)
    random_seed: int
