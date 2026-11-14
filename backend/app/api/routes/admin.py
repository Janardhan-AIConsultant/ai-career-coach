"""Administrator endpoints (role enforced on every route via ``AdminUser``).

Phase 10 adds certificate management; the rest of the admin dashboard arrives in Phase 13.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import (
    AdminUser,
    DbSession,
    SettingsDep,
    get_object_storage,
    get_vector_store,
)
from app.rag.vector_store import VectorStore
from app.schemas.admin import (
    AdminUserOut,
    AssessmentStat,
    AuditEntry,
    CleanupResult,
    Overview,
    SystemStatus,
    UserPatch,
)
from app.schemas.certificates import CertificateOut, RevokeIn
from app.schemas.feedback import AdminTestimonial, FeedbackAnalytics, ModerateIn
from app.services.admin_service import AdminService
from app.services.certificate_service import CertificateService
from app.services.feedback_service import ModerationService
from app.services.guest_service import cleanup_expired
from app.services.object_storage import ObjectStorage

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/certificates", response_model=list[CertificateOut])
def list_certificates(db: DbSession, settings: SettingsDep, admin: AdminUser,
                      limit: Annotated[int, Query(ge=1, le=200)] = 50,
                      offset: Annotated[int, Query(ge=0)] = 0) -> list[CertificateOut]:
    return CertificateService(db, settings).list_all(limit, offset)


@router.post("/certificates/{certificate_id}/revoke", response_model=CertificateOut)
def revoke_certificate(certificate_id: str, body: RevokeIn, db: DbSession, settings: SettingsDep,
                       admin: AdminUser) -> CertificateOut:
    return CertificateService(db, settings).revoke(admin, certificate_id, body.reason)


# ---------------------------------------------------------------- testimonial moderation (Phase 12)
@router.get("/testimonials", response_model=list[AdminTestimonial])
def moderation_queue(db: DbSession, settings: SettingsDep, admin: AdminUser, status: str | None = None,
                     limit: Annotated[int, Query(ge=1, le=200)] = 50,
                     offset: Annotated[int, Query(ge=0)] = 0) -> list[AdminTestimonial]:
    return ModerationService(db, settings, admin).list(status, limit, offset)


@router.get("/testimonials/{testimonial_id}", response_model=AdminTestimonial)
def moderation_detail(testimonial_id: uuid.UUID, db: DbSession, settings: SettingsDep,
                      admin: AdminUser) -> AdminTestimonial:
    return ModerationService(db, settings, admin).get(testimonial_id)


@router.post("/testimonials/{testimonial_id}/moderate", response_model=AdminTestimonial)
def moderate_testimonial(testimonial_id: uuid.UUID, body: ModerateIn, db: DbSession, settings: SettingsDep,
                         admin: AdminUser) -> AdminTestimonial:
    return ModerationService(db, settings, admin).moderate(testimonial_id, body)


@router.get("/feedback/analytics", response_model=FeedbackAnalytics)
def feedback_analytics(db: DbSession, settings: SettingsDep, admin: AdminUser) -> FeedbackAnalytics:
    return ModerationService(db, settings, admin).analytics()


@router.get("/feedback/export.csv")
def feedback_export(db: DbSession, settings: SettingsDep, admin: AdminUser) -> Response:
    csv_text = ModerationService(db, settings, admin).export_csv()
    return Response(csv_text, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="feedback-aggregate.csv"'})


# ---------------------------------------------------------------- dashboard (Phase 13)
@router.get("/overview", response_model=Overview)
def overview(db: DbSession, settings: SettingsDep, admin: AdminUser) -> Overview:
    return AdminService(db, settings, admin).overview()


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: DbSession, settings: SettingsDep, admin: AdminUser,
               search: Annotated[str | None, Query(max_length=100)] = None,
               role: Annotated[str | None, Query(pattern="^(user|admin)$")] = None,
               active: bool | None = None,
               limit: Annotated[int, Query(ge=1, le=200)] = 50,
               offset: Annotated[int, Query(ge=0)] = 0) -> list[AdminUserOut]:
    return AdminService(db, settings, admin).list_users(search, role, active, limit, offset)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def patch_user(user_id: uuid.UUID, body: UserPatch, db: DbSession, settings: SettingsDep,
               admin: AdminUser) -> AdminUserOut:
    return AdminService(db, settings, admin).patch_user(user_id, body)


@router.get("/audit-logs", response_model=list[AuditEntry])
def audit_logs(db: DbSession, settings: SettingsDep, admin: AdminUser,
               action: Annotated[str | None, Query(max_length=80)] = None, actor: uuid.UUID | None = None,
               limit: Annotated[int, Query(ge=1, le=200)] = 50,
               offset: Annotated[int, Query(ge=0)] = 0) -> list[AuditEntry]:
    return AdminService(db, settings, admin).audit_log(action, actor, limit, offset)


@router.get("/assessments", response_model=list[AssessmentStat])
def assessment_stats(db: DbSession, settings: SettingsDep, admin: AdminUser) -> list[AssessmentStat]:
    return AdminService(db, settings, admin).assessment_stats()


@router.get("/system", response_model=SystemStatus)
def system_status(db: DbSession, settings: SettingsDep, admin: AdminUser) -> SystemStatus:
    return AdminService(db, settings, admin).system_status()


@router.post("/maintenance/cleanup-guests", response_model=CleanupResult)
def cleanup_guests(db: DbSession, settings: SettingsDep, admin: AdminUser,
                   store: Annotated[VectorStore, Depends(get_vector_store)],
                   storage: Annotated[ObjectStorage, Depends(get_object_storage)]) -> CleanupResult:
    purged = cleanup_expired(db, store, storage)
    AdminService(db, settings, admin).record_maintenance("admin.guest_cleanup", {"purged": purged})
    return CleanupResult(guest_sessions_purged=purged)
