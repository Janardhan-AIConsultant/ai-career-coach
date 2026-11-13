"""Administrator endpoints (role enforced on every route via ``AdminUser``).

Phase 10 adds certificate management; the rest of the admin dashboard arrives in Phase 13.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import AdminUser, DbSession, SettingsDep
from app.schemas.certificates import CertificateOut, RevokeIn
from app.services.certificate_service import CertificateService

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
