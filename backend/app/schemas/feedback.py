"""Models for ratings, testimonials, moderation and share analytics."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import (
    FEEDBACK_FEATURES,
    MODERATION_ACTIONS,
    SHARE_EVENT_TYPES,
    SHARE_PLATFORMS,
)

Feature = Literal[FEEDBACK_FEATURES]  # type: ignore[valid-type]
Platform = Literal[SHARE_PLATFORMS]  # type: ignore[valid-type]
EventType = Literal[SHARE_EVENT_TYPES]  # type: ignore[valid-type]
Action = Literal[MODERATION_ACTIONS]  # type: ignore[valid-type]
Status = Literal["pending", "approved", "rejected", "flagged", "removed"]

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(value: str) -> str:
    """Strip control characters and angle brackets; collapse nothing else (the text is the user's own)."""
    return _CONTROL.sub("", value).replace("<", "").replace(">", "").strip()


def _utc(v: datetime | None) -> datetime | None:
    return v if v is None or v.tzinfo else v.replace(tzinfo=UTC)


class FeedbackIn(BaseModel):
    feature: Feature
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def _c(cls, v: str | None) -> str | None:
        return clean(v) or None if v else None


class FeedbackOut(BaseModel):
    id: uuid.UUID
    feature: str
    rating: int
    comment: str | None
    created_at: datetime

    _tz = field_validator("created_at")(_utc)


class TestimonialIn(BaseModel):
    __test__ = False
    text: str = Field(min_length=20, max_length=1000)
    feature: Feature = "platform"
    rating: int | None = Field(default=None, ge=1, le=5)
    would_recommend: bool | None = None
    success_story: str | None = Field(default=None, max_length=2000)
    display_name: str | None = Field(default=None, max_length=60)
    public_consent: bool = False  # explicit opt-in to public display; never assumed

    @field_validator("text")
    @classmethod
    def _text(cls, v: str) -> str:
        v = clean(v)
        if len(v) < 20:
            raise ValueError("Testimonial is too short")
        return v

    @field_validator("success_story", "display_name")
    @classmethod
    def _opt(cls, v: str | None) -> str | None:
        return (clean(v) or None) if v else None


class TestimonialUpdate(BaseModel):
    """Edits reset moderation: approved text must not change without a new review."""

    __test__ = False
    text: str | None = Field(default=None, min_length=20, max_length=1000)
    feature: Feature | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    would_recommend: bool | None = None
    success_story: str | None = Field(default=None, max_length=2000)
    display_name: str | None = Field(default=None, max_length=60)
    public_consent: bool | None = None

    @field_validator("text", "success_story", "display_name")
    @classmethod
    def _c(cls, v: str | None) -> str | None:
        return clean(v) if v is not None else None


class TestimonialOut(BaseModel):
    __test__ = False
    id: uuid.UUID
    text: str
    feature: str
    rating: int | None
    would_recommend: bool | None
    success_story: str | None
    display_name: str | None
    public_consent: bool
    consent_withdrawn_at: datetime | None
    status: Status
    is_public: bool
    public_url: str | None
    created_at: datetime

    _tz = field_validator("created_at", "consent_withdrawn_at")(_utc)


class PublicTestimonial(BaseModel):
    """Everything shown publicly. No email, user id or account name."""

    __test__ = False
    id: uuid.UUID
    text: str
    feature: str
    rating: int | None
    would_recommend: bool | None
    success_story: str | None
    display_name: str


class PublicStats(BaseModel):
    ratings_count: int
    average_rating: float | None
    testimonials_count: int


class ShareLinks(BaseModel):
    """Share *interfaces* only. Opening one does not publish anything on the user's behalf."""

    public_url: str
    share_text: str
    links: dict[str, str]  # keys are exactly SHARE_PLATFORMS
    note: str = ("These links open each platform's own share dialog. You review and post there; "
                 "this platform never posts for you.")


class ShareEventIn(BaseModel):
    event_type: EventType
    platform: Platform | None = None

    @model_validator(mode="after")
    def _platform_rules(self) -> ShareEventIn:
        if self.event_type == "share_click" and self.platform is None:
            raise ValueError("platform is required for share_click")
        return self


class ModerateIn(BaseModel):
    action: Action
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def _n(cls, v: str | None) -> str | None:
        return clean(v) or None if v else None


class ModerationEntry(BaseModel):
    action: str
    previous_status: str
    new_status: str
    note: str | None
    created_at: datetime

    _tz = field_validator("created_at")(_utc)


class AdminTestimonial(TestimonialOut):
    """Admin view: includes review hints computed from the text (not stored)."""

    review_hints: list[str]
    history: list[ModerationEntry] = []


class FeatureRating(BaseModel):
    feature: str
    count: int
    average: float


class FeedbackAnalytics(BaseModel):
    total_ratings: int
    average_rating: float | None
    by_feature: list[FeatureRating]
    rating_distribution: dict[str, int]
    testimonials_by_status: dict[str, int]
    share_events: dict[str, dict[str, int]]  # event_type -> platform|"none" -> count
