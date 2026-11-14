"""Ratings and testimonials. Public routes are open (rate limited) and only ever expose approved,
consented testimonials; everything else needs a registered user's token."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.dependencies import CurrentUser, DbSession, SettingsDep, state_singleton
from app.schemas.feedback import (
    FeedbackIn,
    FeedbackOut,
    PublicStats,
    PublicTestimonial,
    ShareEventIn,
    ShareLinks,
    TestimonialIn,
    TestimonialOut,
    TestimonialUpdate,
)
from app.services.feedback_service import FeedbackService
from app.utils.rate_limit import SlidingWindowLimiter

router = APIRouter(tags=["feedback"])


def _svc(db: DbSession, settings: SettingsDep, user: CurrentUser) -> FeedbackService:
    return FeedbackService(db, settings, user)


Svc = Annotated[FeedbackService, Depends(_svc)]


def _limit(request: Request, settings: SettingsDep) -> None:
    limiter: SlidingWindowLimiter = state_singleton(
        request, "public_feedback_limiter",
        lambda: SlidingWindowLimiter(settings.public_feedback_requests_per_minute, 60))
    limiter.check(request.client.host if request.client else "unknown")


PublicLimit = Depends(_limit)


# ---------------------------------------------------------------- public
@router.get("/testimonials/public", response_model=list[PublicTestimonial], dependencies=[PublicLimit])
def public_testimonials(db: DbSession, limit: Annotated[int, Query(ge=1, le=50)] = 20,
                        offset: Annotated[int, Query(ge=0)] = 0) -> list[PublicTestimonial]:
    return FeedbackService.public_list(db, limit, offset)


@router.get("/feedback/stats", response_model=PublicStats, dependencies=[PublicLimit])
def public_stats(db: DbSession) -> PublicStats:
    return FeedbackService.public_stats(db)


@router.get("/testimonials/public/{testimonial_id}", response_model=PublicTestimonial, dependencies=[PublicLimit])
def public_testimonial(testimonial_id: uuid.UUID, db: DbSession) -> PublicTestimonial:
    return FeedbackService.public_get(db, testimonial_id)


@router.get("/testimonials/public/{testimonial_id}/card.png", dependencies=[PublicLimit])
def public_card(testimonial_id: uuid.UUID, db: DbSession) -> Response:
    png = FeedbackService.public_card(db, testimonial_id)
    return Response(png, media_type="image/png", headers={
        "Content-Disposition": 'attachment; filename="testimonial.png"', "Cache-Control": "no-store"})


@router.post("/testimonials/public/{testimonial_id}/events", status_code=204, dependencies=[PublicLimit])
def share_event(testimonial_id: uuid.UUID, body: ShareEventIn, db: DbSession) -> Response:
    FeedbackService.record_event(db, testimonial_id, body)
    return Response(status_code=204)


# ---------------------------------------------------------------- ratings
@router.post("/feedback", response_model=FeedbackOut, status_code=201)
def submit_feedback(body: FeedbackIn, svc: Svc) -> FeedbackOut:
    return svc.submit_feedback(body)


@router.get("/feedback", response_model=list[FeedbackOut])
def my_feedback(svc: Svc, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                offset: Annotated[int, Query(ge=0)] = 0) -> list[FeedbackOut]:
    return svc.my_feedback(limit, offset)


# ---------------------------------------------------------------- owner testimonials
@router.post("/testimonials", response_model=TestimonialOut, status_code=201)
def create_testimonial(body: TestimonialIn, svc: Svc) -> TestimonialOut:
    return svc.create(body)


@router.get("/testimonials", response_model=list[TestimonialOut])
def my_testimonials(svc: Svc) -> list[TestimonialOut]:
    return svc.list_mine()


@router.get("/testimonials/{testimonial_id}", response_model=TestimonialOut)
def get_testimonial(testimonial_id: uuid.UUID, svc: Svc) -> TestimonialOut:
    return svc.get(testimonial_id)


@router.patch("/testimonials/{testimonial_id}", response_model=TestimonialOut)
def update_testimonial(testimonial_id: uuid.UUID, body: TestimonialUpdate, svc: Svc) -> TestimonialOut:
    return svc.update(testimonial_id, body)


@router.post("/testimonials/{testimonial_id}/withdraw-consent", response_model=TestimonialOut)
def withdraw_consent(testimonial_id: uuid.UUID, svc: Svc) -> TestimonialOut:
    return svc.withdraw_consent(testimonial_id)


@router.delete("/testimonials/{testimonial_id}", status_code=204)
def delete_testimonial(testimonial_id: uuid.UUID, svc: Svc) -> Response:
    svc.delete(testimonial_id)
    return Response(status_code=204)


@router.get("/testimonials/{testimonial_id}/share", response_model=ShareLinks)
def share_links(testimonial_id: uuid.UUID, svc: Svc) -> ShareLinks:
    return svc.share_links(testimonial_id)
