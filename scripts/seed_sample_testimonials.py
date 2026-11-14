"""Add clearly labelled SAMPLE testimonials so the landing page can be previewed in development.

These are demo records, not real user feedback: the author is a throwaway "sample" account, every display name
says "(sample)", and the script refuses to run when APP_ENV=production. Remove them with ``--remove``.

Usage (from ``backend/``):
    python ../scripts/seed_sample_testimonials.py            # add
    python ../scripts/seed_sample_testimonials.py --remove   # delete the samples and the sample account
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import delete, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_session_factory  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Feedback, ModerationLog, Testimonial, TestimonialShareEvent, User  # noqa: E402

SAMPLE_EMAIL = "sample-learner@example.invalid"
SAMPLES = [
    ("Sample learner (demo)", "learning_roadmap", 5,
     "The 15 day roadmap broke a big goal into small daily steps. I always knew what to do next."),
    ("Sample learner (demo)", "career_match", 5,
     "Seeing exactly which skills were missing for the job, with a score I could understand, helped me focus my study time."),
    ("Sample learner (demo)", "interview_preparation", 4,
     "The mock interview questions were based on my own gaps, so practice felt relevant and my confidence grew."),
]


def add(db) -> int:  # type: ignore[no-untyped-def]
    user = db.scalar(select(User).where(User.email == SAMPLE_EMAIL))
    if user is None:
        # unusable random password: nobody can sign in as the sample account
        user = User(email=SAMPLE_EMAIL, password_hash=hash_password(secrets.token_urlsafe(24) + "Aa1"),
                    display_name="Sample learner", role="user", is_active=False)
        db.add(user)
        db.flush()
    existing = {t.text for t in db.scalars(select(Testimonial).where(Testimonial.user_id == user.id)).all()}
    created = 0
    for name, feature, rating, text in SAMPLES:
        if text in existing:
            continue
        db.add(Testimonial(user_id=user.id, text=text, feature=feature, rating=rating, display_name=name,
                           public_consent=True, status="approved"))
        db.add(Feedback(user_id=user.id, feature=feature, rating=rating))
        created += 1
    db.commit()
    return created


def remove(db) -> int:  # type: ignore[no-untyped-def]
    user = db.scalar(select(User).where(User.email == SAMPLE_EMAIL))
    if user is None:
        return 0
    ids = select(Testimonial.id).where(Testimonial.user_id == user.id)
    db.execute(delete(TestimonialShareEvent).where(TestimonialShareEvent.testimonial_id.in_(ids)))
    db.execute(delete(ModerationLog).where(ModerationLog.testimonial_id.in_(ids)))
    n = db.execute(delete(Testimonial).where(Testimonial.user_id == user.id)).rowcount
    db.execute(delete(Feedback).where(Feedback.user_id == user.id))
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    return int(n or 0)


def main(argv: list[str]) -> int:
    if get_settings().app_env == "production":
        print("Refusing to create sample testimonials in production.", file=sys.stderr)
        return 2
    with get_session_factory()() as db:
        if "--remove" in argv:
            print(f"removed {remove(db)} sample testimonial(s)")
        else:
            print(f"added {add(db)} sample testimonial(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
