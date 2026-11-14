"""Learning roadmaps: generation, start, progress, completion rules.

Only 7, 15 and 60-day roadmaps exist (validated here, by the API enum and by a DB CHECK).
Assessment activities can only be completed by passing the assessment (``on_assessment_passed``),
so a roadmap cannot be completed by clicking alone. Everything is scoped to the owning user.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.career.taxonomy import LEADERSHIP_CATEGORIES, leadership_patterns, skill_patterns
from app.core.config import Settings
from app.core.exceptions import InputValidationError, NotFoundError, RateLimitExceededError
from app.learning.curriculum import FocusItem, build_roadmap, validate_duration
from app.models import (
    AssessmentAttempt,
    LearningActivity,
    LearningModule,
    LearningRoadmap,
    User,
)
from app.schemas.learning import (
    ActivityOut,
    DashboardOut,
    ModuleOut,
    ProgressOut,
    Requirement,
    RoadmapCreateIn,
    RoadmapOut,
    RoadmapSummary,
)
from app.services import report_builders as rb
from app.services.career_service import CareerService
from app.services.object_storage import ObjectStorage
from app.services.portfolio_service import touch_portfolio
from app.services.principal import Principal
from app.services.report_render import render
from app.services.report_service import create_report
from app.workflows.career_graph import build_career_graph

MAX_ROADMAPS = 10
_KIND_RANK = {"learn": 0, "project": 0, "exercise": 1, "assessment": 2, "review": 2}


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def _normalise(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower().replace("_", " "))


def activity_out(a: LearningActivity) -> ActivityOut:
    return ActivityOut(
        id=a.id, day_number=a.day_number, title=a.title, kind=a.kind, description=a.description,
        resources=list(a.resources or []), estimated_minutes=a.estimated_minutes,
        is_required=a.is_required, ref=a.ref, completed_at=a.completed_at)


class LearningService:
    def __init__(self, db: Session, storage: ObjectStorage, settings: Settings, user: User) -> None:
        self._db, self._storage, self._s, self._user = db, storage, settings, user
        self._principal = Principal("user", user.id)
        self._career = CareerService(db, storage, settings, self._principal, None)

    # ------------------------------------------------------------ focus selection
    def _explicit_focus(self, names: list[str]) -> list[FocusItem]:
        skills = skill_patterns()
        leadership = {_normalise(c): c for c in LEADERSHIP_CATEGORIES}
        items, unknown = [], []
        for raw in names:
            n = _normalise(raw)
            if n in skills:
                items.append(FocusItem(n, skills[n][0], "You chose this focus skill"))
            elif n in leadership:
                items.append(FocusItem(leadership[n], "leadership", "You chose this leadership area"))
            else:
                unknown.append(raw)
        if unknown:
            raise InputValidationError("Unsupported focus skills: " + ", ".join(unknown[:5]))
        return items

    def _gap_focus(self, resume_id: uuid.UUID, jd_id: uuid.UUID) -> list[FocusItem]:
        resume, jd = self._career.load_resume(resume_id), self._career.load_jd(jd_id)
        state = build_career_graph(None).invoke({
            "resume_text": resume.parsed["text"], "jd_text": jd.parsed["text"],  # type: ignore[index]
            "declared_absent": set(), "include_narrative": False})
        items = []
        for g in state["gaps"].gaps:
            reason = f"{g.severity.capitalize()} gap for the target job: {g.current_evidence}"
            if g.kind == "leadership":
                items.append(FocusItem(_normalise(g.skill).replace(" ", "_"), "leadership", reason))
            else:
                items.append(FocusItem(g.skill, g.group, reason))
        return items

    def _goal_focus(self, goal: str) -> list[FocusItem]:
        items = [FocusItem(s, grp, "Mentioned in your goal") for s, (grp, rx) in skill_patterns().items() if rx.search(goal)]
        items += [FocusItem(c, "leadership", "Mentioned in your goal") for c, pats in leadership_patterns().items()
                  if any(p.search(goal) for p in pats)]
        return items

    # ------------------------------------------------------------ creation
    def create(self, body: RoadmapCreateIn) -> RoadmapOut:
        validate_duration(body.duration_days)  # server-side allowlist (7, 15, 60)
        live = self._db.scalar(select(func.count()).select_from(LearningRoadmap).where(
            LearningRoadmap.user_id == self._user.id, LearningRoadmap.deleted_at.is_(None)))
        if (live or 0) >= MAX_ROADMAPS:
            raise RateLimitExceededError("Roadmap limit reached; delete an old roadmap first")
        if bool(body.resume_document_id) != bool(body.job_description_document_id):
            raise InputValidationError("Provide both a resume and a job description, or neither")
        focus: list[FocusItem] = []
        if body.focus_skills:
            focus = self._explicit_focus(body.focus_skills)
        elif body.resume_document_id and body.job_description_document_id:
            focus = self._gap_focus(body.resume_document_id, body.job_description_document_id)
        if not focus:
            focus = self._goal_focus(body.goal)
        plan = build_roadmap(body.duration_days, body.goal, list(dict.fromkeys(focus)))
        roadmap = LearningRoadmap(
            user_id=self._user.id, duration_days=body.duration_days, goal=body.goal.strip(), title=plan.title,
            focus_skills=[m.title for m in plan.modules if m.title != "Capstone project"],
            completion_criteria=plan.completion_criteria, estimated_hours=plan.estimated_hours,
            status="not_started")
        self._db.add(roadmap)
        self._db.flush()
        for pos, m in enumerate(plan.modules, 1):
            module = LearningModule(roadmap_id=roadmap.id, position=pos, title=m.title,
                                    objectives=m.objectives, topics=m.topics)
            self._db.add(module)
            self._db.flush()
            for a in m.activities:
                self._db.add(LearningActivity(
                    module_id=module.id, day_number=a.day, title=a.title[:300], kind=a.kind,
                    description=a.description, resources=a.resources, estimated_minutes=a.minutes,
                    ref=a.ref, is_required=a.required))
        self._db.commit()
        return self.get(roadmap.id)

    # ------------------------------------------------------------ reading
    def _roadmap(self, roadmap_id: uuid.UUID) -> LearningRoadmap:
        row = self._db.scalar(select(LearningRoadmap).where(
            LearningRoadmap.id == roadmap_id, LearningRoadmap.user_id == self._user.id,
            LearningRoadmap.deleted_at.is_(None)))
        if row is None:
            raise NotFoundError()
        return row

    def _modules(self, roadmap_id: uuid.UUID) -> list[tuple[LearningModule, list[LearningActivity]]]:
        mods = self._db.scalars(select(LearningModule).where(LearningModule.roadmap_id == roadmap_id)
                                .order_by(LearningModule.position)).all()
        out = []
        for m in mods:
            acts = sorted(self._db.scalars(select(LearningActivity).where(LearningActivity.module_id == m.id)).all(),
                          key=lambda a: (a.day_number, _KIND_RANK.get(a.kind, 1), a.created_at))
            out.append((m, acts))
        return out

    def _progress(self, roadmap: LearningRoadmap, mods: list[tuple[LearningModule, list[LearningActivity]]]) -> ProgressOut:
        required = [a for _, acts in mods for a in acts if a.is_required]
        done = [a for a in required if a.completed_at]
        pct = round(100 * len(done) / len(required), 1) if required else 0.0
        criteria = roadmap.completion_criteria or {}
        need_pct = float(criteria.get("min_required_activity_percent", 80))
        assess = [a for a in required if a.kind == "assessment"]
        reqs = [Requirement(name=f"Complete at least {need_pct:g}% of required activities", met=pct >= need_pct)]
        if assess:
            reqs.append(Requirement(name="Pass every assessment in the plan",
                                    met=all(a.completed_at for a in assess)))
        nxt = [a for a in sorted((a for a in required if not a.completed_at),
                                 key=lambda a: (a.day_number, _KIND_RANK.get(a.kind, 1)))][:5]
        return ProgressOut(
            percent_required_complete=pct, completed_required=len(done), total_required=len(required),
            requirements=reqs, criteria_met=all(r.met for r in reqs), next_activities=[activity_out(a) for a in nxt])

    def _out(self, roadmap: LearningRoadmap) -> RoadmapOut:
        mods = self._modules(roadmap.id)
        return RoadmapOut(
            id=roadmap.id, title=roadmap.title, duration_days=roadmap.duration_days,
            goal=roadmap.goal, status=roadmap.status, started_at=roadmap.started_at,
            completed_at=roadmap.completed_at, estimated_hours=roadmap.estimated_hours,
            focus_skills=list(roadmap.focus_skills or []), completion_criteria=roadmap.completion_criteria or {},
            modules=[ModuleOut(
                id=m.id, position=m.position, title=m.title, objectives=list(m.objectives or []),
                topics=list(m.topics or []), activities=[activity_out(a) for a in acts],
                completed=sum(1 for a in acts if a.completed_at), total=len(acts)) for m, acts in mods],
            progress=self._progress(roadmap, mods))

    def get(self, roadmap_id: uuid.UUID) -> RoadmapOut:
        return self._out(self._roadmap(roadmap_id))

    def list_roadmaps(self) -> list[RoadmapSummary]:
        rows = self._db.scalars(select(LearningRoadmap).where(
            LearningRoadmap.user_id == self._user.id, LearningRoadmap.deleted_at.is_(None))
            .order_by(LearningRoadmap.created_at.desc())).all()
        return [RoadmapSummary(
            id=r.id, title=r.title, duration_days=r.duration_days,
            status=r.status, started_at=r.started_at,
            percent_required_complete=self._progress(r, self._modules(r.id)).percent_required_complete) for r in rows]

    # ------------------------------------------------------------ actions
    def start(self, roadmap_id: uuid.UUID) -> RoadmapOut:
        r = self._roadmap(roadmap_id)
        if r.status == "completed":
            raise InputValidationError("This roadmap is already completed")
        if r.status == "not_started":
            r.status, r.started_at = "in_progress", datetime.now(UTC)
            self._db.commit()
        return self._out(r)

    def _activity(self, roadmap: LearningRoadmap, activity_id: uuid.UUID) -> LearningActivity:
        a = self._db.scalar(select(LearningActivity).join(LearningModule, LearningActivity.module_id == LearningModule.id)
                            .where(LearningActivity.id == activity_id, LearningModule.roadmap_id == roadmap.id))
        if a is None:
            raise NotFoundError()
        return a

    def set_activity(self, roadmap_id: uuid.UUID, activity_id: uuid.UUID, complete: bool) -> RoadmapOut:
        r = self._roadmap(roadmap_id)
        if r.status == "not_started":
            raise InputValidationError("Start the roadmap before marking activities")
        a = self._activity(r, activity_id)
        if a.kind == "assessment":
            raise InputValidationError("Assessment activities are completed by passing the assessment")
        a.completed_at = datetime.now(UTC) if complete else None
        self._db.flush()
        self._reevaluate(r)
        self._db.commit()
        return self._out(r)

    def _reevaluate(self, r: LearningRoadmap) -> None:
        progress = self._progress(r, self._modules(r.id))
        if progress.criteria_met and r.status == "in_progress":
            r.status, r.completed_at = "completed", datetime.now(UTC)
        elif not progress.criteria_met and r.status == "completed":
            r.status, r.completed_at = "in_progress", None
        touch_portfolio(self._db, r.user_id)  # keep the portfolio in step with roadmap completion

    def on_assessment_passed(self, slug: str) -> int:
        """Complete matching assessment activities in the user's in-progress roadmaps."""
        rows = self._db.scalars(
            select(LearningActivity).join(LearningModule, LearningActivity.module_id == LearningModule.id)
            .join(LearningRoadmap, LearningModule.roadmap_id == LearningRoadmap.id)
            .where(LearningRoadmap.user_id == self._user.id, LearningRoadmap.deleted_at.is_(None),
                   LearningRoadmap.status == "in_progress", LearningActivity.ref == f"assessment:{slug}",
                   LearningActivity.completed_at.is_(None))).all()
        touched = set()
        for a in rows:
            a.completed_at = datetime.now(UTC)
            touched.add(self._db.get(LearningModule, a.module_id).roadmap_id)  # type: ignore[union-attr]
        self._db.flush()
        for rid in touched:
            r = self._db.get(LearningRoadmap, rid)
            if r is not None:
                self._reevaluate(r)
        return len(rows)

    def delete(self, roadmap_id: uuid.UUID) -> None:
        self._roadmap(roadmap_id).deleted_at = datetime.now(UTC)
        self._db.flush()
        touch_portfolio(self._db, self._user.id)
        self._db.commit()

    # ------------------------------------------------------------ dashboard and reports
    def dashboard(self) -> DashboardOut:
        summaries = self.list_roadmaps()
        nxt: list[ActivityOut] = []
        for s in summaries:
            if s.status == "in_progress":
                nxt += self._progress(self._roadmap(s.id), self._modules(s.id)).next_activities[:3]
        attempts = self._db.scalars(select(AssessmentAttempt).where(AssessmentAttempt.user_id == self._user.id)
                                    .order_by(AssessmentAttempt.submitted_at.desc()).limit(5)).all()
        from app.services.assessment_service import attempt_summary

        return DashboardOut(roadmaps=summaries, next_activities=nxt[:8],
                            recent_attempts=[attempt_summary(self._db, a) for a in attempts])

    def report(self, roadmap_id: uuid.UUID, fmt: str) -> uuid.UUID:
        out = self.get(roadmap_id)
        data = render(rb.roadmap_doc(out), fmt)
        return create_report(self._db, self._storage, self._principal, report_type="learning_roadmap",
                             file_format=fmt, data=data, filename=f"learning-roadmap.{fmt}",
                             max_bytes=self._s.max_report_bytes, expires_at=None).id
