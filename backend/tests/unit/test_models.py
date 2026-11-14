"""DB constraint tests (SQLite enforces CHECK constraints; PostgreSQL verified via migration)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import ROADMAP_DURATIONS, SHARE_PLATFORMS
from app.models import (
    Base,
    Certificate,
    Document,
    LearningRoadmap,
    Testimonial,
    TestimonialShareEvent,
)
from tests.conftest import make_guest, make_user


def test_all_28_tables_registered() -> None:
    assert len(Base.metadata.tables) == 30


def test_supported_values_are_exactly_the_allowed_sets() -> None:
    assert ROADMAP_DURATIONS == (7, 15, 60)
    assert SHARE_PLATFORMS == ("linkedin", "whatsapp", "facebook")


@pytest.mark.parametrize("days", [7, 15, 60])
def test_roadmap_allowed_durations(db_session: Session, days: int) -> None:
    u = make_user(db_session)
    db_session.add(LearningRoadmap(user_id=u.id, duration_days=days, goal="g"))
    db_session.commit()


@pytest.mark.parametrize("days", [0, 1, 14, 30, 90])
def test_roadmap_rejects_other_durations(db_session: Session, days: int) -> None:
    u = make_user(db_session)
    db_session.add(LearningRoadmap(user_id=u.id, duration_days=days, goal="g"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def _testimonial(user_id: object, **kw: object) -> Testimonial:
    return Testimonial(user_id=user_id, text="great", feature="platform", **kw)


def test_share_event_platform_allowlist(db_session: Session) -> None:
    u = make_user(db_session)
    t = _testimonial(u.id)
    db_session.add(t)
    db_session.commit()
    for platform in (*SHARE_PLATFORMS, None):
        db_session.add(TestimonialShareEvent(testimonial_id=t.id, platform=platform,
                                             event_type="share_click"))
    db_session.commit()
    for bad in ("twitter", "x", "telegram"):
        db_session.add(TestimonialShareEvent(testimonial_id=t.id, platform=bad,
                                             event_type="share_click"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


def test_testimonial_public_visibility_rules(db_session: Session) -> None:
    u = make_user(db_session)
    t = _testimonial(u.id, status="approved", public_consent=True)
    assert t.is_publicly_visible
    t.public_consent = False
    assert not t.is_publicly_visible
    t.public_consent, t.status = True, "pending"
    assert not t.is_publicly_visible
    t.status, t.consent_withdrawn_at = "approved", datetime.now(UTC)
    assert not t.is_publicly_visible
    t.consent_withdrawn_at, t.deleted_at = None, datetime.now(UTC)
    assert not t.is_publicly_visible


def test_testimonial_rating_bounds(db_session: Session) -> None:
    u = make_user(db_session)
    db_session.add(_testimonial(u.id, rating=6))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_document_requires_exactly_one_owner(db_session: Session) -> None:
    u = make_user(db_session)
    g, _ = make_guest(db_session)
    base = {"kind": "resume", "filename": "a.pdf", "content_type": "application/pdf",
                "size_bytes": 1, "sha256": "0" * 64}
    db_session.add(Document(owner_user_id=u.id, **base))
    db_session.add(Document(guest_session_id=g.id, **base))
    db_session.commit()
    for owners in ({}, {"owner_user_id": u.id, "guest_session_id": g.id}):
        db_session.add(Document(**owners, **base))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


def test_certificate_requires_evidence(db_session: Session) -> None:
    u = make_user(db_session)
    db_session.add(Certificate(certificate_code="C-1", user_id=u.id,
                               certificate_type="assessment", title="t", topic="x",
                               issued_at=datetime.now(UTC)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_unique_email(db_session: Session) -> None:
    make_user(db_session, "dup@example.com")
    with pytest.raises(IntegrityError):
        make_user(db_session, "dup@example.com")
