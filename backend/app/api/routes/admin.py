"""Administrator endpoints (role enforced on every route via ``AdminUser``).

Phase 10 adds certificate management; the rest of the admin dashboard arrives in Phase 13.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.dependencies import AdminUser, DbSession, SettingsDep
from app.schemas.certificates import CertificateOut, RevokeIn
from app.schemas.feedback import AdminTestimonial, FeedbackAnalytics, ModerateIn
from app.services.certificate_service import CertificateService
from app.services.feedback_service import ModerationService

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
