"""Registration, login, refresh-token rotation and logout.

* Passwords: Argon2id. Login for an unknown email still performs a hash verification so response
  time does not reveal which emails exist; all login failures share one generic message.
* Access token: short-lived JWT returned in the response body (kept in memory by the SPA).
* Refresh token: 256-bit random value delivered as an HttpOnly cookie; only its SHA-256 is
  stored (``user_sessions``). Each use rotates it. Presenting an already-revoked refresh token
  signals theft: every session of that user is revoked and ``tokens_valid_after`` is advanced.
Audit entries record the action and ids only - never emails, passwords or tokens.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError, AuthenticationError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AuditLog, User, UserSession

logger = logging.getLogger(__name__)

# Verified against when the email is unknown, to equalise timing.
_DUMMY_HASH = hash_password("dummy-password-for-timing-1")


class EmailAlreadyRegisteredError(AppError):
    code, status_code = "registration_failed", 409
    default_message = "An account with these details could not be created"


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    user: User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _audit(db: Session, action: str, user_id: uuid.UUID | None) -> None:
    db.add(AuditLog(actor_user_id=user_id, action=action, entity_type="user",
                    entity_id=str(user_id) if user_id else None))


def _issue(db: Session, settings: Settings, user: User) -> IssuedTokens:
    raw = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(raw),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    access = create_access_token(
        user.id, settings.jwt_secret_key.get_secret_value(), settings.access_token_expire_minutes
    )
    return IssuedTokens(access, settings.access_token_expire_minutes * 60, raw, user)


def register(
    db: Session, settings: Settings, *, email: str, password: str, display_name: str
) -> IssuedTokens:
    email = normalize_email(email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise EmailAlreadyRegisteredError()
    user = User(email=email, password_hash=hash_password(password), display_name=display_name,
                role="user")
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent registration of the same email
        db.rollback()
        raise EmailAlreadyRegisteredError() from exc
    _audit(db, "auth.register", user.id)
    tokens = _issue(db, settings, user)
    db.commit()
    return tokens


def login(db: Session, settings: Settings, *, email: str, password: str) -> IssuedTokens:
    user = db.scalar(
        select(User).where(User.email == normalize_email(email), User.deleted_at.is_(None))
    )
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok or not user.is_active:
        logger.info("login failed")
        raise AuthenticationError("Invalid email or password")
    _audit(db, "auth.login", user.id)
    tokens = _issue(db, settings, user)
    db.commit()
    return tokens


def revoke_all_sessions(db: Session, user: User) -> None:
    now = datetime.now(UTC)
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    user.tokens_valid_after = now


def refresh(db: Session, settings: Settings, raw_refresh: str | None) -> IssuedTokens:
    if not raw_refresh:
        raise AuthenticationError()
    session = db.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == hash_refresh_token(raw_refresh))
    )
    if session is None:
        raise AuthenticationError()
    user = db.get(User, session.user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise AuthenticationError()
    if session.revoked_at is not None:
        # Reuse of a rotated/revoked token: assume theft, kill everything for this user.
        revoke_all_sessions(db, user)
        _audit(db, "auth.refresh_reuse_detected", user.id)
        db.commit()
        logger.warning("refresh token reuse detected", extra={"user_id": str(user.id)})
        raise AuthenticationError()
    if _aware(session.expires_at) <= datetime.now(UTC):
        raise AuthenticationError("Session expired")
    session.revoked_at = datetime.now(UTC)
    tokens = _issue(db, settings, user)
    db.commit()
    return tokens


def logout(db: Session, raw_refresh: str | None) -> None:
    if not raw_refresh:
        return
    session = db.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == hash_refresh_token(raw_refresh))
    )
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        _audit(db, "auth.logout", session.user_id)
        db.commit()
