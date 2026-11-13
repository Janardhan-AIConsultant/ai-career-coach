"""Career-intelligence orchestration for any principal (guest session or registered user).

Loads the caller's own documents (ownership-checked; foreign ids -> 404), runs the deterministic
engines (via the LangGraph workflow for analysis), persists results, and optionally renders a
PDF/DOCX report. Resume/JD text is never logged.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.career.jd_analysis import analyze_job_description
from app.career.optimization import optimize_resume
from app.career.resume_analysis import analyze_resume
from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.models import CareerAnalysis, JobDescription, Resume, SkillGapAnalysis
from app.schemas.career_api import (
    JobDescriptionAnalyzeOut,
    MatchOut,
    OptimizeOut,
    ResumeAnalyzeOut,
    SkillGapOut,
)
from app.services import report_builders as rb
from app.services.llm import LLMClient
from app.services.object_storage import ObjectStorage
from app.services.principal import Principal
from app.services.report_render import ReportDoc, render
from app.services.report_service import create_report
from app.workflows.career_graph import build_career_graph

logger = logging.getLogger(__name__)


class CareerService:
    def __init__(
        self, db: Session, storage: ObjectStorage, settings: Settings, principal: Principal,
        expires_at: datetime | None, llm: LLMClient | None = None,
    ) -> None:
        self._db, self._storage, self._s = db, storage, settings
        self._p, self._expires, self._llm = principal, expires_at, llm

    # ---- loading (ownership enforced in the query)
    def load_resume(self, document_id: uuid.UUID) -> Resume:
        row = self._db.scalar(select(Resume).where(
            Resume.document_id == document_id, self._p.owns(Resume), Resume.deleted_at.is_(None)))
        if row is None or not row.parsed or "text" not in row.parsed:
            raise NotFoundError("Resume not found")
        return row

    def load_jd(self, document_id: uuid.UUID) -> JobDescription:
        row = self._db.scalar(select(JobDescription).where(
            JobDescription.document_id == document_id, self._p.owns(JobDescription),
            JobDescription.deleted_at.is_(None)))
        if row is None or not row.parsed or "text" not in row.parsed:
            raise NotFoundError("Job description not found")
        return row

    def _report(self, doc: ReportDoc, report_type: str, fmt: str | None, name: str) -> uuid.UUID | None:
        if fmt is None:
            return None
        data = render(doc, fmt)
        return create_report(
            self._db, self._storage, self._p, report_type=report_type, file_format=fmt, data=data,
            filename=f"{name}.{fmt}", max_bytes=self._s.max_report_bytes, expires_at=self._expires,
        ).id

    # ---- 1. resume analysis
    def analyze_resume(self, document_id: uuid.UUID, fmt: str | None) -> ResumeAnalyzeOut:
        row = self.load_resume(document_id)
        analysis = analyze_resume(row.parsed["text"])  # type: ignore[index]
        row.analysis = analysis.model_dump(mode="json")
        self._db.commit()
        rid = self._report(rb.resume_analysis_doc(analysis), "resume_analysis", fmt, "resume-analysis")
        return ResumeAnalyzeOut(analysis=analysis, report_id=rid)

    # ---- 2. job description analysis
    def analyze_jd(self, document_id: uuid.UUID, fmt: str | None) -> JobDescriptionAnalyzeOut:
        row = self.load_jd(document_id)
        analysis = analyze_job_description(row.parsed["text"])  # type: ignore[index]
        row.parsed = {**(row.parsed or {}), "analysis": analysis.model_dump(mode="json")}
        row.title = analysis.title
        self._db.commit()
        rid = self._report(rb.jd_analysis_doc(analysis), "job_description_analysis", fmt, "job-description-analysis")
        return JobDescriptionAnalyzeOut(analysis=analysis, report_id=rid)

    def _run_graph(self, resume_id: uuid.UUID, jd_id: uuid.UUID, *, absent: set[str],
                   narrative: bool) -> tuple[Resume, JobDescription, dict[str, Any]]:
        resume, jd = self.load_resume(resume_id), self.load_jd(jd_id)
        graph = build_career_graph(self._llm)
        state = graph.invoke({
            "resume_text": resume.parsed["text"], "jd_text": jd.parsed["text"],  # type: ignore[index]
            "declared_absent": absent, "include_narrative": narrative,
        })
        return resume, jd, state

    # ---- 3. match
    def match(self, resume_id: uuid.UUID, jd_id: uuid.UUID, fmt: str | None,
              include_narrative: bool) -> MatchOut:
        resume, jd, st = self._run_graph(resume_id, jd_id, absent=set(), narrative=include_narrative)
        result = st["match"]
        self._db.add(CareerAnalysis(
            resume_id=resume.id, job_description_id=jd.id, overall_score=result.overall_score,
            scoring_version=result.scoring_version,
            category_scores={c.category: c.score for c in result.category_scores},
            result=result.model_dump(mode="json"), **self._p.owner_columns))
        self._db.commit()
        rid = self._report(rb.match_doc(result), "career_match", fmt, "career-match")
        return MatchOut(match=result, narrative=st.get("narrative"), report_id=rid)

    # ---- 4. skill gaps
    def skill_gap(self, resume_id: uuid.UUID, jd_id: uuid.UUID, absent: list[str],
                  fmt: str | None) -> SkillGapOut:
        _, _, st = self._run_graph(resume_id, jd_id, absent=set(absent), narrative=False)
        gaps = st["gaps"]
        self._db.add(SkillGapAnalysis(result=gaps.model_dump(mode="json"), **self._p.owner_columns))
        self._db.commit()
        rid = self._report(rb.skill_gap_doc(gaps), "skill_gap", fmt, "skill-gap-analysis")
        return SkillGapOut(analysis=gaps, report_id=rid)

    # ---- 5. optimisation
    def optimize(self, resume_id: uuid.UUID, jd_id: uuid.UUID, *, confirmed: list[str],
                 approved: set[str], declined: set[str], fmt: str | None) -> OptimizeOut:
        resume, _, st = self._run_graph(resume_id, jd_id, absent=set(), narrative=False)
        result = optimize_resume(
            resume.parsed["text"], st["resume"], st["jd"], st["match"],  # type: ignore[index]
            confirmed_skills=confirmed, approved_ids=approved, declined_ids=declined)
        rid = self._report(rb.optimization_doc(result), "resume_optimization", fmt, "resume-optimization")
        file_id = self._report(rb.optimized_resume_doc(result), "resume_optimization", fmt, "optimized-resume")
        return OptimizeOut(result=result, report_id=rid, optimized_resume_report_id=file_id)

