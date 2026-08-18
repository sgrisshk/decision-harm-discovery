"""Input contract for `POST /findings/{id}/feedback` (`TASK-035`).

Field set, valid combinations, and validation rule mirror
`docs/product/finding-feedback-contract.md` §2-§4 exactly — this module adds no new semantics.
"""

from __future__ import annotations

from datetime import date

from policy_schemas.domain import (
    FeedbackActionability,
    FeedbackCertainty,
    FeedbackCommitmentStrength,
    FeedbackNovelty,
    FeedbackTag,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_session: str = Field(min_length=1, max_length=256)
    novelty: FeedbackNovelty | None = None
    actionability: FeedbackActionability | None = None
    tags: tuple[FeedbackTag, ...] = ()
    customer_comment: str | None = Field(default=None, min_length=1)
    customer_certainty: FeedbackCertainty | None = None
    intended_action: str | None = Field(default=None, min_length=1)
    commitment_strength: FeedbackCommitmentStrength | None = None
    customer_owner: str | None = Field(default=None, min_length=1, max_length=200)
    internal_follow_up_owner: str | None = Field(default=None, min_length=1, max_length=200)
    follow_up_date: date | None = None

    @model_validator(mode="after")
    def wrong_requires_comment(self) -> FeedbackCreate:
        # §3 rule 1: a dispute with no explanation is unusable and must not be stored as a bare
        # flag.
        if FeedbackTag.WRONG in self.tags and not self.customer_comment:
            raise ValueError("customer_comment is required when the WRONG tag is set")
        return self
