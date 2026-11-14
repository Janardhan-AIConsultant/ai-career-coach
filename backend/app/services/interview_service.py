"""Interview preparation and mock interviews for registered users.

Question selection and scoring are deterministic (see ``app/interview``). All sessions are
scoped to the owning user; foreign session ids return 404. Answers are stored with their
feedback and deleted with the account.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from statistics import mean

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.career.jd_analysis import analyze_job_description
from app.career.resume_analysis import analyze_resume
from app.core.config import Settings
from app.core.exceptions import InputValidationError, NotFoundError
from app.interview.bank import BY_ID
from app.interview.evaluation import DISCLAIMER, evaluate_answer
from app.interview.selection import Selected, select_questions
from app.models import InterviewAnswer, InterviewSession, User
from app.schemas.interview import (
    AnswerOut,
    MockQuestion,
    MockSessionOut,
    MockStartIn,
    MockSummary,
    PreparedQuestion,
    PrepareIn,
    PrepareOut,
)
from app.services import report_builders as rb
from app.services.career_service import CareerService
from app.services.object_storage import ObjectStorage
from app.services.principal import Principal
from app.services.report_render import render
from app.services.report_service import create_report


class InterviewService:
    def __init__(self, db: Session, storage: ObjectStorage, settings: Settings, user: User) -> None:
        self._db, self._storage, self._s, self._user = db, storage, settings, user
        self._principal = Principal("user", user.id)
        self._career = CareerService(db, storage, settings, self._principal, None)

    def _analyses(self, resume_id: uuid.UUID | None, jd_id: uuid.UUID | None):  # type: ignore[no-untyped-def]
        resume = analyze_resume(self._career.load_resume(resume_id).parsed["text"]) if resume_id else None  # type: ignore[index]
        jd = analyze_job_description(self._career.load_jd(jd_id).parsed["text"]) if jd_id else None  # type: ignore[index]
        return resume, jd

    # ------------------------------------------------------------ preparation
    def prepare(self, body: PrepareIn) -> PrepareOut:
        resume, jd = self._analyses(body.resume_document_id, body.job_description_document_id)
        picked = select_questions(list(body.kinds), resume=resume, jd=jd, topics=body.topics,
                                  count=body.count)
        questions = [self._prepared(s) for s in picked]
        focus = list(dict.fromkeys(s.reason for s in picked if "practise" in s.reason or "requires" in s.reason))[:6]
        report_id = None
        if body.report_format:
            data = render(rb.interview_doc(questions), body.report_format)
            report_id = create_report(
                self._db, self._storage, self._principal, report_type="interview_preparation",
                file_format=body.report_format, data=data,
                filename=f"interview-preparation.{body.report_format}",
                max_bytes=self._s.max_report_bytes, expires_at=None).id
        return PrepareOut(questions=questions, focus_areas=focus, report_id=report_id)

    @staticmethod
    def _prepared(s: Selected) -> PreparedQuestion:
        q = s.question
        return PreparedQuestion(
            id=q.id, kind=q.kind, topic=q.topic, difficulty=q.difficulty, question=q.question,
            reason=s.reason, model_answer=q.model_answer, key_points=[k.text for k in q.key_points],
            practical_example=q.practical_example, follow_ups=list(q.follow_ups),
            evaluation_criteria=q.evaluation_criteria)

    # ------------------------------------------------------------ mock interviews
    def start_mock(self, body: MockStartIn) -> MockSessionOut:
        resume, jd = self._analyses(body.resume_document_id, body.job_description_document_id)
        picked = select_questions(list(body.kinds), resume=resume, jd=jd, topics=body.topics,
                                  count=body.count)
        if not picked:
            raise InputValidationError("No questions match the selection")
        session = InterviewSession(
            user_id=self._user.id, kinds=list(body.kinds),
            question_ids=[s.question.id for s in picked], summary={"reasons": {s.question.id: s.reason for s in picked}})
        self._db.add(session)
        self._db.commit()
        return self._session_out(session)

    def _get(self, session_id: uuid.UUID) -> InterviewSession:
        row = self._db.scalar(select(InterviewSession).where(
            InterviewSession.id == session_id, InterviewSession.user_id == self._user.id))
        if row is None:
            raise NotFoundError()
        return row

    def _session_out(self, s: InterviewSession) -> MockSessionOut:
        reasons = (s.summary or {}).get("reasons", {})
        answered = list(self._db.scalars(select(InterviewAnswer.question_id).where(
            InterviewAnswer.session_id == s.id)).all())
        qs = [BY_ID[i] for i in s.question_ids if i in BY_ID]
        return MockSessionOut(
            session_id=s.id, status=s.status, answered_question_ids=answered, overall_score=s.overall_score,
            created_at=s.created_at,
            questions=[MockQuestion(id=q.id, kind=q.kind, topic=q.topic, difficulty=q.difficulty,
                                    question=q.question, reason=reasons.get(q.id, "")) for q in qs])

    def get_mock(self, session_id: uuid.UUID) -> MockSessionOut:
        return self._session_out(self._get(session_id))

    def list_mocks(self, limit: int = 20, offset: int = 0) -> list[MockSessionOut]:
        rows = self._db.scalars(select(InterviewSession).where(InterviewSession.user_id == self._user.id)
                                .order_by(InterviewSession.created_at.desc()).limit(limit).offset(offset)).all()
        return [self._session_out(r) for r in rows]

    def answer(self, session_id: uuid.UUID, question_id: str, text: str) -> AnswerOut:
        session = self._get(session_id)
        if session.status != "in_progress":
            raise InputValidationError("This interview is already completed")
        if question_id not in session.question_ids:
            raise NotFoundError("Question not part of this interview")
        if len(text) > self._s.interview_answer_max_chars:
            raise InputValidationError("Answer is too long")
        feedback = evaluate_answer(BY_ID[question_id], text)
        self._db.add(InterviewAnswer(session_id=session.id, question_id=question_id,
                                     answer_text=text.strip(), feedback=feedback.model_dump(mode="json"),
                                     overall_score=feedback.overall_score))
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise InputValidationError("This question has already been answered") from exc
        return AnswerOut(question_id=question_id, feedback=feedback)

    def complete(self, session_id: uuid.UUID) -> MockSummary:
        session = self._get(session_id)
        answers = list(self._db.scalars(select(InterviewAnswer).where(
            InterviewAnswer.session_id == session.id)).all())
        if not answers:
            raise InputValidationError("Answer at least one question before completing")
        dims: dict[str, list[int]] = {}
        by_kind: dict[str, list[float]] = {}
        for a in answers:
            for d in a.feedback["dimensions"]:
                if d["score"] is not None:
                    dims.setdefault(d["name"], []).append(d["score"])
            by_kind.setdefault(BY_ID[a.question_id].kind, []).append(a.overall_score)
        averages = {k: round(mean(v), 1) for k, v in dims.items()}
        weakest = [k for k, _ in sorted(averages.items(), key=lambda kv: kv[1])[:2]]
        overall = round(mean(a.overall_score for a in answers), 1)
        recs = [f"Practise {w.replace('_', ' ')}: it was your lowest-scoring dimension" for w in weakest]
        weak_topics = sorted({BY_ID[a.question_id].topic for a in answers if a.overall_score < 50})
        recs += [f"Revisit {t.replace('_', ' ')}" for t in weak_topics[:3]]
        session.status, session.overall_score = "completed", overall
        session.completed_at = datetime.now(UTC)
        session.summary = {**(session.summary or {}), "dimension_averages": averages}
        self._db.commit()
        return MockSummary(
            session_id=session.id, overall_score=overall, answered=len(answers),
            unanswered=len(session.question_ids) - len(answers), dimension_averages=averages,
            by_kind={k: round(mean(v), 1) for k, v in by_kind.items()}, weakest_dimensions=weakest,
            recommendations=recs, disclaimer=DISCLAIMER)
