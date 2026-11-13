"""Models for learning roadmaps (7/15/60 days only) and assessments."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.schemas.career_api import ReportFormat

SkillKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


def _utc(v: datetime | None) -> datetime | None:
    """Naive datetimes (e.g. SQLite) are UTC; make every timestamp explicit."""
    return v if v is None or v.tzinfo else v.replace(tzinfo=UTC)



class RoadmapCreateIn(BaseModel):
    duration_days: Literal[7, 15, 60]
    goal: str = Field(min_length=3, max_length=500)
    resume_document_id: uuid.UUID | None = None
    job_description_document_id: uuid.UUID | None = None
    focus_skills: list[SkillKey] = Field(default_factory=list, max_length=10)


class ActivityOut(BaseModel):
    id: uuid.UUID
    day_number: int
    title: str
    kind: str
    description: str | None
    resources: list[str]
    estimated_minutes: int | None
    is_required: bool
    ref: str | None
    completed_at: datetime | None

    _tz = field_validator("completed_at")(_utc)


class ModuleOut(BaseModel):
    id: uuid.UUID
    position: int
    title: str
    objectives: list[str]
    topics: list[str]
    activities: list[ActivityOut]
    completed: int
    total: int


class Requirement(BaseModel):
    name: str
    met: bool


class ProgressOut(BaseModel):
    percent_required_complete: float
    completed_required: int
    total_required: int
    requirements: list[Requirement]
    criteria_met: bool
    next_activities: list[ActivityOut]


class RoadmapOut(BaseModel):
    id: uuid.UUID
    title: str
    duration_days: Literal[7, 15, 60]
    goal: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    estimated_hours: float | None
    focus_skills: list[str]
    completion_criteria: dict[str, Any]
    modules: list[ModuleOut]
    progress: ProgressOut

    _tz = field_validator("started_at", "completed_at")(_utc)


class RoadmapSummary(BaseModel):
    id: uuid.UUID
    title: str
    duration_days: Literal[7, 15, 60]
    status: str
    percent_required_complete: float
    started_at: datetime | None

    _tz = field_validator("started_at")(_utc)


class ReportRequest(BaseModel):
    report_format: ReportFormat


class ReportCreated(BaseModel):
    report_id: uuid.UUID


# ------------------------------------------------------------------ assessments
class AssessmentSummary(BaseModel):
    slug: str
    title: str
    topic: str
    difficulty: str
    description: str | None
    pass_score: float
    question_count: int
    attempts: int
    best_score: float | None


class QuestionPublic(BaseModel):
    id: uuid.UUID
    type: str
    prompt: str
    options: list[str] | None
    points: int


class AssessmentDetail(AssessmentSummary):
    questions: list[QuestionPublic]


class SubmitIn(BaseModel):
    # question id -> int (mcq/scenario), list[int] (multi_select) or str (technical/practical)
    answers: dict[uuid.UUID, Any] = Field(max_length=50)


class QuestionFeedback(BaseModel):
    question_id: uuid.UUID
    type: str
    points_earned: float
    points_possible: int
    status: str
    feedback: str
    explanation: str | None
    correct_answer: Any


class SubmitOut(BaseModel):
    attempt_id: uuid.UUID
    slug: str
    score: float
    passed: bool
    pass_score: float
    results: list[QuestionFeedback]
    roadmap_activities_completed: int


class AttemptSummary(BaseModel):
    attempt_id: uuid.UUID
    slug: str | None
    title: str
    score: float
    passed: bool
    submitted_at: datetime


class DashboardOut(BaseModel):
    roadmaps: list[RoadmapSummary]
    next_activities: list[ActivityOut]
    recent_attempts: list[AttemptSummary]
