from datetime import datetime
from typing import Any
from uuid import UUID

from policy_schemas.domain import DatasetColumn, EvidenceLevel, ResourceStatus
from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class HealthResponse(ApiModel):
    status: str


class DatasetRead(ApiModel):
    id: UUID
    name: str
    source_filename: str
    version: int
    status: ResourceStatus
    checksum_sha256: str
    size_bytes: int
    content_type: str
    source_type: str
    columns: list[DatasetColumn]
    created_at: datetime
    updated_at: datetime


class AnalysisRunCreate(ApiModel):
    dataset_id: UUID
    code_version: str = Field(min_length=1, max_length=100)
    configuration: dict[str, Any] = Field(default_factory=dict)
    random_seed: int = Field(ge=0, le=2**32 - 1)


class AnalysisRunRead(ApiModel):
    id: UUID
    dataset_id: UUID
    dataset_version: int
    code_version: str
    configuration: dict[str, Any]
    random_seed: int
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime


class FindingRead(ApiModel):
    id: UUID
    dataset_id: UUID
    analysis_run_id: UUID
    title: str
    pattern_definition: dict[str, Any]
    sample_size: int
    evidence_level: EvidenceLevel
    status: ResourceStatus
    warnings: list[str]
    created_at: datetime
    updated_at: datetime
