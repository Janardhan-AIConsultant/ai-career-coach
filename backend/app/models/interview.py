"""Mock interview persistence (registered users only)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, JsonType, TimestampMixin, fk


class InterviewSession(IdMixin, TimestampMixin, Base):
    __tablename__ = "interview_sessions"

    user_id: Mapped[uuid.UUID] = fk("users.id")
    kinds: Mapped[list[Any]] = mapped_column(JsonType)
    question_ids: Mapped[list[Any]] = mapped_column(JsonType)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    overall_score: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InterviewAnswer(IdMixin, TimestampMixin, Base):
    __tablename__ = "interview_answers"
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_interview_answer"),)

    session_id: Mapped[uuid.UUID] = fk("interview_sessions.id")
    question_id: Mapped[str] = mapped_column(String(40))
    answer_text: Mapped[str] = mapped_column(Text)
    feedback: Mapped[dict[str, Any]] = mapped_column(JsonType)
    overall_score: Mapped[float] = mapped_column(Float)
