from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OUTPUT_SCHEMA_VERSION = "1.1.0"


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature: str
    operator: Literal["eq", "ge", "lt"]
    value: str | float | bool


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
    conditions: list[Condition] = Field(min_length=1, max_length=3)
    outcome: str
    sample_size: int = Field(ge=1)
    support: float = Field(ge=0, le=1)
    raw_effect: float
    economic_exposure: float
    discovery_method: str
    description: str
    warnings: list[str] = []


class CandidatesDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.1.0"]
    run_id: str
    status: Literal["PERSISTED", "INSUFFICIENT_CANDIDATES"]
    blind_bundle_id: str = Field(min_length=64, max_length=64)
    run_contract_version: str
    dataset_version: str
    dataset_identity_sha256: str = Field(min_length=64, max_length=64)
    outcome_contract_version: str
    discovery_contract_version: str
    discovery_method_version: str
    search_fit_split: str
    diagnostic_only_splits: list[str]
    selection_used_only_fit_split: bool
    input_provenance_hashes: dict[str, str]
    feature_timing_classes: dict[str, str]
    insufficiency_reason: str | None = None
    candidates: list[Candidate]

    @model_validator(mode="after")
    def validate_candidate_count(self) -> CandidatesDocument:
        count = len(self.candidates)
        if self.status == "PERSISTED" and not 10 <= count <= 20:
            raise ValueError("PERSISTED output must contain 10-20 candidates")
        if self.status == "INSUFFICIENT_CANDIDATES":
            if count >= 10:
                raise ValueError("INSUFFICIENT_CANDIDATES output must contain fewer than 10")
            if not self.insufficiency_reason or not self.insufficiency_reason.strip():
                raise ValueError("insufficient candidate output requires insufficiency_reason")
        return self


class MetricsDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.1.0"]
    run_id: str
    evaluated_hypotheses: int = Field(ge=0)
    random_seed: int
    run_contract_version: str
    dataset_identity_sha256: str = Field(min_length=64, max_length=64)
    discovery_method_version: str
    search_fit_split: str
    selection_used_only_fit_split: bool
