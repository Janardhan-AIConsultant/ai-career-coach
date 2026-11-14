"""Accounts and sessions: User, UserProfile, UserSession, GuestSession."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import USER_ROLES
from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin, fk, in_check


class User(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (in_check("role", USER_ROLES, "ck_users_role"),)

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Access tokens issued before this instant are rejected (password change / logout-all).
    tokens_valid_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped[UserProfile | None] = relationship(back_populates="user", uselist=False)


class UserProfile(IdMixin, TimestampMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = fk("users.id")
    headline: Mapped[str | None] = mapped_column(String(200))
    career_goal: Mapped[str | None] = mapped_column(Text)
    target_role: Mapped[str | None] = mapped_column(String(200))
    years_experience: Mapped[int | None] = mapped_column(Integer)

    user: Mapped[User] = relationship(back_populates="profile")


class UserSession(IdMixin, TimestampMixin, Base):
    """Refresh-token session; only the token hash is stored."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = fk("users.id")
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuestSession(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Guest capability session. Authentication is the secret token, whose hash is stored here."""

    __tablename__ = "guest_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    claimed_by_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
