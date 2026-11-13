"""Transparent, configurable resume-to-job matching.

Method (every number is reproducible from the inputs; the LLM never produces a score):
1. Each JD skill is weighted by level (mandatory 1.0, preferred 0.5, optional 0.25).
2. A skill is ``matching`` if the resume evidences it; ``partial`` if the resume evidences a
   different skill from the same substitutable group (credit per group in ``partial_credit``,
   e.g. 0.5 for messaging, 0.25 for programming languages); otherwise ``missing``.
3. Category score = earned weight / total weight x 100 for skills of that category. Categories
   the JD does not ask about are excluded and the remaining weights are renormalised.
4. Overall = weighted mean of the applicable category scores using ``ScoringConfig.weights``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.career.taxonomy import PARTIAL_CREDIT, category_of_group
from app.schemas.career import (
    CategoryScore,
    JobDescriptionAnalysis,
    MatchResult,
    ResumeAnalysis,
    SkillMatch,
)

LEVEL_WEIGHT = {"mandatory": 1.0, "preferred": 0.5, "optional": 0.25}
EDU_RANK = {"diploma": 2, "bachelor's": 3, "master's": 4, "doctorate": 5}


@dataclass(frozen=True)
class ScoringConfig:
    weights: dict[str, float] = field(default_factory=lambda: {
        "technical": 0.30, "tools": 0.08, "architecture": 0.12, "leadership": 0.12,
        "experience": 0.14, "domain": 0.05, "projects": 0.07, "education": 0.05,
        "certifications": 0.07,
    })
    partial_credit: dict[str, float] = field(default_factory=lambda: dict(PARTIAL_CREDIT))


def _skill_matches(resume: ResumeAnalysis, jd: JobDescriptionAnalysis,
                   cfg: ScoringConfig) -> list[SkillMatch]:
    have = {s.skill: s for s in [*resume.technical_skills, *resume.tools_and_technologies]}
    by_group: dict[str, list[str]] = {}
    for s in have.values():
        by_group.setdefault(s.group, []).append(s.skill)
    out: list[SkillMatch] = []
    for req in jd.skills:
        if req.skill in have:
            out.append(SkillMatch(skill=req.skill, group=req.group, level=req.level,
                                  status="matching", resume_evidence=have[req.skill].evidence))
        elif by_group.get(req.group) and req.group in cfg.partial_credit:
            related = by_group[req.group][0]
            out.append(SkillMatch(skill=req.skill, group=req.group, level=req.level, status="partial",
                                  related_resume_skill=related, resume_evidence=have[related].evidence))
        else:
            out.append(SkillMatch(skill=req.skill, group=req.group, level=req.level, status="missing"))
    return out


def _skill_category_score(matches: list[SkillMatch], category: str, cfg: ScoringConfig) -> CategoryScore:
    relevant = [m for m in matches if category_of_group(m.group) == category]
    weight = cfg.weights.get(category, 0.0)
    if not relevant:
        return CategoryScore(category=category, score=None, weight=weight,
                             detail="The job description lists no requirements in this category")
    total = earned = 0.0
    for m in relevant:
        w = LEVEL_WEIGHT[m.level]
        total += w
        if m.status == "matching":
            earned += w
        elif m.status == "partial":
            earned += w * cfg.partial_credit.get(m.group, 0.0)
    hits = sum(m.status == "matching" for m in relevant)
    return CategoryScore(category=category, score=round(100 * earned / total, 1), weight=weight,
                         detail=f"{hits} of {len(relevant)} requirements evidenced")


def match(resume: ResumeAnalysis, jd: JobDescriptionAnalysis,
          cfg: ScoringConfig | None = None) -> MatchResult:
    cfg = cfg or ScoringConfig()
    matches = _skill_matches(resume, jd, cfg)
    scores = [_skill_category_score(matches, c, cfg) for c in ("technical", "tools", "architecture")]

    lead_match = {c: c in resume.leadership_skills for c in jd.leadership_expectations}
    if lead_match:
        n = sum(lead_match.values())
        scores.append(CategoryScore(category="leadership", score=round(100 * n / len(lead_match), 1),
                                    weight=cfg.weights["leadership"],
                                    detail=f"{n} of {len(lead_match)} leadership expectations evidenced"))
    else:
        scores.append(CategoryScore(category="leadership", score=None, weight=cfg.weights["leadership"],
                                    detail="The job description lists no leadership expectations"))

    if jd.min_years_experience and resume.years_of_experience is not None:
        ratio = min(1.0, resume.years_of_experience / jd.min_years_experience)
        scores.append(CategoryScore(
            category="experience", score=round(100 * ratio, 1), weight=cfg.weights["experience"],
            detail=f"{resume.years_of_experience:g} years evidenced vs {jd.min_years_experience:g} requested"))
    elif jd.min_years_experience:
        scores.append(CategoryScore(category="experience", score=0.0, weight=cfg.weights["experience"],
                                    detail="Years of experience could not be determined from the resume"))
    else:
        scores.append(CategoryScore(category="experience", score=None, weight=cfg.weights["experience"],
                                    detail="No minimum experience stated"))

    if jd.domain_knowledge:
        hit = [d for d in jd.domain_knowledge if d in resume.domains]
        scores.append(CategoryScore(category="domain", score=round(100 * len(hit) / len(jd.domain_knowledge), 1),
                                    weight=cfg.weights["domain"],
                                    detail=f"{len(hit)} of {len(jd.domain_knowledge)} domains evidenced"))
    else:
        scores.append(CategoryScore(category="domain", score=None, weight=cfg.weights["domain"],
                                    detail="No domain requirement stated"))

    mandatory = [m for m in matches if m.level == "mandatory"]
    if mandatory and resume.projects:
        proj_text = " ".join(resume.projects).lower()
        used = [m for m in mandatory if m.skill in proj_text or (m.related_resume_skill or "") in proj_text]
        scores.append(CategoryScore(category="projects", score=round(100 * len(used) / len(mandatory), 1),
                                    weight=cfg.weights["projects"],
                                    detail=f"{len(used)} of {len(mandatory)} mandatory skills appear in projects"))
    elif mandatory:
        scores.append(CategoryScore(category="projects", score=None, weight=cfg.weights["projects"],
                                    detail="No projects section detected, so project relevance was not scored"))
    else:
        scores.append(CategoryScore(category="projects", score=None, weight=cfg.weights["projects"],
                                    detail="No mandatory skills to compare against projects"))

    if jd.required_education_level:
        need = EDU_RANK.get(jd.required_education_level, 0)
        have = EDU_RANK.get(resume.highest_education_level or "", 0)
        scores.append(CategoryScore(category="education", score=100.0 if have >= need else 0.0,
                                    weight=cfg.weights["education"],
                                    detail=f"Requires {jd.required_education_level}; resume shows "
                                           f"{resume.highest_education_level or 'no detected degree'}"))
    else:
        scores.append(CategoryScore(category="education", score=None, weight=cfg.weights["education"],
                                    detail="No education requirement stated"))

    if jd.certifications:
        res_certs = " ".join(resume.certifications).lower()
        hit = [c for c in jd.certifications if c.lower() in res_certs]
        scores.append(CategoryScore(category="certifications", score=round(100 * len(hit) / len(jd.certifications), 1),
                                    weight=cfg.weights["certifications"],
                                    detail=f"{len(hit)} of {len(jd.certifications)} certifications evidenced"))
    else:
        scores.append(CategoryScore(category="certifications", score=None, weight=cfg.weights["certifications"],
                                    detail="No certification requirement stated"))

    applicable = [s for s in scores if s.score is not None and s.weight > 0]
    total_w = sum(s.weight for s in applicable)
    overall = round(sum((s.score or 0) * s.weight for s in applicable) / total_w, 1) if total_w else 0.0

    missing = [m for m in matches if m.status == "missing"]
    partial = [m for m in matches if m.status == "partial"]
    recs: list[str] = []
    for m in missing:
        if m.level == "mandatory":
            recs.append(f"Mandatory skill '{m.skill}' is not evidenced in your resume - add it only if you truly have it, otherwise plan to learn it")
    for m in partial[:3]:
        recs.append(f"You show '{m.related_resume_skill}' but the job asks for '{m.skill}' - highlight any transferable experience")
    for c, ok in lead_match.items():
        if not ok:
            recs.append(f"Leadership area '{c.replace('_', ' ')}' is expected but not evidenced - add a concrete example if you have one")
    if not recs:
        recs.append("Your resume evidences the listed requirements well; focus on quantifying achievements")

    return MatchResult(
        overall_score=overall, category_scores=scores,
        matching_skills=[m for m in matches if m.status == "matching"],
        partial_skills=partial, missing_skills=missing, leadership_match=lead_match,
        recommendations=recs[:10], weights=cfg.weights,
    )
