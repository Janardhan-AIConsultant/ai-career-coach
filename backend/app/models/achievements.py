"""Certificates, practical projects and the career achievement portfolio."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import (
    CERTIFICATE_STATUSES,
    CERTIFICATE_TYPES,
    EVIDENCE_LEVELS,
    PORTFOLIO_VISIBILITY,
)
from app.models.base import Base, IdMixin, JsonType, SoftDeleteMixin, TimestampMixin, fk, in_check


class ProjectSubmission(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "project_submissions"

    user_id: Mapped[uuid.UUID] = fk("users.id")
    title: Mapped[str] = mapped_column(String(200))
    template_id: Mapped[str | None] = mapped_column(String(60))
    repo_key: Mapped[str | None] = mapped_column(String(300), index=True)  # normalised github.com/owner/repo
    documentation_text: Mapped[str | None] = mapped_column(Text)
    repo_url: Mapped[str | None] = mapped_column(String(500))
    documentation_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="submitted")


class ProjectEvaluation(IdMixin, TimestampMixin, Base):
    __tablename__ = "project_evaluations"

    submission_id: Mapped[uuid.UUID] = fk("project_submissions.id")
    criteria_scores: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    overall_score: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    feedback: Mapped[str | None] = mapped_column(Text)
    # Code is only ever marked executed when it really was; default is "static review only".
    code_executed: Mapped[bool] = mapped_column(Boolean, default=False)


class Certificate(IdMixin, TimestampMixin, Base):
    """Platform-issued certificate (not an externally accredited qualification)."""

    __tablename__ = "certificates"
    __table_args__ = (
        in_check("certificate_type", CERTIFICATE_TYPES, "ck_certificates_type"),
        in_check("status", CERTIFICATE_STATUSES, "ck_certificates_status"),
        UniqueConstraint("user_id", "source_key", name="uq_certificates_source"),
        # A certificate must be backed by real evidence, never by a button click.
        CheckConstraint(
            "roadmap_id IS NOT NULL OR attempt_id IS NOT NULL OR evaluation_id IS NOT NULL",
            name="ck_certificates_has_evidence",
        ),
    )

    certificate_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    learner_name: Mapped[str] = mapped_column(String(120), default="")
    source_key: Mapped[str] = mapped_column(String(120), default="")  # one certificate per evidence source
    user_id: Mapped[uuid.UUID] = fk("users.id")
    certificate_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(200))
    score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="valid")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    roadmap_id: Mapped[uuid.UUID | None] = fk("learning_roadmaps.id", nullable=True, ondelete="RESTRICT")
    attempt_id: Mapped[uuid.UUID | None] = fk("assessment_attempts.id", nullable=True, ondelete="RESTRICT")
    evaluation_id: Mapped[uuid.UUID | None] = fk("project_evaluations.id", nullable=True, ondelete="RESTRICT")


class Portfolio(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        in_check("visibility", PORTFOLIO_VISIBILITY, "ck_portfolios_visibility"),
    )

    user_id: Mapped[uuid.UUID] = fk("users.id", unique=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    public_slug: Mapped[str | None] = mapped_column(String(80), unique=True)
    summary: Mapped[str | None] = mapped_column(Text)
    section_visibility: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    resume_integration_approved: Mapped[bool] = mapped_column(Boolean, default=False)


class PortfolioAchievement(IdMixin, TimestampMixin, Base):
    """Learning evidence only; never represents professional employment."""

    __tablename__ = "portfolio_achievements"
    __table_args__ = (
        in_check("evidence_level", EVIDENCE_LEVELS, "ck_portfolio_achievements_evidence"),
    )

    portfolio_id: Mapped[uuid.UUID] = fk("portfolios.id")
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    skill: Mapped[str | None] = mapped_column(String(100), index=True)
    evidence_level: Mapped[str] = mapped_column(String(20))
    source_type: Mapped[str | None] = mapped_column(String(30))
    source_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    achieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
