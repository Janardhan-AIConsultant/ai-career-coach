"""Practical projects: recommendations, submissions and static evidence evaluation.

Submissions and evaluations are owned by one user. A repository that already passed evaluation for
another user cannot be reused (prevents sharing one repo to farm certificates). Evaluations never
run code; see ``app/projects/evaluation.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    InputValidationError,
    NotFoundError,
    RateLimitExceededError,
)
from app.models import AuditLog, LearningRoadmap, ProjectEvaluation, ProjectSubmission, User
from app.projects.catalog import BY_ID, TEMPLATES, ProjectTemplate
from app.projects.evaluation import evaluate_project
from app.projects.github import RepoEvidence, RepoFetcher, parse_repo_url, repo_key
from app.schemas.projects import (
    EvaluationOut,
    RecommendationOut,
    SubmissionIn,
    SubmissionOut,
    TemplateOut,
)
from app.services.career_service import CareerService
from app.services.principal import Principal
from app.workflows.career_graph import build_career_graph

MAX_EVALUATIONS_PER_DAY = 3


def template_out(t: ProjectTemplate) -> TemplateOut:
    return TemplateOut(
        id=t.id, title=t.title, kind=t.kind, difficulty=t.difficulty, description=t.description,
        skills=list(t.skills), requirements=[r.text for r in t.requirements],
        expected_outcomes=list(t.expected_outcomes), technologies=list(t.technologies),
        milestones=[m.text for m in t.milestones])


def _norm(s: str) -> str:
    return s.strip().lower().replace("_", " ")


class ProjectService:
    def __init__(self, db: Session, settings: Settings, user: User, fetcher: RepoFetcher) -> None:
        self._db, self._s, self._user, self._fetcher = db, settings, user, fetcher

    # ------------------------------------------------------------ recommendations
    def _user_skills(self, roadmap_id: uuid.UUID | None, resume_id: uuid.UUID | None,
                     jd_id: uuid.UUID | None) -> set[str]:
        skills: set[str] = set()
        if roadmap_id:
            r = self._db.scalar(select(LearningRoadmap).where(
                LearningRoadmap.id == roadmap_id, LearningRoadmap.user_id == self._user.id,
                LearningRoadmap.deleted_at.is_(None)))
            if r is None:
                raise NotFoundError()
            skills |= {_norm(s) for s in (r.focus_skills or [])}
        if bool(resume_id) != bool(jd_id):
            raise InputValidationError("Provide both a resume and a job description, or neither")
        if resume_id and jd_id:
            career = CareerService(self._db, None, self._s, Principal("user", self._user.id), None)  # type: ignore[arg-type]
            state = build_career_graph(None).invoke({
                "resume_text": career.load_resume(resume_id).parsed["text"],  # type: ignore[index]
                "jd_text": career.load_jd(jd_id).parsed["text"],  # type: ignore[index]
                "declared_absent": set(), "include_narrative": False})
            skills |= {_norm(g.skill) for g in state["gaps"].gaps}
        return skills

    def recommend(self, roadmap_id: uuid.UUID | None, resume_id: uuid.UUID | None,
                  jd_id: uuid.UUID | None) -> list[RecommendationOut]:
        skills = self._user_skills(roadmap_id, resume_id, jd_id)
        out = []
        for t in TEMPLATES:
            matched = sorted({_norm(s) for s in t.skills} & skills)
            reason = (f"Practises your focus areas: {', '.join(matched)}" if matched
                      else "General practice project")
            out.append(RecommendationOut(template=template_out(t), matched_skills=matched, reason=reason))
        out.sort(key=lambda r: -len(r.matched_skills))
        return out

    # ------------------------------------------------------------ submissions
    def submit(self, body: SubmissionIn) -> SubmissionOut:
        tpl = BY_ID.get(body.template_id)
        if tpl is None:
            raise NotFoundError("Unknown project template")
        if not body.repo_url and not body.documentation_text:
            raise InputValidationError("Provide a GitHub repository URL or pasted documentation")
        if tpl.kind == "code" and not body.repo_url:
            raise InputValidationError("This project needs a public GitHub repository URL")
        count = self._db.scalar(select(func.count()).select_from(ProjectSubmission).where(
            ProjectSubmission.user_id == self._user.id, ProjectSubmission.deleted_at.is_(None))) or 0
        if count >= self._s.max_projects_per_user:
            raise RateLimitExceededError("Project submission limit reached")
        key = None
        if body.repo_url:
            key = repo_key(*parse_repo_url(body.repo_url))
            taken = self._db.scalar(select(ProjectSubmission.id).join(
                ProjectEvaluation, ProjectEvaluation.submission_id == ProjectSubmission.id).where(
                ProjectSubmission.repo_key == key, ProjectSubmission.user_id != self._user.id,
                ProjectEvaluation.passed.is_(True)).limit(1))
            if taken is not None:
                raise ConflictError("This repository has already been submitted by another learner")
        sub = ProjectSubmission(
            user_id=self._user.id, title=tpl.title, template_id=tpl.id, repo_key=key,
            repo_url=body.repo_url.strip() if body.repo_url else None, documentation_url=body.documentation_url,
            documentation_text=body.documentation_text, notes=body.notes, status="submitted")
        self._db.add(sub)
        self._db.commit()
        return self._out(sub)

    def _get(self, submission_id: uuid.UUID) -> ProjectSubmission:
        sub = self._db.scalar(select(ProjectSubmission).where(
            ProjectSubmission.id == submission_id, ProjectSubmission.user_id == self._user.id,
            ProjectSubmission.deleted_at.is_(None)))
        if sub is None:
            raise NotFoundError()
        return sub

    def _latest(self, sub: ProjectSubmission) -> ProjectEvaluation | None:
        return self._db.scalar(select(ProjectEvaluation).where(ProjectEvaluation.submission_id == sub.id)
                               .order_by(ProjectEvaluation.created_at.desc()).limit(1))

    def _out(self, sub: ProjectSubmission) -> SubmissionOut:
        ev = self._latest(sub)
        return SubmissionOut(
            id=sub.id, template_id=sub.template_id, title=sub.title, repo_url=sub.repo_url,
            documentation_url=sub.documentation_url, status=sub.status, created_at=sub.created_at,
            latest_evaluation=EvaluationOut(
                id=ev.id, overall_score=ev.overall_score, passed=ev.passed, code_executed=ev.code_executed,
                details=ev.criteria_scores or {}, created_at=ev.created_at) if ev else None)

    def get(self, submission_id: uuid.UUID) -> SubmissionOut:
        return self._out(self._get(submission_id))

    def list_submissions(self) -> list[SubmissionOut]:
        rows = self._db.scalars(select(ProjectSubmission).where(
            ProjectSubmission.user_id == self._user.id, ProjectSubmission.deleted_at.is_(None))
            .order_by(ProjectSubmission.created_at.desc())).all()
        return [self._out(r) for r in rows]

    # ------------------------------------------------------------ evaluation
    def evaluate(self, submission_id: uuid.UUID) -> SubmissionOut:
        sub = self._get(submission_id)
        since = datetime.now(UTC) - timedelta(hours=24)
        recent = self._db.scalar(select(func.count()).select_from(ProjectEvaluation).where(
            ProjectEvaluation.submission_id == sub.id, ProjectEvaluation.created_at >= since)) or 0
        if recent >= MAX_EVALUATIONS_PER_DAY:
            raise RateLimitExceededError("Evaluation limit reached for this submission; try again tomorrow")
        tpl = BY_ID[sub.template_id or ""]
        evidence: RepoEvidence | None = None
        if sub.repo_url:
            evidence = self._fetcher.fetch(*parse_repo_url(sub.repo_url))
        result = evaluate_project(tpl, evidence, sub.documentation_text or "", self._s.project_pass_score)
        feedback = "\n".join([result.disclaimer, *result.improvements]) if result.improvements else result.disclaimer
        self._db.add(ProjectEvaluation(
            submission_id=sub.id, criteria_scores=result.model_dump(mode="json"),
            overall_score=result.overall_score, passed=result.passed, feedback=feedback, code_executed=False))
        sub.status = "passed" if result.passed else "needs_work"
        self._db.add(AuditLog(actor_user_id=self._user.id, action="project.evaluated", entity_type="project_submission",
                              entity_id=str(sub.id), details={"passed": result.passed, "score": result.overall_score}))
        self._db.commit()
        return self._out(sub)

    def delete(self, submission_id: uuid.UUID) -> None:
        sub = self._get(submission_id)
        sub.deleted_at = datetime.now(UTC)
        self._db.commit()
