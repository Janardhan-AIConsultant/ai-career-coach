"""Coaching conversations, learning roadmaps (7/15/60 days only) and assessments."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import (
    DIFFICULTIES,
    MESSAGE_ROLES,
    QUESTION_TYPES,
    ROADMAP_DURATIONS,
)
from app.models.base import Base, IdMixin, JsonType, SoftDeleteMixin, TimestampMixin, fk, in_check


class Conversation(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = fk("users.id")
    title: Mapped[str] = mapped_column(String(200), default="New conversation")


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (in_check("role", MESSAGE_ROLES, "ck_messages_role"),)

    conversation_id: Mapped[uuid.UUID] = fk("conversations.id")
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[Any] | None] = mapped_column(JsonType)


class LearningRoadmap(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "learning_roadmaps"
    __table_args__ = (
        in_check("duration_days", ROADMAP_DURATIONS, "ck_learning_roadmaps_duration"),
    )

    user_id: Mapped[uuid.UUID] = fk("users.id")
    duration_days: Mapped[int] = mapped_column(Integer)
    goal: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(200), default="Learning roadmap")
    focus_skills: Mapped[list[Any] | None] = mapped_column(JsonType)
    completion_criteria: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    estimated_hours: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningModule(IdMixin, TimestampMixin, Base):
    __tablename__ = "learning_modules"

    roadmap_id: Mapped[uuid.UUID] = fk("learning_roadmaps.id")
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    objectives: Mapped[list[Any] | None] = mapped_column(JsonType)
    topics: Mapped[list[Any] | None] = mapped_column(JsonType)


class LearningActivity(IdMixin, TimestampMixin, Base):
    __tablename__ = "learning_activities"

    module_id: Mapped[uuid.UUID] = fk("learning_modules.id")
    day_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default="task")
    description: Mapped[str | None] = mapped_column(Text)
    resources: Mapped[list[Any] | None] = mapped_column(JsonType)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    ref: Mapped[str | None] = mapped_column(String(80))  # e.g. "assessment:kafka"
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Assessment(IdMixin, TimestampMixin, Base):
    __tablename__ = "assessments"
    __table_args__ = (
        in_check("difficulty", DIFFICULTIES, "ck_assessments_difficulty"),
        UniqueConstraint("slug", name="uq_assessments_slug"),
    )

    slug: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(100), index=True)
    difficulty: Mapped[str] = mapped_column(String(20))
    pass_score: Mapped[float] = mapped_column(Float, default=70.0)


class AssessmentQuestion(IdMixin, TimestampMixin, Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (in_check("question_type", QUESTION_TYPES, "ck_assessment_questions_type"),)

    assessment_id: Mapped[uuid.UUID] = fk("assessments.id")
    key: Mapped[str | None] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=1)
    question_type: Mapped[str] = mapped_column(String(20))
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[Any] | None] = mapped_column(JsonType)
    correct_answer: Mapped[Any | None] = mapped_column(JsonType)  # server-side only, never sent early
    explanation: Mapped[str | None] = mapped_column(Text)


class AssessmentAttempt(IdMixin, TimestampMixin, Base):
    __tablename__ = "assessment_attempts"

    user_id: Mapped[uuid.UUID] = fk("users.id")
    assessment_id: Mapped[uuid.UUID] = fk("assessments.id")
    answers: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    score: Mapped[float] = mapped_column(Float)  # computed server-side
    passed: Mapped[bool] = mapped_column(Boolean)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
