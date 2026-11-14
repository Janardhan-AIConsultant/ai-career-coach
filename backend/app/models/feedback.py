"""Feedback, testimonials, aggregate share events, moderation history and audit log."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import (
    FEEDBACK_FEATURES,
    MODERATION_ACTIONS,
    SHARE_EVENT_TYPES,
    SHARE_PLATFORMS,
    TESTIMONIAL_STATUSES,
)
from app.models.base import (
    Base,
    IdMixin,
    JsonType,
    SoftDeleteMixin,
    TimestampMixin,
    fk,
    in_check,
    utcnow,
)


class Feedback(IdMixin, TimestampMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        in_check("feature", FEEDBACK_FEATURES, "ck_feedback_feature"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating"),
    )

    user_id: Mapped[uuid.UUID] = fk("users.id")
    feature: Mapped[str] = mapped_column(String(40))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)


class Testimonial(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Public only when status == 'approved', consent given and not withdrawn."""

    __test__ = False  # not a pytest class
    __tablename__ = "testimonials"
    __table_args__ = (
        in_check("status", TESTIMONIAL_STATUSES, "ck_testimonials_status"),
        in_check("feature", FEEDBACK_FEATURES, "ck_testimonials_feature"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="ck_testimonials_rating"),
    )

    user_id: Mapped[uuid.UUID] = fk("users.id")
    text: Mapped[str] = mapped_column(Text)
    feature: Mapped[str] = mapped_column(String(40))
    would_recommend: Mapped[bool | None] = mapped_column(Boolean)
    success_story: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(120))
    rating: Mapped[int | None] = mapped_column(Integer)
    public_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    @property
    def is_publicly_visible(self) -> bool:
        return (
            self.status == "approved"
            and self.public_consent
            and self.consent_withdrawn_at is None
            and self.deleted_at is None
        )


class TestimonialShareEvent(IdMixin, Base):
    """Aggregate-only analytics: no user, IP or device identifiers are stored."""

    __test__ = False  # not a pytest class
    __tablename__ = "testimonial_share_events"
    __table_args__ = (
        in_check("platform", SHARE_PLATFORMS, "ck_share_events_platform", nullable=True),
        in_check("event_type", SHARE_EVENT_TYPES, "ck_share_events_type"),
    )

    testimonial_id: Mapped[uuid.UUID] = fk("testimonials.id")
    platform: Mapped[str | None] = mapped_column(String(20))
    event_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ModerationLog(IdMixin, Base):
    __tablename__ = "moderation_logs"
    __table_args__ = (in_check("action", MODERATION_ACTIONS, "ck_moderation_logs_action"),)

    testimonial_id: Mapped[uuid.UUID] = fk("testimonials.id")
    admin_user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="RESTRICT")
    action: Mapped[str] = mapped_column(String(20))
    previous_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any] | None] = mapped_column(JsonType)  # never PII / document text
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
