"""Models for practical projects."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, field_validator

Skill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


def _utc(v: datetime | None) -> datetime | None:
    from datetime import UTC

    return v if v is None or v.tzinfo else v.replace(tzinfo=UTC)


class ItemOut(BaseModel):
    text: str


class TemplateOut(BaseModel):
    id: str
    title: str
    kind: str
    difficulty: str
    description: str
    skills: list[str]
    requirements: list[str]
    expected_outcomes: list[str]
    technologies: list[str]
    milestones: list[str]


class RecommendationOut(BaseModel):
    template: TemplateOut
    matched_skills: list[str]
    reason: str


class SubmissionIn(BaseModel):
    template_id: str = Field(min_length=1, max_length=60)
    repo_url: str | None = Field(default=None, max_length=300)
    documentation_url: str | None = Field(default=None, max_length=300)  # stored as a link only; never fetched
    documentation_text: str | None = Field(default=None, max_length=20_000)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("documentation_url")
    @classmethod
    def _https(cls, v: str | None) -> str | None:
        if v and not v.startswith("https://"):
            raise ValueError("documentation_url must start with https://")
        return v


class EvaluationOut(BaseModel):
    id: uuid.UUID
    overall_score: float
    passed: bool
    code_executed: bool
    details: dict[str, Any]
    created_at: datetime

    _tz = field_validator("created_at")(_utc)


class SubmissionOut(BaseModel):
    id: uuid.UUID
    template_id: str | None
    title: str
    repo_url: str | None
    documentation_url: str | None
    status: str
    created_at: datetime
    latest_evaluation: EvaluationOut | None = None

    _tz = field_validator("created_at")(_utc)
