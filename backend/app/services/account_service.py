"""Account operations: profile, password change, account deletion, guest-data import.

Guest import (consent + ownership): the caller must hold a valid, unexpired, unclaimed guest
token (proof of ownership) AND be an authenticated user who explicitly consents. Rows are
re-owned in one database transaction; vectors are re-tagged before commit and restored if the
commit fails. Imported items lose their guest expiry so they are not cleaned up.

Account deletion: deletes the user's documents, resumes/JDs, analyses, reports (files), vectors,
conversations, feedback, testimonials, profile and sessions; anonymises the user row (kept only
so platform-issued certificates stay verifiable) and frees the email for re-registration.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, DatabaseError, InputValidationError
from app.core.security import hash_password, verify_password
from app.models import (
    AssessmentAttempt,
    AuditLog,
    CareerAnalysis,
    Certificate,
    Conversation,
    Document,
    Feedback,
    GuestSession,
    InterviewAnswer,
    InterviewSession,
    JobDescription,
    LearningActivity,
    LearningModule,
    LearningRoadmap,
    Message,
    Portfolio,
    PortfolioAchievement,
    ProjectEvaluation,
    ProjectSubmission,
    Report,
    Resume,
    SkillGapAnalysis,
    Testimonial,
    User,
    UserProfile,
    UserSession,
)
from app.rag.vector_store import Owner, VectorStore
from app.services.auth_service import revoke_all_sessions
from app.services.object_storage import ObjectStorage
from app.services.principal import Principal

logger = logging.getLogger(__name__)


def get_profile(db: Session, user: User) -> UserProfile | None:
    return db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))


def upsert_profile(db: Session, user: User, data: dict[str, object]) -> UserProfile:
    profile = get_profile(db, user)
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    for key, value in data.items():
        setattr(profile, key, value)
    db.commit()
    return profile


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthenticationError("Current password is incorrect")
    user.password_hash = hash_password(new)
    revoke_all_sessions(db, user)  # other devices must log in again
    db.add(AuditLog(actor_user_id=user.id, action="auth.password_changed", entity_type="user",
                    entity_id=str(user.id)))
    db.commit()


def delete_account(
    db: Session, store: VectorStore, storage: ObjectStorage, user: User, password: str
) -> None:
    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Password is incorrect")
    owner = Owner("user", str(user.id))
    keys = db.scalars(select(Report.storage_key).where(Report.owner_user_id == user.id)).all()
    store.delete_owner(owner)
    for key in keys:
        storage.delete(key)
    sess_ids = select(InterviewSession.id).where(InterviewSession.user_id == user.id)
    db.execute(delete(InterviewAnswer).where(InterviewAnswer.session_id.in_(sess_ids)))
    db.execute(delete(InterviewSession).where(InterviewSession.user_id == user.id))
    pf_ids = select(Portfolio.id).where(Portfolio.user_id == user.id)
    db.execute(delete(PortfolioAchievement).where(PortfolioAchievement.portfolio_id.in_(pf_ids)))
    db.execute(delete(Portfolio).where(Portfolio.user_id == user.id))
    # certificates reference their evidence, so they go first (right to erasure: the ID then verifies as invalid)
    db.execute(delete(Certificate).where(Certificate.user_id == user.id))
    sub_ids = select(ProjectSubmission.id).where(ProjectSubmission.user_id == user.id)
    db.execute(delete(ProjectEvaluation).where(ProjectEvaluation.submission_id.in_(sub_ids)))
    db.execute(delete(ProjectSubmission).where(ProjectSubmission.user_id == user.id))
    db.execute(delete(AssessmentAttempt).where(AssessmentAttempt.user_id == user.id))
    road_ids = select(LearningRoadmap.id).where(LearningRoadmap.user_id == user.id)
    mod_ids = select(LearningModule.id).where(LearningModule.roadmap_id.in_(road_ids))
    db.execute(delete(LearningActivity).where(LearningActivity.module_id.in_(mod_ids)))
    db.execute(delete(LearningModule).where(LearningModule.roadmap_id.in_(road_ids)))
    db.execute(delete(LearningRoadmap).where(LearningRoadmap.user_id == user.id))
    conv_ids = select(Conversation.id).where(Conversation.user_id == user.id)
    db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
    db.execute(delete(Conversation).where(Conversation.user_id == user.id))
    for owned in (SkillGapAnalysis, CareerAnalysis, Resume, JobDescription, Report, Document):
        db.execute(delete(owned).where(owned.owner_user_id == user.id))
    for by_user in (Feedback, Testimonial, UserProfile, UserSession):
        db.execute(delete(by_user).where(by_user.user_id == user.id))
    now = datetime.now(UTC)
    user.email = f"deleted-{user.id.hex}@deleted.invalid"
    user.display_name = "Deleted user"
    user.password_hash = hash_password(uuid.uuid4().hex + "Aa1")  # unusable
    user.is_active = False
    user.deleted_at = now
    user.tokens_valid_after = now
    db.add(AuditLog(actor_user_id=None, action="account.deleted", entity_type="user",
                    entity_id=str(user.id)))
    db.commit()


def import_guest_session(
    db: Session, store: VectorStore, user: User, guest: GuestSession, consent: bool
) -> tuple[int, int]:
    """Move everything the guest session owns into ``user``. Returns (documents, reports)."""
    if not consent:
        raise InputValidationError("Explicit consent is required to import guest data")
    if guest.claimed_by_user_id is not None:
        raise InputValidationError("This guest session has already been imported")
    gid, source, target = guest.id, Owner("guest", str(guest.id)), Owner("user", str(user.id))
    try:
        counts: dict[str, int] = {}
        for label, model in (("documents", Document), ("reports", Report)):
            result = cast(CursorResult[Any], db.execute(
                update(model).where(model.guest_session_id == gid)
                .values(owner_user_id=user.id, guest_session_id=None, expires_at=None)
            ))
            counts[label] = result.rowcount
        for child in (Resume, JobDescription, CareerAnalysis, SkillGapAnalysis):
            db.execute(
                update(child).where(child.guest_session_id == gid)
                .values(owner_user_id=user.id, guest_session_id=None)
            )
        guest.claimed_by_user_id = user.id
        guest.deleted_at = datetime.now(UTC)  # unusable from now on; cleanup removes the row
        db.add(AuditLog(actor_user_id=user.id, action="guest.imported", entity_type="guest_session",
                        entity_id=str(gid)))
        db.flush()
        store.reassign_owner(source, target)
    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseError() from exc
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        store.reassign_owner(target, source)  # restore vector ownership
        logger.exception("guest import commit failed; vectors restored")
        raise DatabaseError() from exc
    return counts["documents"], counts["reports"]


def principal_for(user: User) -> Principal:
    return Principal("user", user.id)
