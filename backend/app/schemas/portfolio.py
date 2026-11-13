"""Models for the Career Achievement Portfolio."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EvidenceLevel = Literal["learned", "assessed", "demonstrated"]
SECTIONS = ("summary", "timeline", "skills", "learning_paths", "assessments", "certificates", "projects", "scores")
DISCLAIMER = ("Learning achievements recorded on the AI Career Coach platform. This is NOT professional "
              "employment experience. Certificates are platform-issued, not externally accredited, and "
              "project reviews are automated static reviews of submitted evidence.")


def _utc(v: datetime | None) -> datetime | None:
    return v if v is None or v.tzinfo else v.replace(tzinfo=UTC)


class SettingsIn(BaseModel):
    visibility: Literal["private", "public"] | None = None
    display_name: str | None = Field(default=None, max_length=80)
    headline: str | None = Field(default=None, max_length=160)
    summary: str | None = Field(default=None, max_length=1000)
    section_visibility: dict[str, bool] | None = None
    consent_public: bool = False  # must be true to publish

    @field_validator("section_visibility")
    @classmethod
    def _known_sections(cls, v: dict[str, bool] | None) -> dict[str, bool] | None:
        if v and not set(v) <= set(SECTIONS):
            raise ValueError("Unknown section: " + ", ".join(sorted(set(v) - set(SECTIONS))))
        return v


class SettingsOut(BaseModel):
    visibility: Literal["private", "public"]
    public_slug: str | None
    public_url: str | None  # only while public
    display_name: str | None
    headline: str | None
    summary: str | None
    section_visibility: dict[str, bool]
    resume_integration_approved: bool
    consent_at: datetime | None

    _tz = field_validator("consent_at")(_utc)


class ItemOut(BaseModel):
    id: uuid.UUID
    kind: Literal["learning_path", "assessment", "certificate", "project"]
    title: str
    evidence_level: EvidenceLevel
    skills: list[str]
    achieved_at: datetime
    is_visible: bool
    details: dict[str, Any]

    _tz = field_validator("achieved_at")(_utc)


class SkillEvidenceOut(BaseModel):
    skill: str
    levels: list[EvidenceLevel]
    highest: EvidenceLevel
    evidence: list[dict[str, Any]]


class StatsOut(BaseModel):
    learning_paths_completed: int
    activities_completed: int
    estimated_learning_hours: float
    assessments_passed: int
    certificates: int
    projects_passed: int


class PortfolioOut(BaseModel):
    settings: SettingsOut
    timeline: list[ItemOut]
    skills: list[SkillEvidenceOut]
    stats: StatsOut
    disclaimer: str = DISCLAIMER


class ItemPatch(BaseModel):
    is_visible: bool


class PublicItem(BaseModel):
    kind: str
    title: str
    evidence_level: EvidenceLevel
    skills: list[str]
    achieved_at: datetime
    details: dict[str, Any]

    _tz = field_validator("achieved_at")(_utc)


class PublicPortfolio(BaseModel):
    display_name: str
    headline: str | None
    summary: str | None
    timeline: list[PublicItem]
    skills: list[SkillEvidenceOut]
    disclaimer: str = DISCLAIMER


class ApprovalIn(BaseModel):
    approve: bool


class TextOut(BaseModel):
    text: str


class LinkedInCertification(BaseModel):
    name: str
    issuing_organization: str
    issue_date: str
    credential_id: str
    credential_url: str


class LinkedInOut(BaseModel):
    about: str
    certifications: list[LinkedInCertification]
    notes: list[str]
