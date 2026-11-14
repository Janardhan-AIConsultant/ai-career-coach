"""Deterministic job-description analysis.

Skill level rules (highest wins when a skill appears several times):
* ``mandatory``: under a required/qualifications/responsibilities heading, or on a line with
  required/must/essential/mandatory cues.
* ``preferred``: under a preferred/nice-to-have heading, or a line with preferred/bonus/plus cues.
* ``optional``: mentioned elsewhere without any cue (e.g. company description).
"""

from __future__ import annotations

import re

from app.career.taxonomy import (
    ARCHITECTURE_GROUPS,
    CERTIFICATIONS,
    DOMAINS,
    EDUCATION_LEVELS,
    leadership_patterns,
    skill_patterns,
)
from app.career.text_utils import BULLET
from app.schemas.career import JobDescriptionAnalysis, JobRequirement

_REQUIRED_HEAD = re.compile(
    r"^(required|requirements?|must[- ]have|mandatory|essential|qualifications?|what you('|’)ll need|"
    r"what we('|’)re looking for|key skills|skills required|required skills|minimum qualifications?)\b", re.IGNORECASE)
_PREFERRED_HEAD = re.compile(
    r"^(preferred|nice[- ]to[- ]have|bonus|good[- ]to[- ]have|desirable|plus|preferred (skills|qualifications))\b", re.IGNORECASE)
_RESP_HEAD = re.compile(
    r"^(responsibilities|key responsibilities|what you('|’)ll do|duties|the role|role overview|your role)\b", re.IGNORECASE)
_OTHER_HEAD = re.compile(r"^(about|benefits|what we offer|why join|our company|company|perks)\b", re.IGNORECASE)
_PREFERRED_CUE = re.compile(r"\b(preferred|nice to have|bonus|a plus|good to have|desirable|advantage)\b", re.IGNORECASE)
_REQUIRED_CUE = re.compile(r"\b(required|must|mandatory|essential)\b", re.IGNORECASE)
_SOFT_CUE = re.compile(r"\b(proficien\w+|strong|expert\w*|hands-on)\b", re.IGNORECASE)
_OPTIONAL_CUE = re.compile(r"\boptional\b", re.IGNORECASE)
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)", re.IGNORECASE)
_RANK = {"mandatory": 3, "preferred": 2, "optional": 1}


def _heading_kind(line: str) -> str | None:
    s = re.sub(r"[:\-–—*#\s]+$", "", line.strip())
    s = re.sub(r"^[#*\s]+", "", s)
    if not s or len(s) > 60 or BULLET.match(line):
        return None
    for kind, rx in (("preferred", _PREFERRED_HEAD), ("mandatory", _REQUIRED_HEAD),
                     ("responsibilities", _RESP_HEAD), ("other", _OTHER_HEAD)):
        if rx.match(s):
            return kind
    return None


def _first(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip(" -:|,")[:120]
    return None


def analyze_job_description(text: str) -> JobDescriptionAnalysis:
    lines = [ln.rstrip() for ln in text.splitlines()]
    nonempty = [ln.strip() for ln in lines if ln.strip()]

    title = _first([r"^\s*(?:job title|title|role|position)\s*[:\-]\s*(.+)$"], text) or (
        nonempty[0][:120] if nonempty and len(nonempty[0]) < 80 and ":" not in nonempty[0] else None)
    company = _first([r"^\s*company\s*[:\-]\s*(.+)$", r"\bat\s+([A-Z][\w&.\- ]{2,40})(?:[,.\n]|$)"], text)

    section = "other"
    levels: dict[str, str] = {}
    responsibilities: list[str] = []
    education_lines: list[str] = []
    comm_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        kind = _heading_kind(stripped)
        if kind:
            section = kind
            continue
        if section == "responsibilities" and (BULLET.match(line) or len(stripped) > 15):
            responsibilities.append(BULLET.sub("", stripped)[:300])
        if re.search(r"degree|bachelor|master|ph\.?d|b\.?tech|m\.?tech|diploma|\bmba\b", stripped, re.IGNORECASE):
            education_lines.append(BULLET.sub("", stripped)[:200])
        if re.search(r"communicat|stakeholder|present(ation)?s?\b|collaborat", stripped, re.IGNORECASE):
            comm_lines.append(BULLET.sub("", stripped)[:200])
        if _PREFERRED_CUE.search(stripped):
            line_level = "preferred"
        elif _OPTIONAL_CUE.search(stripped):
            line_level = "optional"
        elif _REQUIRED_CUE.search(stripped) or section in ("mandatory", "responsibilities"):
            line_level = "mandatory"
        elif section == "preferred":
            line_level = "preferred"
        elif _SOFT_CUE.search(stripped):
            line_level = "mandatory"
        else:
            line_level = "optional"
        for canonical, (_g, rx) in skill_patterns().items():
            if rx.search(stripped) and _RANK[line_level] > _RANK.get(levels.get(canonical, ""), 0):
                levels[canonical] = line_level

    reqs = [
        JobRequirement(skill=s, group=skill_patterns()[s][0], level=lv)
        for s, lv in levels.items()
    ]
    reqs.sort(key=lambda r: (-_RANK[r.level], r.group, r.skill))

    tech: dict[str, list[str]] = {}
    for r in reqs:
        tech.setdefault(r.group, []).append(r.skill)

    years = [int(n) for n in _YEARS.findall(text) if 0 < int(n) <= 40]
    best_level = None
    for label, (rank, pattern) in EDUCATION_LEVELS.items():
        if re.search(pattern, "\n".join(education_lines), re.IGNORECASE) and (
            best_level is None or rank < best_level[0]
        ):
            best_level = (rank, label)  # the *minimum* level the JD mentions

    leadership = [c for c, pats in leadership_patterns().items() if any(p.search(text) for p in pats)]
    certs = sorted({m.group(0).strip().title() for pat in CERTIFICATIONS.values()
                    for m in re.finditer(pat, text, re.IGNORECASE)})
    domains = sorted({d for d in DOMAINS if re.search(rf"\b{re.escape(d)}\b", text, re.IGNORECASE)})
    arch_lines = [BULLET.sub("", ln.strip())[:200] for ln in lines
                  if re.search(r"architect|system design|design pattern", ln, re.IGNORECASE)][:6]

    return JobDescriptionAnalysis(
        title=title, company=company,
        min_years_experience=float(min(years)) if years else None,
        skills=reqs,
        mandatory_skills=[r.skill for r in reqs if r.level == "mandatory"],
        preferred_skills=[r.skill for r in reqs if r.level == "preferred"],
        optional_skills=[r.skill for r in reqs if r.level == "optional"],
        responsibilities=responsibilities[:15], education_requirements=list(dict.fromkeys(education_lines))[:5],
        required_education_level=best_level[1] if best_level else None,
        leadership_expectations=leadership, technical_requirements=tech,
        architecture_requirements=list(dict.fromkeys(
            [r.skill for r in reqs if r.group in ARCHITECTURE_GROUPS] + arch_lines))[:10],
        domain_knowledge=domains, certifications=certs,
        communication_expectations=list(dict.fromkeys(comm_lines))[:5],
    )
