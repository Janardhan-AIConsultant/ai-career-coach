"""Models for interview preparation and mock interviews."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.interview.evaluation import AnswerFeedback
from app.schemas.career_api import ReportFormat

Kind = Literal["technical", "engineering_leadership", "engineering_management", "architecture",
               "system_design", "behavioural", "scenario", "hr"]
TopicName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class PrepareIn(BaseModel):
    kinds: list[Kind] = Field(min_length=1, max_length=8)
    resume_document_id: uuid.UUID | None = None
    job_description_document_id: uuid.UUID | None = None
    topics: list[TopicName] = Field(default_factory=list, max_length=20)
    count: int = Field(default=15, ge=1, le=40)
    report_format: ReportFormat | None = None


class MockStartIn(BaseModel):
    kinds: list[Kind] = Field(min_length=1, max_length=8)
    resume_document_id: uuid.UUID | None = None
    job_description_document_id: uuid.UUID | None = None
    topics: list[TopicName] = Field(default_factory=list, max_length=20)
    count: int = Field(default=8, ge=1, le=20)


class AnswerIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=40)
    answer: str = Field(min_length=1, max_length=5000)


class PreparedQuestion(BaseModel):
    id: str
    kind: str
    topic: str
    difficulty: str
    question: str
    reason: str
    model_answer: str
    key_points: list[str]
    practical_example: str
    follow_ups: list[str]
    evaluation_criteria: list[str]


class PrepareOut(BaseModel):
    questions: list[PreparedQuestion]
    focus_areas: list[str]
    report_id: uuid.UUID | None = None


class MockQuestion(BaseModel):
    id: str
    kind: str
    topic: str
    difficulty: str
    question: str
    reason: str


class MockSessionOut(BaseModel):
    session_id: uuid.UUID
    status: str
    questions: list[MockQuestion]
    answered_question_ids: list[str]
    overall_score: float | None = None
    created_at: datetime | None = None


class MockSummary(BaseModel):
    session_id: uuid.UUID
    overall_score: float
    answered: int
    unanswered: int
    dimension_averages: dict[str, float]
    by_kind: dict[str, float]
    weakest_dimensions: list[str]
    recommendations: list[str]
    disclaimer: str


class AnswerOut(BaseModel):
    question_id: str
    feedback: AnswerFeedback


class TopicsOut(BaseModel):
    kinds: list[str]
    topics: list[str]
