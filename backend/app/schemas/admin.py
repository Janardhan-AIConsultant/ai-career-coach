"""Models for the admin dashboard. Everything here is aggregate or account-administration data;
none of it contains document text, resume content, passwords, tokens or API keys."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def _utc(v: datetime | None) -> datetime | None:
    return v if v is None or v.tzinfo else v.replace(tzinfo=UTC)


class UserCounts(BaseModel):
    total: int
    active: int
    admins: int
    new_7d: int
    new_30d: int


class GuestCounts(BaseModel):
    active_sessions: int
    expired_pending_cleanup: int
    claimed: int


class ContentCounts(BaseModel):
    documents_by_kind: dict[str, int]
    reports: int
    career_analyses: int
    skill_gap_analyses: int
    interview_sessions: int
    conversations: int


class LearningCounts(BaseModel):
    roadmaps_by_status: dict[str, int]
    roadmaps_by_duration: dict[str, int]  # keys are only "7", "15", "60"
    assessment_attempts: int
    assessment_pass_rate: float | None


class AchievementCounts(BaseModel):
    certificates_by_status: dict[str, int]
    certificates_by_type: dict[str, int]
    projects_by_status: dict[str, int]
    public_portfolios: int


class CommunityCounts(BaseModel):
    ratings: int
    average_rating: float | None
    testimonials_by_status: dict[str, int]


class Overview(BaseModel):
    generated_at: datetime
    users: UserCounts
    guests: GuestCounts
    content: ContentCounts
    learning: LearningCounts
    achievements: AchievementCounts
    community: CommunityCounts


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    roadmaps: int
    certificates: int
    assessment_attempts: int

    _tz = field_validator("created_at")(_utc)


class UserPatch(BaseModel):
    is_active: bool | None = None
    role: Literal["user", "admin"] | None = None
    reason: str | None = Field(default=None, max_length=300)


class AuditEntry(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any] | None
    created_at: datetime

    _tz = field_validator("created_at")(_utc)


class AssessmentStat(BaseModel):
    slug: str
    title: str
    questions: int
    attempts: int
    pass_rate: float | None
    average_score: float | None


class ComponentStatus(BaseModel):
    name: str
    status: Literal["ok", "configured", "not_configured", "error"]
    detail: str


class SystemStatus(BaseModel):
    """Booleans and names only: no keys, URLs with credentials or connection strings."""

    environment: str
    roadmap_durations: list[int]
    share_platforms: list[str]
    components: list[ComponentStatus]
    warnings: list[str]


class CleanupResult(BaseModel):
    guest_sessions_purged: int
