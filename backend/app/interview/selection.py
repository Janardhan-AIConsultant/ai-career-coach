"""Personalised question selection from the curated bank (deterministic, no LLM).

Priority for technical/architecture topics: JD-required skills the resume does not evidence
(practise these), then JD-required skills the resume does evidence (prove depth), then preferred
skills, then resume skills, then everything else. Leadership/management questions are prioritised
when the JD expects team or technical leadership.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.interview.bank import INTERVIEW_KINDS, QUESTIONS, Question
from app.schemas.career import JobDescriptionAnalysis, ResumeAnalysis

SKILL_TO_TOPIC = {
    "java": "java", "spring boot": "spring_boot", "react": "react", "typescript": "typescript",
    "python": "python", "fastapi": "fastapi", "aws": "aws", "kafka": "kafka", "postgresql": "postgresql",
    "microservices": "microservices", "distributed systems": "distributed_systems",
    "event-driven architecture": "distributed_systems", "generative ai": "generative_ai", "llm": "generative_ai",
    "rag": "rag", "langchain": "langchain", "langgraph": "langgraph", "chromadb": "chromadb",
    "vector databases": "chromadb", "prompt engineering": "prompt_engineering",
    "system design": "system_design", "solution architecture": "solution_architecture",
}
_LEADERSHIP_JD = {"team_management", "technical_leadership", "engineering_management", "mentoring"}
_DIFFICULTY = {"beginner": 0, "intermediate": 1, "advanced": 2}


@dataclass(frozen=True)
class Selected:
    question: Question
    reason: str


def _topic_priorities(resume: ResumeAnalysis | None, jd: JobDescriptionAnalysis | None) -> dict[str, tuple[int, str]]:
    prio: dict[str, tuple[int, str]] = {}
    have = {s.skill for s in [*(resume.technical_skills if resume else []),
                              *(resume.tools_and_technologies if resume else [])]}

    def put(topic: str, rank: int, reason: str) -> None:
        if topic not in prio or rank < prio[topic][0]:
            prio[topic] = (rank, reason)

    if jd:
        for req in jd.skills:
            topic = SKILL_TO_TOPIC.get(req.skill)
            if not topic:
                continue
            if req.level == "mandatory" and req.skill not in have:
                put(topic, 0, f"The job requires {req.skill} and your resume does not evidence it - practise this")
            elif req.level == "mandatory":
                put(topic, 1, f"The job requires {req.skill}; expect depth questions")
            elif req.level == "preferred":
                put(topic, 2, f"{req.skill} is a preferred skill for the job")
    for skill in have:
        topic = SKILL_TO_TOPIC.get(skill)
        if topic:
            put(topic, 3, f"{skill} is on your resume, so you may be asked about it")
    return prio


def select_questions(
    kinds: list[str], *, resume: ResumeAnalysis | None = None, jd: JobDescriptionAnalysis | None = None,
    topics: list[str] | None = None, count: int = 15,
) -> list[Selected]:
    kinds = [k for k in INTERVIEW_KINDS if k in set(kinds)]  # allowlist, stable order
    prio = _topic_priorities(resume, jd)
    lead_jd = bool(jd and _LEADERSHIP_JD & set(jd.leadership_expectations))
    wanted_topics = set(topics or [])

    def key(q: Question) -> tuple[int, int, str]:
        if q.topic in prio:
            rank, _ = prio[q.topic]
        elif q.kind in ("engineering_leadership", "engineering_management") and lead_jd:
            rank = 1
        else:
            rank = 5
        if wanted_topics and q.topic in wanted_topics:
            rank = -1
        return (rank, _DIFFICULTY[q.difficulty], q.id)

    def reason(q: Question) -> str:
        if wanted_topics and q.topic in wanted_topics:
            return "You asked to practise this topic"
        if q.topic in prio:
            return prio[q.topic][1]
        if q.kind in ("engineering_leadership", "engineering_management") and lead_jd:
            return "The job expects leadership responsibilities"
        return "Common interview question for this category"

    per_kind = {k: sorted((q for q in QUESTIONS if q.kind == k), key=key) for k in kinds}
    if wanted_topics:  # restrict topic-based kinds; behavioural/scenario/hr/leadership are unaffected
        topical = {"technical", "architecture", "system_design"}
        per_kind = {k: [q for q in qs if k not in topical or q.topic in wanted_topics]
                    for k, qs in per_kind.items()}
    chosen: list[Selected] = []
    index = 0
    while len(chosen) < count and any(index < len(v) for v in per_kind.values()):
        for k in kinds:  # round-robin so every requested kind is represented
            if index < len(per_kind[k]) and len(chosen) < count:
                q = per_kind[k][index]
                chosen.append(Selected(q, reason(q)))
        index += 1
    return chosen
