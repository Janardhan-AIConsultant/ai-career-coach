"""LangGraph workflow for career analysis (resume + JD -> match -> gaps -> optional narrative).

LangGraph is used here because the flow is multi-step with a conditional branch (the LLM-written
narrative only runs when requested and an LLM is configured). All scores and extractions come from
deterministic code; the narrative node receives *structured facts only* (never raw resume text),
so instructions hidden in a document cannot reach the model, and a narrative failure degrades to
``None`` instead of failing the analysis.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.career.jd_analysis import analyze_job_description
from app.career.matching import ScoringConfig, match
from app.career.resume_analysis import analyze_resume
from app.career.skill_gap import analyze_skill_gaps
from app.core.exceptions import AppError
from app.guardrails.prompt_safety import CANARY
from app.schemas.career import (
    JobDescriptionAnalysis,
    MatchResult,
    ResumeAnalysis,
    SkillGapAnalysis,
)
from app.services.llm import LLMClient

logger = logging.getLogger(__name__)

NARRATIVE_SYSTEM = (
    "You are a career coach. Write 3-5 plain sentences summarising the candidate's fit for the role "
    "using ONLY the facts provided. Do not add skills, employers, numbers or claims that are not in "
    "the facts. Do not give guarantees about hiring outcomes. [" + CANARY + "]"
)


class CareerState(TypedDict, total=False):
    resume_text: str
    jd_text: str
    declared_absent: set[str]
    include_narrative: bool
    resume: ResumeAnalysis
    jd: JobDescriptionAnalysis
    match: MatchResult
    gaps: SkillGapAnalysis
    narrative: str | None


def _facts(state: CareerState) -> str:
    m, g = state["match"], state["gaps"]
    return (
        f"Estimated match score: {m.overall_score}/100 (application estimate, not an ATS score)\n"
        f"Role: {state['jd'].title or 'unspecified'}\n"
        f"Evidenced matching skills: {', '.join(s.skill for s in m.matching_skills) or 'none'}\n"
        f"Missing mandatory skills: {', '.join(s.skill for s in m.missing_skills if s.level == 'mandatory') or 'none'}\n"
        f"Top gaps: {', '.join(x.skill for x in g.gaps[:5]) or 'none'}"
    )


def build_career_graph(llm: LLMClient | None, config: ScoringConfig | None = None):  # type: ignore[no-untyped-def]
    def n_resume(s: CareerState) -> CareerState:
        return {"resume": analyze_resume(s["resume_text"])}

    def n_jd(s: CareerState) -> CareerState:
        return {"jd": analyze_job_description(s["jd_text"])}

    def n_match(s: CareerState) -> CareerState:
        return {"match": match(s["resume"], s["jd"], config)}

    def n_gaps(s: CareerState) -> CareerState:
        return {"gaps": analyze_skill_gaps(s["match"], s["jd"], s.get("declared_absent"))}

    def n_narrative(s: CareerState) -> CareerState:
        assert llm is not None
        try:
            text = llm.invoke(NARRATIVE_SYSTEM, _facts(s)).strip()
        except AppError:
            logger.warning("narrative generation failed; continuing without it")
            return {"narrative": None}
        if not text or CANARY in text or len(text) > 1500:
            return {"narrative": None}
        return {"narrative": text}

    def route(s: CareerState) -> str:
        return "narrative" if llm is not None and s.get("include_narrative") else END

    g = StateGraph(CareerState)

    def add(name: str, fn: Callable[[CareerState], CareerState]) -> None:
        g.add_node(name, fn)  # type: ignore[call-overload]

    add("resume", n_resume)
    add("jd", n_jd)
    add("match", n_match)
    add("gaps", n_gaps)
    add("narrative", n_narrative)
    g.add_edge(START, "resume")
    g.add_edge("resume", "jd")
    g.add_edge("jd", "match")
    g.add_edge("match", "gaps")
    g.add_conditional_edges("gaps", route, {"narrative": "narrative", END: END})
    g.add_edge("narrative", END)
    return g.compile()
