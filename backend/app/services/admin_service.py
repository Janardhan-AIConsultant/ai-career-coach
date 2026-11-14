"""Admin dashboard: aggregate metrics, user administration, audit log, system status, maintenance.

Principles: aggregates only (never document or resume text), every state change is audit-logged,
an admin cannot lock the platform out of administration, and system status reports booleans and
names, never secrets.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, case, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import ROADMAP_DURATIONS, SHARE_PLATFORMS
from app.core.exceptions import ConflictError, InputValidationError, NotFoundError
from app.models import (
    Assessment,
    AssessmentAttempt,
    AssessmentQuestion,
    AuditLog,
    CareerAnalysis,
    Certificate,
    Conversation,
    Document,
    Feedback,
    GuestSession,
    InterviewSession,
    LearningRoadmap,
    Portfolio,
    ProjectSubmission,
    Report,
    SkillGapAnalysis,
    Testimonial,
    User,
    UserSession,
)
from app.schemas.admin import (
    AchievementCounts,
    AdminUserOut,
    AssessmentStat,
    AuditEntry,
    CommunityCounts,
    ComponentStatus,
    ContentCounts,
    GuestCounts,
    LearningCounts,
    Overview,
    SystemStatus,
    UserCounts,
    UserPatch,
)


def _count(db: Session, stmt: Select[Any]) -> int:
    return int(db.scalar(stmt) or 0)


def _group(db: Session, column, *where) -> dict[str, int]:  # type: ignore[no-untyped-def]
    stmt = select(column, func.count()).where(*where).group_by(column)
    return {str(k): int(v) for k, v in db.execute(stmt).all()}


class AdminService:
    def __init__(self, db: Session, settings: Settings, admin: User) -> None:
        self._db, self._settings, self._admin = db, settings, admin

    # ------------------------------------------------------------ overview
    def overview(self) -> Overview:
        db, now = self._db, datetime.now(UTC)
        live_users = User.deleted_at.is_(None)

        def users_since(days: int) -> int:
            return _count(db, select(func.count()).select_from(User).where(
                live_users, User.created_at >= now - timedelta(days=days)))

        users = UserCounts(
            total=_count(db, select(func.count()).select_from(User).where(live_users)),
            active=_count(db, select(func.count()).select_from(User).where(live_users, User.is_active.is_(True))),
            admins=_count(db, select(func.count()).select_from(User).where(live_users, User.role == "admin")),
            new_7d=users_since(7), new_30d=users_since(30))
        guests = GuestCounts(
            active_sessions=_count(db, select(func.count()).select_from(GuestSession).where(
                GuestSession.deleted_at.is_(None), GuestSession.expires_at > now)),
            expired_pending_cleanup=_count(db, select(func.count()).select_from(GuestSession).where(
                (GuestSession.expires_at <= now) | GuestSession.deleted_at.is_not(None))),
            claimed=_count(db, select(func.count()).select_from(GuestSession).where(
                GuestSession.claimed_by_user_id.is_not(None))))

        def total(model) -> int:  # type: ignore[no-untyped-def]
            stmt = select(func.count()).select_from(model)
            if hasattr(model, "deleted_at"):
                stmt = stmt.where(model.deleted_at.is_(None))
            return _count(db, stmt)

        content = ContentCounts(
            documents_by_kind=_group(db, Document.kind, Document.deleted_at.is_(None)),
            reports=total(Report), career_analyses=total(CareerAnalysis), skill_gap_analyses=total(SkillGapAnalysis),
            interview_sessions=total(InterviewSession), conversations=total(Conversation))
        attempts = _count(db, select(func.count()).select_from(AssessmentAttempt))
        passed = _count(db, select(func.count()).select_from(AssessmentAttempt).where(
            AssessmentAttempt.passed.is_(True)))
        live_rm = LearningRoadmap.deleted_at.is_(None)
        learning = LearningCounts(
            roadmaps_by_status=_group(db, LearningRoadmap.status, live_rm),
            roadmaps_by_duration={str(d): n for d, n in sorted(
                (int(k), v) for k, v in _group(db, LearningRoadmap.duration_days, live_rm).items())},
            assessment_attempts=attempts,
            assessment_pass_rate=round(100 * passed / attempts, 1) if attempts else None)
        achievements = AchievementCounts(
            certificates_by_status=_group(db, Certificate.status),
            certificates_by_type=_group(db, Certificate.certificate_type),
            projects_by_status=_group(db, ProjectSubmission.status, ProjectSubmission.deleted_at.is_(None)),
            public_portfolios=_count(db, select(func.count()).select_from(Portfolio).where(
                Portfolio.visibility == "public")))
        n, avg = db.execute(select(func.count(Feedback.id), func.avg(Feedback.rating))).one()
        community = CommunityCounts(
            ratings=int(n), average_rating=round(float(avg), 2) if avg is not None else None,
            testimonials_by_status=_group(db, Testimonial.status, Testimonial.deleted_at.is_(None)))
        return Overview(generated_at=now, users=users, guests=guests, content=content, learning=learning,
                        achievements=achievements, community=community)

    # ------------------------------------------------------------ users
    def _user_out(self, u: User) -> AdminUserOut:
        db = self._db
        return AdminUserOut(
            id=u.id, email=u.email, display_name=u.display_name, role=u.role, is_active=u.is_active,
            created_at=u.created_at,
            roadmaps=_count(db, select(func.count()).select_from(LearningRoadmap).where(
                LearningRoadmap.user_id == u.id, LearningRoadmap.deleted_at.is_(None))),
            certificates=_count(db, select(func.count()).select_from(Certificate).where(Certificate.user_id == u.id)),
            assessment_attempts=_count(db, select(func.count()).select_from(AssessmentAttempt).where(
                AssessmentAttempt.user_id == u.id)))

    def list_users(self, search: str | None, role: str | None, active: bool | None,
                   limit: int, offset: int) -> list[AdminUserOut]:
        stmt = select(User).where(User.deleted_at.is_(None))
        if search:
            term = search.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(func.lower(User.email).like(f"%{term}%", escape="\\")
                              | func.lower(User.display_name).like(f"%{term}%", escape="\\"))
        if role:
            stmt = stmt.where(User.role == role)
        if active is not None:
            stmt = stmt.where(User.is_active.is_(active))
        rows = self._db.scalars(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)).all()
        return [self._user_out(u) for u in rows]

    def _target(self, user_id: uuid.UUID) -> User:
        u = self._db.get(User, user_id)
        if u is None or u.deleted_at is not None:
            raise NotFoundError()
        return u

    def _other_active_admins(self, excluding: uuid.UUID) -> int:
        return _count(self._db, select(func.count()).select_from(User).where(
            User.role == "admin", User.is_active.is_(True), User.deleted_at.is_(None), User.id != excluding))

    def patch_user(self, user_id: uuid.UUID, body: UserPatch) -> AdminUserOut:
        if body.is_active is None and body.role is None:
            raise InputValidationError("Nothing to change")
        u = self._target(user_id)
        losing_admin = (body.is_active is False and u.role == "admin" and u.is_active) or (
            body.role == "user" and u.role == "admin")
        if u.id == self._admin.id and (body.is_active is False or body.role == "user"):
            raise ConflictError("You cannot deactivate or demote your own account")
        if losing_admin and self._other_active_admins(u.id) == 0:
            raise ConflictError("The last active administrator cannot be deactivated or demoted")
        now = datetime.now(UTC)
        changes: dict[str, Any] = {}
        if body.is_active is not None and body.is_active != u.is_active:
            u.is_active = body.is_active
            changes["is_active"] = body.is_active
            if not body.is_active:  # end access now: access tokens and refresh sessions
                u.tokens_valid_after = now
                self._db.execute(update(UserSession).where(
                    UserSession.user_id == u.id, UserSession.revoked_at.is_(None)).values(revoked_at=now))
        if body.role is not None and body.role != u.role:
            u.role = body.role
            u.tokens_valid_after = now  # forces a fresh token carrying the new privileges
            changes["role"] = body.role
        if changes:
            self._db.add(AuditLog(actor_user_id=self._admin.id, action="admin.user_updated", entity_type="user",
                                  entity_id=str(u.id), details={**changes, "reason": body.reason}))
        self._db.commit()
        return self._user_out(u)

    # ------------------------------------------------------------ audit and content
    def audit_log(self, action: str | None, actor: uuid.UUID | None, limit: int, offset: int) -> list[AuditEntry]:
        stmt = select(AuditLog)
        if action:
            stmt = stmt.where(AuditLog.action.like(action.replace("%", "").replace("_", "\\_") + "%", escape="\\"))
        if actor:
            stmt = stmt.where(AuditLog.actor_user_id == actor)
        rows = self._db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)).all()
        return [AuditEntry(id=r.id, actor_user_id=r.actor_user_id, action=r.action, entity_type=r.entity_type,
                           entity_id=r.entity_id, details=r.details, created_at=r.created_at) for r in rows]

    def assessment_stats(self) -> list[AssessmentStat]:
        db, out = self._db, []
        for a in db.scalars(select(Assessment).order_by(Assessment.title)).all():
            n, passed, avg = db.execute(select(
                func.count(AssessmentAttempt.id),
                func.sum(case((AssessmentAttempt.passed.is_(True), 1), else_=0)),
                func.avg(AssessmentAttempt.score)).where(AssessmentAttempt.assessment_id == a.id)).one()
            out.append(AssessmentStat(
                slug=a.slug or "", title=a.title,
                questions=_count(db, select(func.count()).select_from(AssessmentQuestion).where(
                    AssessmentQuestion.assessment_id == a.id)),
                attempts=int(n), pass_rate=round(100 * int(passed or 0) / n, 1) if n else None,
                average_score=round(float(avg), 1) if avg is not None else None))
        return out

    # ------------------------------------------------------------ system
    def system_status(self) -> SystemStatus:
        s = self._settings
        try:
            self._db.execute(text("SELECT 1"))
            db_status = ComponentStatus(name="database", status="ok", detail="Query succeeded")
        except Exception:  # noqa: BLE001 - report, never leak the driver message
            db_status = ComponentStatus(name="database", status="error", detail="Query failed")
        prod = s.app_env == "production"
        has_llm = bool(s.groq_api_key.get_secret_value())
        chroma = ("Chroma Cloud" if s.chroma_api_key.get_secret_value()
                  else "Chroma server" if s.chroma_host else "local persistent Chroma")
        components = [
            db_status,
            ComponentStatus(name="llm", status="configured" if has_llm else "not_configured",
                            detail=f"Groq model {s.llm_model}" if has_llm else
                            "No API key: narrative and coach answers use deterministic fallbacks"),
            ComponentStatus(name="vector_store", status="configured", detail=chroma),
            ComponentStatus(name="embeddings", status="configured", detail=s.embedding_provider),
            ComponentStatus(name="object_storage", status="configured", detail=s.object_storage_backend),
            ComponentStatus(name="github_token", status="configured" if s.github_token.get_secret_value()
                            else "not_configured", detail="Optional; raises GitHub API rate limits"),
        ]
        warnings = []
        if prod and s.embedding_provider == "hash":
            warnings.append("Hash embeddings are for development and tests only")
        if prod and s.object_storage_backend == "local":
            warnings.append("Local object storage is not durable on ephemeral hosts")
        if prod and s.database_url.startswith("sqlite"):
            warnings.append("SQLite is not supported in production")
        if prod and "localhost" in s.frontend_url:
            warnings.append("FRONTEND_URL still points at localhost")
        if prod and not has_llm:
            warnings.append("No LLM key configured; AI-narrative features are degraded")
        return SystemStatus(environment=s.app_env, roadmap_durations=list(ROADMAP_DURATIONS),
                            share_platforms=list(SHARE_PLATFORMS), components=components, warnings=warnings)

    def record_maintenance(self, action: str, details: dict[str, int]) -> None:
        self._db.add(AuditLog(actor_user_id=self._admin.id, action=action, entity_type="system", details=details))
        self._db.commit()
