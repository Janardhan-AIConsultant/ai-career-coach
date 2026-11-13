"""Career Achievement Portfolio endpoints. Owner routes need a user token; ``/public/{slug}`` is open."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    SettingsDep,
    get_object_storage,
    state_singleton,
)
from app.schemas.learning import ReportCreated, ReportRequest
from app.schemas.portfolio import (
    ApprovalIn,
    ItemPatch,
    LinkedInOut,
    PortfolioOut,
    PublicPortfolio,
    SettingsIn,
    TextOut,
)
from app.services import report_builders as rb
from app.services.object_storage import ObjectStorage
from app.services.portfolio_service import PortfolioService
from app.services.principal import Principal
from app.services.report_render import render
from app.services.report_service import create_report
from app.utils.rate_limit import SlidingWindowLimiter

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _svc(db: DbSession, settings: SettingsDep, user: CurrentUser) -> PortfolioService:
    return PortfolioService(db, settings, user)


Svc = Annotated[PortfolioService, Depends(_svc)]


@router.get("/public/{slug}", response_model=PublicPortfolio)
def public_portfolio(slug: str, request: Request, db: DbSession, settings: SettingsDep) -> PublicPortfolio:
    """Public. Private, withdrawn, deleted and unknown portfolios all return the same 404."""
    limiter: SlidingWindowLimiter = state_singleton(
        request, "portfolio_limiter", lambda: SlidingWindowLimiter(settings.portfolio_requests_per_minute, 60))
    limiter.check(request.client.host if request.client else "unknown")
    return PortfolioService.public_view(db, settings, slug)


@router.get("", response_model=PortfolioOut)
def get_portfolio(svc: Svc) -> PortfolioOut:
    return svc.view()


@router.put("/settings", response_model=PortfolioOut)
def update_settings(body: SettingsIn, svc: Svc) -> PortfolioOut:
    return svc.update_settings(body)


@router.patch("/items/{item_id}", response_model=PortfolioOut)
def patch_item(item_id: uuid.UUID, body: ItemPatch, svc: Svc) -> PortfolioOut:
    return svc.set_item_visibility(item_id, body.is_visible)


@router.post("/rotate-slug", response_model=PortfolioOut)
def rotate_slug(svc: Svc) -> PortfolioOut:
    return svc.rotate_slug()


@router.post("/resume-integration", status_code=204)
def resume_integration(body: ApprovalIn, svc: Svc) -> None:
    svc.set_resume_integration(body.approve)


@router.get("/resume-section", response_model=TextOut)
def resume_section(svc: Svc) -> TextOut:
    return TextOut(text=svc.resume_section())


@router.get("/linkedin-summary", response_model=LinkedInOut)
def linkedin_summary(svc: Svc) -> LinkedInOut:
    return svc.linkedin()


@router.post("/report", response_model=ReportCreated, status_code=201)
def portfolio_report(body: ReportRequest, svc: Svc, db: DbSession, settings: SettingsDep, user: CurrentUser,
                     storage: Annotated[ObjectStorage, Depends(get_object_storage)]) -> ReportCreated:
    data = render(rb.portfolio_doc(svc.view()), body.report_format)
    report = create_report(db, storage, Principal("user", user.id), report_type="portfolio",
                           file_format=body.report_format, data=data, filename=f"career-portfolio.{body.report_format}",
                           max_bytes=settings.max_report_bytes, expires_at=None)
    return ReportCreated(report_id=report.id)
