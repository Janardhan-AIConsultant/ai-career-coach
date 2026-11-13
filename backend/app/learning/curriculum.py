"""Roadmap generation. SUPPORTED DURATIONS: 7, 15 and 60 days only (see ``core.constants``).

Deterministic planner: focus items (skills / leadership areas) become modules; days are split
among modules; each day gets learn / exercise tasks, each module ends with an assessment (when an
authored assessment exists for it) or a review, and 15/60-day plans end with a capstone project.
Learning content reuses the generic guidance of the skill-gap engine (no invented URLs).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.assessments.bank import SKILL_ASSESSMENTS
from app.career.skill_gap import GROUP_LEARNING, LEADERSHIP_LEARNING
from app.core.constants import ROADMAP_DURATIONS
from app.core.exceptions import InputValidationError

FOCUS_LIMIT = {7: 3, 15: 5, 60: 10}
CAPSTONE_DAYS = {7: 0, 15: 2, 60: 7}
MINUTES = {"learn": 45, "exercise": 60, "assessment": 30, "review": 30, "project": 90}
COMPLETION_PERCENT = 80

GROUP_TOPICS: dict[str, list[str]] = {
    "programming_languages": ["Syntax, types and tooling", "Core data structures and idioms", "Error handling and testing", "Packaging and style", "Concurrency basics", "Performance and profiling"],
    "backend": ["Project structure and routing", "Validation and serialization", "Authentication and authorization", "Persistence and transactions", "Testing", "Deployment and observability"],
    "frontend": ["Components and props", "State and effects", "Forms and validation", "Data fetching and caching", "Testing and accessibility", "Build and performance"],
    "databases": ["Data modelling", "Indexes and query plans", "Transactions and isolation", "Migrations", "Backup, replication and scaling"],
    "cloud": ["Core services and identity", "Networking and security", "Compute and storage", "Infrastructure as code", "Monitoring and cost"],
    "microservices": ["Service boundaries", "Synchronous vs asynchronous communication", "Data ownership and consistency", "Resilience patterns", "Observability and deployment"],
    "distributed_systems": ["Consistency models and CAP", "Replication and partitioning", "Failure modes and retries", "Idempotency and ordering", "Consensus and coordination basics"],
    "messaging": ["Core concepts", "Producers and consumers", "Delivery guarantees and idempotency", "Failure handling and dead letters", "Monitoring and scaling"],
    "ai_genai": ["Fundamentals and terminology", "Prompting and structured output", "Building a small prototype", "Evaluation and failure modes", "Cost, latency and safety"],
    "rag": ["Document ingestion and chunking", "Embeddings and vector search", "Retrieval quality (hybrid, reranking)", "Grounding and citations", "Evaluation and tenant isolation"],
    "vector_databases": ["Embeddings and distance metrics", "Indexing (HNSW) and recall", "Metadata filtering and isolation", "Operations and migration"],
    "system_design": ["Requirements and estimation", "Core building blocks", "Storage and partitioning", "Caching and queues", "Reliability and trade-offs"],
    "solution_architecture": ["Quality attributes and drivers", "Documentation (C4, ADRs)", "Integration patterns", "Security and compliance", "Governance and trade-offs"],
    "devops_tools": ["Concepts and installation", "Configuration and automation", "Pipelines and delivery", "Security and secrets", "Monitoring and troubleshooting"],
    "leadership": ["Why it matters and common failure modes", "Frameworks and practices", "Applying it to a real situation", "Feedback and reflection"],
}


@dataclass(frozen=True)
class FocusItem:
    key: str  # canonical skill or leadership category
    group: str  # taxonomy group or "leadership"
    reason: str


@dataclass
class ActivityPlan:
    day: int
    title: str
    kind: str
    description: str
    resources: list[str]
    ref: str | None = None
    required: bool = True

    @property
    def minutes(self) -> int:
        return MINUTES[self.kind]


@dataclass
class ModulePlan:
    title: str
    objectives: list[str]
    topics: list[str]
    activities: list[ActivityPlan] = field(default_factory=list)


@dataclass
class RoadmapPlan:
    title: str
    duration_days: int
    modules: list[ModulePlan]
    completion_criteria: dict[str, object]

    @property
    def estimated_hours(self) -> float:
        return round(sum(a.minutes for m in self.modules for a in m.activities) / 60, 1)


def validate_duration(days: int) -> int:
    if days not in ROADMAP_DURATIONS:
        raise InputValidationError("Roadmap duration must be one of: 7, 15 or 60 days")
    return days


def _label(key: str) -> str:
    return key.replace("_", " ")


def _content(item: FocusItem) -> tuple[list[str], list[str]]:
    if item.group == "leadership":
        return LEADERSHIP_LEARNING.get(item.key, ([], []))
    recs, exercises = GROUP_LEARNING.get(item.group, (["Study the official documentation"], ["Build a small project"]))
    return [r.format(skill=item.key) for r in recs], [e.format(skill=item.key) for e in exercises]


def _module(item: FocusItem, days: int, first_day: int) -> ModulePlan:
    label = _label(item.key)
    topics = GROUP_TOPICS.get(item.group, GROUP_TOPICS["leadership"])
    recs, exercises = _content(item)
    exercises = exercises or [f"Apply {label} in a small hands-on task"]
    assess = SKILL_ASSESSMENTS.get(item.key)
    mod = ModulePlan(
        title=label.title(),
        objectives=[item.reason, f"Explain the core ideas of {label} in your own words",
                    f"Complete a practical exercise using {label}"],
        topics=topics[: max(days, 1)] if days < len(topics) else topics,
    )
    for d in range(1, days + 1):
        day = first_day + d - 1
        if d <= len(topics):
            mod.activities.append(ActivityPlan(
                day, f"Learn: {topics[d - 1]} ({label})", "learn",
                f"Study '{topics[d - 1]}' for {label}. Take notes and write 3 questions you could be asked.",
                [*recs, f"Official {label} documentation"]))
        if d % 2 == 0 or d == days or d > len(topics):
            ex = exercises[(d - 1) % len(exercises)]
            mod.activities.append(ActivityPlan(day, f"Practice: {ex}", "exercise",
                                               f"Hands-on task: {ex}. Keep your work for the portfolio.",
                                               [f"Your notes from earlier {label} lessons"]))
        if d == days:
            if assess:
                mod.activities.append(ActivityPlan(
                    day, f"Assessment: {label}", "assessment",
                    "Pass the platform assessment (completes automatically when you pass).", [], ref=f"assessment:{assess}"))
            else:
                mod.activities.append(ActivityPlan(
                    day, f"Review: {label}", "review",
                    f"Self-review: list what you can now do with {label}, what is still unclear and one next step.", []))
    return mod


def build_roadmap(duration_days: int, goal: str, focus: list[FocusItem]) -> RoadmapPlan:
    validate_duration(duration_days)
    if not focus:
        raise InputValidationError("Provide a goal that mentions skills, documents to analyse, or focus skills")
    focus = focus[: FOCUS_LIMIT[duration_days]]
    capstone = CAPSTONE_DAYS[duration_days]
    learn_days = duration_days - capstone
    k = min(len(focus), learn_days)
    focus = focus[:k]
    base, rem = divmod(learn_days, k)
    modules: list[ModulePlan] = []
    day = 1
    for i, item in enumerate(focus):
        n = base + (1 if i < rem else 0)
        modules.append(_module(item, n, day))
        day += n
    if capstone:
        names = ", ".join(_label(f.key) for f in focus[:3])
        cap = ModulePlan("Capstone project", [f"Combine {names} in one small project", "Document and present your work"],
                         ["Plan and scope", "Build", "Test and document", "Present"])
        for j in range(capstone):
            d = day + j
            if j == 0:
                t, desc = "Capstone: define scope", f"Define a small project that uses {names}; write requirements and milestones."
            elif j == capstone - 1:
                t, desc = "Capstone: finish, document and reflect", "Finish the project, write a README, record what you learned and add it to your portfolio notes."
            else:
                t, desc = f"Capstone: build milestone {j}", "Implement the next milestone, test it, and commit your work."
            cap.activities.append(ActivityPlan(d, t, "project", desc, ["Your own repository and notes"]))
        modules.append(cap)
    refs = sorted({a.ref for m in modules for a in m.activities if a.ref})
    plan = RoadmapPlan(
        title=f"{duration_days}-day roadmap: " + ", ".join(_label(f.key) for f in focus[:3]),
        duration_days=duration_days, modules=modules,
        completion_criteria={
            "min_required_activity_percent": COMPLETION_PERCENT,
            "assessments_must_be_passed": refs,
            "description": (f"Complete at least {COMPLETION_PERCENT}% of required activities and pass every "
                            "assessment in the plan. Assessment activities complete only by passing, "
                            "so the roadmap cannot be finished by clicking alone."),
        },
    )
    return plan
