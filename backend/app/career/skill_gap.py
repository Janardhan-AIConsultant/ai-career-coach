"""Technical and leadership skill-gap analysis.

Gaps come from the match result (JD requirement not fully evidenced) plus JD leadership
expectations that the resume does not evidence. A gap is ``not_evidenced`` unless the user told
us they do not have the skill (``declared_absent``), which makes it ``confirmed_absent``.
Suggested timelines use only the platform's supported durations: 7, 15 or 60 days.
Learning content is generic guidance (no invented URLs or course names).
"""

from __future__ import annotations

from typing import Literal

from app.career.taxonomy import LEADERSHIP_CATEGORIES
from app.schemas.career import (
    JobDescriptionAnalysis,
    MatchResult,
    SkillGap,
    SkillGapAnalysis,
    SkillMatch,
)

GROUP_LEARNING: dict[str, tuple[list[str], list[str]]] = {
    "programming_languages": (
        ["Work through the official language tutorial", "Read a well-regarded style guide and idioms reference"],
        ["Re-implement a small project you know in {skill}", "Solve 15 graded practice problems in {skill}"]),
    "backend": (
        ["Follow the official {skill} getting-started guide", "Study its project structure and testing conventions"],
        ["Build a CRUD API with authentication and tests using {skill}"]),
    "frontend": (
        ["Complete the official {skill} tutorial", "Learn component design and state management basics"],
        ["Build a small responsive app with {skill} and a form with validation"]),
    "databases": (
        ["Read the official {skill} documentation on schema design and indexing", "Learn query planning basics"],
        ["Model a small domain in {skill}, add indexes and compare query plans"]),
    "cloud": (
        ["Study the provider's core-services overview for {skill}", "Review the well-architected guidance"],
        ["Deploy a small containerised app using {skill} with infrastructure defined as code"]),
    "microservices": (
        ["Study service boundaries, API contracts and resilience patterns", "Read about {skill} trade-offs"],
        ["Split a monolith sample into two services and add retries and timeouts"]),
    "distributed_systems": (
        ["Study consistency, replication and failure modes", "Read about {skill} in a reputable systems text"],
        ["Write a design note on how a system you know handles partial failure"]),
    "messaging": (
        ["Learn the core concepts of {skill} (topics/queues, delivery guarantees)"],
        ["Build a producer and consumer with {skill} and test redelivery handling"]),
    "ai_genai": (
        ["Complete an introductory course or the official docs for {skill}", "Read about evaluation and failure modes"],
        ["Build a small prototype using {skill} and write down how you evaluated it"]),
    "rag": (
        ["Study chunking, embeddings, retrieval and grounding for {skill}"],
        ["Build a RAG question-answering app over your own documents and measure answer quality"]),
    "vector_databases": (
        ["Read the {skill} documentation on indexing and metadata filtering"],
        ["Index sample documents in {skill} and run filtered similarity queries"]),
    "system_design": (
        ["Study standard system-design building blocks (caching, queues, sharding)"],
        ["Design a URL shortener and a feed service on paper, then review with a peer"]),
    "solution_architecture": (
        ["Learn to write architecture decision records and C4-style diagrams"],
        ["Produce an architecture document for a system you know, including trade-offs"]),
    "devops_tools": (
        ["Follow the official {skill} quick-start"],
        ["Automate build and deploy of a sample app using {skill}"]),
}
LEADERSHIP_LEARNING: dict[str, tuple[list[str], list[str]]] = {
    c: ([f"Read a practical guide on {c.replace('_', ' ')} for engineers",
         "Ask a manager or lead to review how you approach it"],
        [f"Volunteer for a small task that exercises {c.replace('_', ' ')} and record the outcome"])
    for c in LEADERSHIP_CATEGORIES
}

Severity = Literal["critical", "high", "medium", "low"]
_TIMELINE: dict[str, Literal[7, 15, 60]] = {"critical": 60, "high": 15, "medium": 15, "low": 7}


def _severity(m: SkillMatch) -> Severity:
    if m.level == "mandatory":
        return "high" if m.status == "partial" else "critical"
    if m.level == "preferred":
        return "medium" if m.status == "missing" else "low"
    return "low"


def _tech_gap(m: SkillMatch, absent: set[str]) -> SkillGap:
    recs, exercises = GROUP_LEARNING.get(m.group, (["Study the official documentation"], ["Build a small project"]))
    status: Literal["not_evidenced", "confirmed_absent", "partial"] = (
        "confirmed_absent" if m.skill in absent else "partial" if m.status == "partial" else "not_evidenced"
    )
    evidence = (f"Related skill evidenced: {m.related_resume_skill} ({m.resume_evidence})"
                if m.status == "partial" else "No evidence of this skill in the resume")
    sev = _severity(m)
    return SkillGap(
        skill=m.skill, kind="technical", group=m.group, status=status, severity=sev,
        current_evidence=evidence,
        required_competency=f"{m.level.capitalize()} requirement: working knowledge of {m.skill}",
        learning_recommendations=[r.format(skill=m.skill) for r in recs],
        practical_exercises=[e.format(skill=m.skill) for e in exercises],
        suggested_timeline_days=_TIMELINE[sev],
    )


def analyze_skill_gaps(match: MatchResult, jd: JobDescriptionAnalysis,
                       declared_absent: set[str] | None = None) -> SkillGapAnalysis:
    absent = {a.strip().lower() for a in (declared_absent or set())}
    gaps = [_tech_gap(m, absent) for m in [*match.missing_skills, *match.partial_skills]]
    for category, evidenced in match.leadership_match.items():
        if evidenced:
            continue
        recs, exercises = LEADERSHIP_LEARNING[category]
        label = category.replace("_", " ")
        gaps.append(SkillGap(
            skill=label, kind="leadership", group="leadership",
            status="confirmed_absent" if category in absent or label in absent else "not_evidenced",
            severity="high", current_evidence="No evidence of this leadership area in the resume",
            required_competency=f"The job description expects {label}",
            learning_recommendations=recs, practical_exercises=exercises,
            suggested_timeline_days=15,
        ))
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    gaps.sort(key=lambda g: (order[g.severity], g.kind, g.skill))
    tech = sum(g.kind == "technical" for g in gaps)
    lead = len(gaps) - tech
    crit = sum(g.severity == "critical" for g in gaps)
    summary = (f"{tech} technical and {lead} leadership gap(s) identified, {crit} critical."
               if gaps else "No gaps identified against this job description.")
    return SkillGapAnalysis(gaps=gaps, summary=summary)
