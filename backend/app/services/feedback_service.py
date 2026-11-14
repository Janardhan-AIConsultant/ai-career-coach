"""Ratings, testimonials (consent-gated), moderation and aggregate share analytics.

Rules enforced here:
* A testimonial is public only when approved AND consent was given AND not withdrawn AND not deleted.
* Consent is never assumed (``public_consent`` defaults to false) and can be withdrawn at any time;
  withdrawal takes effect immediately.
* Editing a testimonial returns it to ``pending``; moderators never see text change under an approval.
* Sharing produces links to LinkedIn, WhatsApp and Facebook share dialogs only. Nothing is posted.
* Share events store no user, IP or device identifiers.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import SHARE_PLATFORMS, TESTIMONIAL_STATUSES
from app.core.exceptions import (
    ConflictError,
    InputValidationError,
    NotFoundError,
    RateLimitExceededError,
)
from app.models import AuditLog, Feedback, ModerationLog, Testimonial, TestimonialShareEvent, User
from app.schemas.feedback import (
    AdminTestimonial,
    FeatureRating,
    FeedbackAnalytics,
    FeedbackIn,
    FeedbackOut,
    ModerateIn,
    ModerationEntry,
    PublicStats,
    PublicTestimonial,
    ShareEventIn,
    ShareLinks,
    TestimonialIn,
    TestimonialOut,
    TestimonialUpdate,
)
from app.services.testimonial_card import excerpt, render_card

MAX_FEEDBACK_PER_DAY = 20
MAX_TESTIMONIALS = 5
DELETED_TEXT = "[deleted by author]"

# action -> (resulting status, statuses it may be applied from)
TRANSITIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "approve": ("approved", ("pending", "flagged", "rejected")),
    "reject": ("rejected", ("pending", "flagged", "approved")),
    "flag": ("flagged", ("pending", "approved")),
    "remove": ("removed", ("pending", "approved", "rejected", "flagged")),
}

_LINK = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|net|org|io|in|co)\b)", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s().-]{8,}\d)(?!\d)")


def review_hints(t: Testimonial) -> list[str]:
    """Cheap heuristics to help a human moderator. Advisory only; they never change status."""
    blob = " ".join(filter(None, [t.text, t.success_story, t.display_name]))
    hints = []
    if _LINK.search(blob):
        hints.append("contains a link")
    if _EMAIL.search(blob):
        hints.append("contains an email address")
    if _PHONE.search(blob):
        hints.append("contains a phone-like number")
    letters = [c for c in t.text if c.isalpha()]
    if len(letters) > 20 and sum(c.isupper() for c in letters) / len(letters) > 0.6:
        hints.append("mostly upper case")
    if not t.public_consent or t.consent_withdrawn_at:
        hints.append("no active public-display consent")
    return hints


def _public_url(settings: Settings, t: Testimonial) -> str:
    return f"{settings.frontend_url.rstrip('/')}/testimonials/{t.id}"


def _out(settings: Settings, t: Testimonial) -> TestimonialOut:
    return TestimonialOut(
        id=t.id, text=t.text, feature=t.feature, rating=t.rating, would_recommend=t.would_recommend,
        success_story=t.success_story, display_name=t.display_name, public_consent=t.public_consent,
        consent_withdrawn_at=t.consent_withdrawn_at, status=t.status,
        is_public=t.is_publicly_visible, public_url=_public_url(settings, t) if t.is_publicly_visible else None,
        created_at=t.created_at)


def _public(t: Testimonial) -> PublicTestimonial:
    return PublicTestimonial(
        id=t.id, text=t.text, feature=t.feature, rating=t.rating, would_recommend=t.would_recommend,
        success_story=t.success_story, display_name=t.display_name or "Anonymous learner")


def _visible(db: Session, testimonial_id: uuid.UUID) -> Testimonial:
    """Identical 404 for unknown, pending, rejected, flagged, removed, withdrawn and deleted."""
    t = db.get(Testimonial, testimonial_id)
    if t is None or not t.is_publicly_visible:
        raise NotFoundError()
    return t


def share_text(t: Testimonial) -> str:
    return f"“{excerpt(t.text, 200)}” — {t.display_name or 'Anonymous learner'}, AI Career Coach"


class FeedbackService:
    """Owner-facing operations."""

    def __init__(self, db: Session, settings: Settings, user: User) -> None:
        self._db, self._settings, self._user = db, settings, user

    # ------------------------------------------------------------ ratings
    def submit_feedback(self, body: FeedbackIn) -> FeedbackOut:
        since = datetime.now(UTC) - timedelta(days=1)
        recent = self._db.scalar(select(func.count()).select_from(Feedback).where(
            Feedback.user_id == self._user.id, Feedback.created_at >= since)) or 0
        if recent >= MAX_FEEDBACK_PER_DAY:
            raise RateLimitExceededError("Feedback limit reached; try again tomorrow")
        row = Feedback(user_id=self._user.id, feature=body.feature, rating=body.rating, comment=body.comment)
        self._db.add(row)
        self._db.commit()
        return FeedbackOut(id=row.id, feature=row.feature, rating=row.rating, comment=row.comment,
                           created_at=row.created_at)

    def my_feedback(self, limit: int, offset: int) -> list[FeedbackOut]:
        rows = self._db.scalars(select(Feedback).where(Feedback.user_id == self._user.id)
                                .order_by(Feedback.created_at.desc()).limit(limit).offset(offset)).all()
        return [FeedbackOut(id=r.id, feature=r.feature, rating=r.rating, comment=r.comment,
                            created_at=r.created_at) for r in rows]

    # ------------------------------------------------------------ testimonials
    def _mine(self, testimonial_id: uuid.UUID) -> Testimonial:
        t = self._db.scalar(select(Testimonial).where(
            Testimonial.id == testimonial_id, Testimonial.user_id == self._user.id,
            Testimonial.deleted_at.is_(None)))
        if t is None:
            raise NotFoundError()
        return t

    def create(self, body: TestimonialIn) -> TestimonialOut:
        count = self._db.scalar(select(func.count()).select_from(Testimonial).where(
            Testimonial.user_id == self._user.id, Testimonial.deleted_at.is_(None))) or 0
        if count >= MAX_TESTIMONIALS:
            raise ConflictError(f"You can keep at most {MAX_TESTIMONIALS} testimonials; delete one first")
        t = Testimonial(
            user_id=self._user.id, text=body.text, feature=body.feature, rating=body.rating,
            would_recommend=body.would_recommend, success_story=body.success_story,
            display_name=body.display_name, public_consent=body.public_consent, status="pending")
        self._db.add(t)
        self._db.commit()
        return _out(self._settings, t)

    def list_mine(self) -> list[TestimonialOut]:
        rows = self._db.scalars(select(Testimonial).where(
            Testimonial.user_id == self._user.id, Testimonial.deleted_at.is_(None))
            .order_by(Testimonial.created_at.desc())).all()
        return [_out(self._settings, t) for t in rows]

    def get(self, testimonial_id: uuid.UUID) -> TestimonialOut:
        return _out(self._settings, self._mine(testimonial_id))

    def update(self, testimonial_id: uuid.UUID, body: TestimonialUpdate) -> TestimonialOut:
        t = self._mine(testimonial_id)
        if t.status == "removed":
            raise ConflictError("A testimonial removed by a moderator cannot be edited")
        changes = body.model_dump(exclude_unset=True)
        consent = changes.pop("public_consent", None)
        if "text" in changes and changes["text"] is None:
            raise InputValidationError("Text cannot be empty")
        if "text" in changes and len(changes["text"]) < 20:
            raise InputValidationError("Testimonial is too short")
        content_changed = any(getattr(t, k) != v for k, v in changes.items())
        for k, v in changes.items():
            setattr(t, k, v or None if k in ("success_story", "display_name") else v)
        if consent is False:
            self._withdraw(t)
        elif consent is True and not (t.public_consent and t.consent_withdrawn_at is None):
            t.public_consent, t.consent_withdrawn_at = True, None  # fresh, explicit consent
            t.status = "pending"
        if content_changed and t.status != "pending":
            t.status = "pending"  # content must be reviewed again
        self._db.commit()
        return _out(self._settings, t)

    def _withdraw(self, t: Testimonial) -> None:
        if t.consent_withdrawn_at is None and t.public_consent:
            t.consent_withdrawn_at = datetime.now(UTC)
            self._db.add(AuditLog(actor_user_id=self._user.id, action="testimonial.consent_withdrawn",
                                  entity_type="testimonial", entity_id=str(t.id)))
        t.public_consent = False

    def withdraw_consent(self, testimonial_id: uuid.UUID) -> TestimonialOut:
        t = self._mine(testimonial_id)
        self._withdraw(t)
        self._db.commit()
        return _out(self._settings, t)

    def delete(self, testimonial_id: uuid.UUID) -> None:
        """Soft delete that scrubs the user's words, keeping only the moderation audit trail."""
        t = self._mine(testimonial_id)
        t.text, t.success_story, t.display_name = DELETED_TEXT, None, None
        t.public_consent, t.deleted_at = False, datetime.now(UTC)
        self._db.commit()

    def share_links(self, testimonial_id: uuid.UUID) -> ShareLinks:
        t = self._mine(testimonial_id)
        if not t.is_publicly_visible:
            raise ConflictError("Only an approved testimonial with active public-display consent can be shared")
        url, text = _public_url(self._settings, t), share_text(t)
        links = {
            "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={quote(url, safe='')}",
            "whatsapp": f"https://wa.me/?text={quote(text + ' ' + url, safe='')}",
            "facebook": f"https://www.facebook.com/sharer/sharer.php?u={quote(url, safe='')}",
        }
        assert tuple(links) == SHARE_PLATFORMS
        return ShareLinks(public_url=url, share_text=text, links=links)

    # ------------------------------------------------------------ public (static)
    @staticmethod
    def public_list(db: Session, limit: int, offset: int) -> list[PublicTestimonial]:
        rows = db.scalars(select(Testimonial).where(
            Testimonial.status == "approved", Testimonial.public_consent.is_(True),
            Testimonial.consent_withdrawn_at.is_(None), Testimonial.deleted_at.is_(None))
            .order_by(Testimonial.created_at.desc()).limit(limit).offset(offset)).all()
        return [_public(t) for t in rows]

    @staticmethod
    def public_get(db: Session, testimonial_id: uuid.UUID) -> PublicTestimonial:
        return _public(_visible(db, testimonial_id))

    @staticmethod
    def public_card(db: Session, testimonial_id: uuid.UUID) -> bytes:
        t = _visible(db, testimonial_id)
        return render_card(t.text, t.display_name or "Anonymous learner", t.rating)

    @staticmethod
    def public_stats(db: Session) -> PublicStats:
        n, avg = db.execute(select(func.count(Feedback.id), func.avg(Feedback.rating))).one()
        shown = db.scalar(select(func.count()).select_from(Testimonial).where(
            Testimonial.status == "approved", Testimonial.public_consent.is_(True),
            Testimonial.consent_withdrawn_at.is_(None), Testimonial.deleted_at.is_(None))) or 0
        return PublicStats(ratings_count=n, average_rating=round(float(avg), 2) if avg is not None else None,
                           testimonials_count=shown)

    @staticmethod
    def record_event(db: Session, testimonial_id: uuid.UUID, body: ShareEventIn) -> None:
        """Aggregate counter only: testimonial id, platform, event type, time. Nothing identifying."""
        t = _visible(db, testimonial_id)
        db.add(TestimonialShareEvent(testimonial_id=t.id, platform=body.platform, event_type=body.event_type))
        db.commit()


class ModerationService:
    """Admin operations; every route using this requires the admin role."""

    def __init__(self, db: Session, settings: Settings, admin: User) -> None:
        self._db, self._settings, self._admin = db, settings, admin

    def _admin_view(self, t: Testimonial) -> AdminTestimonial:
        logs = self._db.scalars(select(ModerationLog).where(ModerationLog.testimonial_id == t.id)
                                .order_by(ModerationLog.created_at)).all()
        return AdminTestimonial(
            **_out(self._settings, t).model_dump(), review_hints=review_hints(t),
            history=[ModerationEntry(action=m.action, previous_status=m.previous_status,
                                     new_status=m.new_status, note=m.note, created_at=m.created_at) for m in logs])

    def list(self, status: str | None, limit: int, offset: int) -> list[AdminTestimonial]:
        if status is not None and status not in TESTIMONIAL_STATUSES:
            raise InputValidationError("Unknown status")
        stmt = select(Testimonial).where(Testimonial.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Testimonial.status == status)
        rows = self._db.scalars(stmt.order_by(Testimonial.created_at).limit(limit).offset(offset)).all()
        return [self._admin_view(t) for t in rows]

    def get(self, testimonial_id: uuid.UUID) -> AdminTestimonial:
        t = self._db.get(Testimonial, testimonial_id)
        if t is None or t.deleted_at is not None:
            raise NotFoundError()
        return self._admin_view(t)

    def moderate(self, testimonial_id: uuid.UUID, body: ModerateIn) -> AdminTestimonial:
        t = self._db.get(Testimonial, testimonial_id)
        if t is None or t.deleted_at is not None:
            raise NotFoundError()
        new, allowed_from = TRANSITIONS[body.action]
        if t.status not in allowed_from:
            raise ConflictError(f"Cannot {body.action} a testimonial that is {t.status}")
        if body.action == "approve" and (not t.public_consent or t.consent_withdrawn_at is not None):
            raise ConflictError("Cannot approve: the author has not given (or has withdrawn) public-display consent")
        previous, t.status = t.status, new
        self._db.add(ModerationLog(testimonial_id=t.id, admin_user_id=self._admin.id, action=body.action,
                                   previous_status=previous, new_status=new, note=body.note))
        self._db.add(AuditLog(actor_user_id=self._admin.id, action=f"testimonial.{body.action}",
                              entity_type="testimonial", entity_id=str(t.id)))
        self._db.commit()
        return self._admin_view(t)

    def analytics(self) -> FeedbackAnalytics:
        db = self._db
        total, avg = db.execute(select(func.count(Feedback.id), func.avg(Feedback.rating))).one()
        by_feature = [FeatureRating(feature=f, count=c, average=round(float(a), 2)) for f, c, a in db.execute(
            select(Feedback.feature, func.count(Feedback.id), func.avg(Feedback.rating))
            .group_by(Feedback.feature).order_by(Feedback.feature)).all()]
        dist = {str(i): 0 for i in range(1, 6)}
        for r, c in db.execute(select(Feedback.rating, func.count(Feedback.id)).group_by(Feedback.rating)).all():
            dist[str(r)] = c
        statuses = {s: 0 for s in TESTIMONIAL_STATUSES}
        for s, c in db.execute(select(Testimonial.status, func.count(Testimonial.id)).where(
                Testimonial.deleted_at.is_(None)).group_by(Testimonial.status)).all():
            statuses[s] = c
        events: dict[str, dict[str, int]] = {}
        for et, pf, c in db.execute(select(TestimonialShareEvent.event_type, TestimonialShareEvent.platform,
                                           func.count(TestimonialShareEvent.id))
                                    .group_by(TestimonialShareEvent.event_type, TestimonialShareEvent.platform)).all():
            events.setdefault(et, {})[pf or "none"] = c
        return FeedbackAnalytics(total_ratings=total, average_rating=round(float(avg), 2) if avg is not None else None,
                                 by_feature=by_feature, rating_distribution=dist,
                                 testimonials_by_status=statuses, share_events=events)

    def export_csv(self) -> str:
        """Aggregate export. Contains counts and averages only: no names, emails, comments or text."""
        a = self.analytics()
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["section", "key", "subkey", "value"])
        w.writerow(["ratings", "total", "", a.total_ratings])
        w.writerow(["ratings", "average", "", "" if a.average_rating is None else a.average_rating])
        for f in a.by_feature:
            w.writerow(["feature_count", f.feature, "", f.count])
            w.writerow(["feature_average", f.feature, "", f.average])
        for k, v in a.rating_distribution.items():
            w.writerow(["rating_distribution", k, "", v])
        for k, v in a.testimonials_by_status.items():
            w.writerow(["testimonials_by_status", k, "", v])
        for et, by in sorted(a.share_events.items()):
            for pf, v in sorted(by.items()):
                w.writerow(["share_events", et, pf, v])
        self._db.add(AuditLog(actor_user_id=self._admin.id, action="feedback.exported", entity_type="feedback"))
        self._db.commit()
        return out.getvalue()
