"""Certificate endpoints: owner actions (auth) and public verification (no auth, rate limited)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    SettingsDep,
    get_object_storage,
    state_singleton,
)
from app.schemas.certificates import CertificateOut, EligibilityItem, IssueIn, VerifyOut
from app.services.certificate_service import CertificateService
from app.services.learning_service import LearningService
from app.services.object_storage import ObjectStorage
from app.utils.rate_limit import SlidingWindowLimiter

router = APIRouter(prefix="/certificates", tags=["certificates"])


def _learning(db: DbSession, storage: Annotated[ObjectStorage, Depends(get_object_storage)],
              settings: SettingsDep, user: CurrentUser) -> LearningService:
    return LearningService(db, storage, settings, user)


@router.get("/verify/{certificate_id}", response_model=VerifyOut)
def verify(certificate_id: str, request: Request, db: DbSession, settings: SettingsDep) -> Response:
    """Public. 200 for valid/revoked, 404 with ``status: invalid`` otherwise."""
    limiter: SlidingWindowLimiter = state_singleton(
        request, "verify_limiter", lambda: SlidingWindowLimiter(settings.verify_requests_per_minute, 60))
    limiter.check(request.client.host if request.client else "unknown")  # limits ID enumeration
    result = CertificateService(db, settings).verify(certificate_id)
    return JSONResponse(result.model_dump(mode="json"), status_code=404 if result.status == "invalid" else 200)


@router.get("/eligibility", response_model=list[EligibilityItem])
def eligibility(db: DbSession, settings: SettingsDep, user: CurrentUser,
                learning: Annotated[LearningService, Depends(_learning)]) -> list[EligibilityItem]:
    return CertificateService(db, settings, user).eligibility(learning)


@router.post("", response_model=CertificateOut, status_code=201)
def issue(body: IssueIn, db: DbSession, settings: SettingsDep, user: CurrentUser,
          learning: Annotated[LearningService, Depends(_learning)]) -> CertificateOut:
    return CertificateService(db, settings, user).issue(
        body.certificate_type, body.source_id, body.learner_name, learning)


@router.get("", response_model=list[CertificateOut])
def my_certificates(db: DbSession, settings: SettingsDep, user: CurrentUser) -> list[CertificateOut]:
    return CertificateService(db, settings, user).list_mine()


@router.get("/{certificate_id}/download")
def download(certificate_id: str, db: DbSession, settings: SettingsDep, user: CurrentUser) -> Response:
    data, filename = CertificateService(db, settings, user).pdf(certificate_id)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
