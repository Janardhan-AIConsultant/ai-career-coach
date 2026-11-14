"""Result models for career intelligence (also the JSON persisted in the database)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCORE_DISCLAIMER = (
    "This score is an application-generated estimate based on keyword and evidence matching. "
    "It is not an official ATS score and does not predict or guarantee selection."
)
SCORING_VERSION = "v1"


class SkillEvidence(BaseModel):
    skill: str
    group: str
    evidence: str  # short excerpt from the resume that mentions the skill


class EmploymentEntry(BaseModel):
    heading: str
    start_year: int | None = None
    end_year: int | None = None
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list)


class ResumeQuality(BaseModel):
    score: int  # 0-100 heuristic completeness/clarity estimate
    breakdown: dict[str, int]
    note: str = "Heuristic estimate of resume completeness and clarity, not an ATS score."


class ResumeAnalysis(BaseModel):
    word_count: int
    sections_found: list[str]
    technical_skills: list[SkillEvidence]
    tools_and_technologies: list[SkillEvidence]
    leadership_skills: dict[str, str]  # category -> evidence excerpt
    skill_categories: dict[str, list[str]]  # group -> skills
    employment: list[EmploymentEntry]
    years_of_experience: float | None
    years_source: Literal["employment_dates", "stated", "unknown"]
    education: list[str]
    highest_education_level: str | None
    projects: list[str]
    certifications: list[str]
    achievements: list[str]
    domains: list[str]
    contact_present: dict[str, bool]  # booleans only; contact details are never stored in results
    experience_summary: str
    quality: ResumeQuality
    strengths: list[str]
    weaknesses: list[str]
    missing_information: list[str]
    ats_recommendations: list[str]


class JobRequirement(BaseModel):
    skill: str
    group: str
    level: Literal["mandatory", "preferred", "optional"]


class JobDescriptionAnalysis(BaseModel):
    title: str | None
    company: str | None
    min_years_experience: float | None
    skills: list[JobRequirement]
    mandatory_skills: list[str]
    preferred_skills: list[str]
    optional_skills: list[str]
    responsibilities: list[str]
    education_requirements: list[str]
    required_education_level: str | None
    leadership_expectations: list[str]  # leadership categories
    technical_requirements: dict[str, list[str]]  # group -> skills
    architecture_requirements: list[str]
    domain_knowledge: list[str]
    certifications: list[str]
    communication_expectations: list[str]


class SkillMatch(BaseModel):
    skill: str
    group: str
    level: Literal["mandatory", "preferred", "optional"]
    status: Literal["matching", "partial", "missing"]
    resume_evidence: str | None = None
    related_resume_skill: str | None = None  # for partial matches


class CategoryScore(BaseModel):
    category: str
    score: float | None  # None when the job description has no requirements in this category
    weight: float
    detail: str


class MatchResult(BaseModel):
    overall_score: float
    category_scores: list[CategoryScore]
    matching_skills: list[SkillMatch]
    partial_skills: list[SkillMatch]
    missing_skills: list[SkillMatch]
    leadership_match: dict[str, bool]  # JD leadership category -> evidenced in resume
    recommendations: list[str]
    scoring_version: str = SCORING_VERSION
    weights: dict[str, float]
    disclaimer: str = SCORE_DISCLAIMER


class SkillGap(BaseModel):
    skill: str
    kind: Literal["technical", "leadership"]
    group: str
    status: Literal["not_evidenced", "confirmed_absent", "partial"]
    severity: Literal["critical", "high", "medium", "low"]
    current_evidence: str
    required_competency: str
    learning_recommendations: list[str]
    practical_exercises: list[str]
    suggested_timeline_days: Literal[7, 15, 60]


class SkillGapAnalysis(BaseModel):
    gaps: list[SkillGap]
    summary: str
    note: str = (
        "'not_evidenced' means the resume does not show the skill (you may still have it); "
        "'confirmed_absent' means you told us you do not have it."
    )


class Change(BaseModel):
    id: str
    section: str
    change_type: Literal["minor", "significant"]
    before: str
    after: str
    reason: str
    applied: bool  # whether it is included in the optimised resume text


class OptimizationResult(BaseModel):
    optimized_resume_text: str
    changes: list[Change]
    keyword_recommendations: dict[str, list[str]]
    needs_confirmation: list[str]  # JD skills that may be added only if the user confirms them
    clarification_questions: list[str]
    pending_approval_ids: list[str]
    note: str = (
        "Only facts already in your resume (or skills you explicitly confirmed) are used. "
        "Significant changes are applied only after you approve them."
    )
