"""Request/response models for the career-intelligence endpoints (guest and registered)."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.career import (
    JobDescriptionAnalysis,
    MatchResult,
    OptimizationResult,
    ResumeAnalysis,
    SkillGapAnalysis,
)

ReportFormat = Literal["pdf", "docx"]
SkillName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class ResumeAnalyzeIn(BaseModel):
    document_id: uuid.UUID
    report_format: ReportFormat | None = None


class JobDescriptionAnalyzeIn(BaseModel):
    document_id: uuid.UUID
    report_format: ReportFormat | None = None


class PairIn(BaseModel):
    resume_document_id: uuid.UUID
    job_description_document_id: uuid.UUID
    report_format: ReportFormat | None = None


class MatchIn(PairIn):
    include_narrative: bool = False  # off by default: uses an LLM call


class SkillGapIn(PairIn):
    declared_absent_skills: list[SkillName] = Field(default_factory=list, max_length=50)


class OptimizeIn(PairIn):
    confirmed_skills: list[SkillName] = Field(default_factory=list, max_length=30)
    approved_change_ids: list[str] = Field(default_factory=list, max_length=50)
    declined_change_ids: list[str] = Field(default_factory=list, max_length=50)


class ResumeAnalyzeOut(BaseModel):
    analysis: ResumeAnalysis
    report_id: uuid.UUID | None = None


class JobDescriptionAnalyzeOut(BaseModel):
    analysis: JobDescriptionAnalysis
    report_id: uuid.UUID | None = None


class MatchOut(BaseModel):
    match: MatchResult
    narrative: str | None = None
    report_id: uuid.UUID | None = None


class SkillGapOut(BaseModel):
    analysis: SkillGapAnalysis
    report_id: uuid.UUID | None = None


class OptimizeOut(BaseModel):
    result: OptimizationResult
    report_id: uuid.UUID | None = None  # change report (before/after)
    optimized_resume_report_id: uuid.UUID | None = None  # the optimised resume file


class ReportOut(BaseModel):
    report_id: uuid.UUID
    report_type: str
    file_format: str
    filename: str
    created_at: str
