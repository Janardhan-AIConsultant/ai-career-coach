"""Documents and career analyses. Every row is owned by exactly one user OR one guest session."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import DOCUMENT_KINDS, REPORT_FORMATS, REPORT_TYPES
from app.models.base import Base, IdMixin, JsonType, SoftDeleteMixin, TimestampMixin, fk, in_check


def _one_owner(table: str) -> CheckConstraint:
    return CheckConstraint(
        "(owner_user_id IS NULL) <> (guest_session_id IS NULL)", name=f"ck_{table}_one_owner"
    )


class OwnerMixin:
    owner_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    guest_session_id: Mapped[uuid.UUID | None] = fk("guest_sessions.id", nullable=True)


class Document(IdMixin, TimestampMixin, SoftDeleteMixin, OwnerMixin, Base):
    """Uploaded file metadata. Bytes live in object storage (``storage_key``), vectors in Chroma."""

    __tablename__ = "documents"
    __table_args__ = (_one_owner("documents"), in_check("kind", DOCUMENT_KINDS, "ck_documents_kind"))

    kind: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Report(IdMixin, TimestampMixin, SoftDeleteMixin, OwnerMixin, Base):
    """Generated downloadable report. Bytes live in object storage under ``storage_key``."""

    __tablename__ = "reports"
    __table_args__ = (
        _one_owner("reports"),
        in_check("report_type", REPORT_TYPES, "ck_reports_type"),
        in_check("file_format", REPORT_FORMATS, "ck_reports_format"),
    )

    report_type: Mapped[str] = mapped_column(String(40))
    file_format: Mapped[str] = mapped_column(String(10))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Resume(IdMixin, TimestampMixin, SoftDeleteMixin, OwnerMixin, Base):
    __tablename__ = "resumes"
    __table_args__ = (_one_owner("resumes"),)

    document_id: Mapped[uuid.UUID | None] = fk("documents.id", nullable=True, ondelete="SET NULL")
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class JobDescription(IdMixin, TimestampMixin, SoftDeleteMixin, OwnerMixin, Base):
    __tablename__ = "job_descriptions"
    __table_args__ = (_one_owner("job_descriptions"),)

    document_id: Mapped[uuid.UUID | None] = fk("documents.id", nullable=True, ondelete="SET NULL")
    title: Mapped[str | None] = mapped_column(String(200))
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class CareerAnalysis(IdMixin, TimestampMixin, SoftDeleteMixin, OwnerMixin, Base):
    __tablename__ = "career_analyses"
    __table_args__ = (_one_owner("career_analyses"),)

    resume_id: Mapped[uuid.UUID] = fk("resumes.id")
    job_description_id: Mapped[uuid.UUID] = fk("job_descriptions.id")
    overall_score: Mapped[float | None] = mapped_column(Float)  # computed in code, never by the LLM
    scoring_version: Mapped[str] = mapped_column(String(20), default="v1")
    category_scores: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class SkillGapAnalysis(IdMixin, TimestampMixin, SoftDeleteMixin, OwnerMixin, Base):
    __tablename__ = "skill_gap_analyses"
    __table_args__ = (_one_owner("skill_gap_analyses"),)

    career_analysis_id: Mapped[uuid.UUID | None] = fk("career_analyses.id", nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
