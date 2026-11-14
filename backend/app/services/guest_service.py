"""Guest session lifecycle: create, purge (explicit delete) and expiry cleanup.

Purging removes everything a guest owns: vectors, stored report files, and all database rows.
Expired sessions are already unusable (rejected at access time); ``cleanup_expired`` physically
removes their data and is meant for a scheduled job (``scripts/cleanup_guest_data.py``).
Failures to delete vectors/files abort the purge of that session (it is retried next run) rather
than leaving a half-deleted session with orphaned data.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import new_guest_token
from app.models import (
    CareerAnalysis,
    Document,
    GuestSession,
    JobDescription,
    Report,
    Resume,
    SkillGapAnalysis,
)
from app.rag.vector_store import Owner, VectorStore
from app.services.object_storage import ObjectStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreatedGuestSession:
    session: GuestSession
    token: str  # returned to the client once; only its hash is stored


def create_guest_session(db: Session, expire_minutes: int) -> CreatedGuestSession:
    raw, hashed = new_guest_token()
    session = GuestSession(
        token_hash=hashed, expires_at=datetime.now(UTC) + timedelta(minutes=expire_minutes)
    )
    db.add(session)
    db.commit()
    return CreatedGuestSession(session, raw)


def purge_guest_session(
    db: Session, store: VectorStore, storage: ObjectStorage, session_id: uuid.UUID
) -> None:
    owner = Owner("guest", str(session_id))
    keys = db.scalars(select(Report.storage_key).where(Report.guest_session_id == session_id)).all()
    store.delete_owner(owner)  # raises VectorStoreError -> nothing else is deleted
    for key in keys:
        storage.delete(key)
    # children first (explicit, so it does not depend on DB-level cascade support)
    for model in (SkillGapAnalysis, CareerAnalysis, Resume, JobDescription, Report, Document):
        db.execute(delete(model).where(model.guest_session_id == session_id))
    db.execute(delete(GuestSession).where(GuestSession.id == session_id))
    db.commit()


def cleanup_expired(
    db: Session,
    store: VectorStore,
    storage: ObjectStorage,
    *,
    now: datetime | None = None,
    batch_size: int = 100,
) -> int:
    """Purge expired or explicitly-deleted guest sessions. Returns the number purged."""
    now = now or datetime.now(UTC)
    ids = db.scalars(
        select(GuestSession.id)
        .where((GuestSession.expires_at <= now) | GuestSession.deleted_at.is_not(None))
        .limit(batch_size)
    ).all()
    purged = 0
    for session_id in ids:
        try:
            purge_guest_session(db, store, storage, session_id)
            purged += 1
        except Exception:
            db.rollback()
            logger.exception("guest purge failed", extra={"session_id": str(session_id)})
    logger.info("guest cleanup finished", extra={"purged": purged, "candidates": len(ids)})
    return purged
