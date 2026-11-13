"""Assessment engine: seeding from the authored bank, listing, scoring, attempt history.

All scoring happens here from the stored answer key; the client only sends raw answers. The
answer key is never returned before submission. Attempts are limited per assessment per 24 hours
(the key is revealed after submission, so unlimited retries would allow memorising answers).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assessments.bank import ASSESSMENTS
from app.assessments.scoring import correct_display, score_question
from app.core.exceptions import InputValidationError, NotFoundError, RateLimitExceededError
from app.models import Assessment, AssessmentAttempt, AssessmentQuestion, User
from app.schemas.learning import (
    AssessmentDetail,
    AssessmentSummary,
    AttemptSummary,
    QuestionFeedback,
    QuestionPublic,
    SubmitOut,
)
from app.services.learning_service import LearningService

MAX_ATTEMPTS_PER_DAY = 5
MAX_ANSWER_CHARS = 5000


def seed_assessments(db: Session) -> int:
    """Idempotently insert missing bank assessments (by slug). Returns the number created."""
    existing = set(db.scalars(select(Assessment.slug)).all())
    created = 0
    for item in ASSESSMENTS:
        if item["slug"] in existing:
            continue
        a = Assessment(slug=item["slug"], title=item["title"], topic=item["topic"],
                       difficulty=item["difficulty"], pass_score=item["pass_score"],
                       description=item["description"])
        db.add(a)
        db.flush()
        for pos, q in enumerate(item["questions"]):
            db.add(AssessmentQuestion(
                assessment_id=a.id, key=q["key"], position=pos, points=q["points"], question_type=q["type"],
                prompt=q["prompt"], options=q["options"], correct_answer=q["correct"], explanation=q["explanation"]))
        created += 1
    db.commit()
    return created


def attempt_summary(db: Session, a: AssessmentAttempt) -> AttemptSummary:
    asm = db.get(Assessment, a.assessment_id)
    return AttemptSummary(attempt_id=a.id, slug=asm.slug if asm else None, title=asm.title if asm else "",
                          score=a.score, passed=a.passed, submitted_at=a.submitted_at)


class AssessmentService:
    def __init__(self, db: Session, user: User, learning: LearningService) -> None:
        self._db, self._user, self._learning = db, user, learning

    def _questions(self, assessment: Assessment) -> list[AssessmentQuestion]:
        return list(self._db.scalars(select(AssessmentQuestion).where(
            AssessmentQuestion.assessment_id == assessment.id).order_by(AssessmentQuestion.position)).all())

    def _by_slug(self, slug: str) -> Assessment:
        seed_assessments(self._db)
        a = self._db.scalar(select(Assessment).where(Assessment.slug == slug))
        if a is None:
            raise NotFoundError()
        return a

    def _summary(self, a: Assessment) -> AssessmentSummary:
        n = self._db.scalar(select(func.count()).select_from(AssessmentQuestion).where(
            AssessmentQuestion.assessment_id == a.id)) or 0
        attempts = self._db.scalar(select(func.count()).select_from(AssessmentAttempt).where(
            AssessmentAttempt.assessment_id == a.id, AssessmentAttempt.user_id == self._user.id)) or 0
        best = self._db.scalar(select(func.max(AssessmentAttempt.score)).where(
            AssessmentAttempt.assessment_id == a.id, AssessmentAttempt.user_id == self._user.id))
        return AssessmentSummary(slug=a.slug or "", title=a.title, topic=a.topic, difficulty=a.difficulty,
                                 description=a.description, pass_score=a.pass_score, question_count=n,
                                 attempts=attempts, best_score=best)

    def list_assessments(self) -> list[AssessmentSummary]:
        seed_assessments(self._db)
        rows = self._db.scalars(select(Assessment).order_by(Assessment.title)).all()
        return [self._summary(a) for a in rows]

    def detail(self, slug: str) -> AssessmentDetail:
        a = self._by_slug(slug)
        qs = [QuestionPublic(id=q.id, type=q.question_type, prompt=q.prompt, options=q.options, points=q.points)
              for q in self._questions(a)]  # no correct_answer / explanation here
        return AssessmentDetail(**self._summary(a).model_dump(), questions=qs)

    def submit(self, slug: str, answers: dict[uuid.UUID, Any]) -> SubmitOut:
        a = self._by_slug(slug)
        since = datetime.now(UTC) - timedelta(hours=24)
        recent = self._db.scalar(select(func.count()).select_from(AssessmentAttempt).where(
            AssessmentAttempt.assessment_id == a.id, AssessmentAttempt.user_id == self._user.id,
            AssessmentAttempt.submitted_at >= since)) or 0
        if recent >= MAX_ATTEMPTS_PER_DAY:
            raise RateLimitExceededError("Attempt limit reached for this assessment; try again tomorrow")
        questions = self._questions(a)
        known = {q.id for q in questions}
        if not set(answers) <= known:
            raise InputValidationError("Answers refer to questions that are not part of this assessment")
        if any(isinstance(v, str) and len(v) > MAX_ANSWER_CHARS for v in answers.values()):
            raise InputValidationError("An answer is too long")

        results, earned, possible = [], 0.0, 0
        for q in questions:
            r = score_question(q.question_type, q.options, q.correct_answer, answers.get(q.id))
            earned += r.points * q.points
            possible += q.points
            results.append(QuestionFeedback(
                question_id=q.id, type=q.question_type, points_earned=round(r.points * q.points, 2),
                points_possible=q.points, status=r.status, feedback=r.feedback, explanation=q.explanation,
                correct_answer=correct_display(q.question_type, q.options, q.correct_answer)))
        score = round(100 * earned / possible, 1) if possible else 0.0
        passed = score >= a.pass_score
        attempt = AssessmentAttempt(
            user_id=self._user.id, assessment_id=a.id, score=score, passed=passed,
            submitted_at=datetime.now(UTC),
            answers={"answers": {str(k): v for k, v in answers.items()},
                     "results": [r.model_dump(mode="json") for r in results]})
        self._db.add(attempt)
        self._db.flush()
        completed = self._learning.on_assessment_passed(slug) if passed else 0
        self._db.commit()
        return SubmitOut(attempt_id=attempt.id, slug=slug, score=score, passed=passed, pass_score=a.pass_score,
                         results=results, roadmap_activities_completed=completed)

    def history(self, slug: str | None, limit: int, offset: int) -> list[AttemptSummary]:
        stmt = select(AssessmentAttempt).where(AssessmentAttempt.user_id == self._user.id)
        if slug:
            stmt = stmt.where(AssessmentAttempt.assessment_id == self._by_slug(slug).id)
        rows = self._db.scalars(stmt.order_by(AssessmentAttempt.submitted_at.desc()).limit(limit).offset(offset)).all()
        return [attempt_summary(self._db, r) for r in rows]

    def attempt_detail(self, attempt_id: uuid.UUID) -> dict[str, Any]:
        row = self._db.scalar(select(AssessmentAttempt).where(
            AssessmentAttempt.id == attempt_id, AssessmentAttempt.user_id == self._user.id))
        if row is None:
            raise NotFoundError()
        summary = attempt_summary(self._db, row).model_dump(mode="json")
        return {**summary, "results": (row.answers or {}).get("results", [])}
