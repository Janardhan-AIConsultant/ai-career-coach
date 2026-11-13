"""Deterministic resume analysis.

Everything reported is *detected in the resume text*: skills via the taxonomy, dates via regex,
leadership via phrase patterns. Nothing is inferred or invented, so a prompt-injected resume
cannot add skills it does not literally state. ``contact_present`` holds booleans only.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.career.taxonomy import (
    CERTIFICATIONS,
    DOMAINS,
    EDUCATION_LEVELS,
    TOOL_GROUPS,
    leadership_patterns,
    skill_patterns,
)
from app.career.text_utils import (
    BULLET,
    RANGE,
    bullets_of,
    evidence_snippet,
    heading_of,
    split_sections,
    years_from_ranges,
)
from app.schemas.career import (
    EmploymentEntry,
    ResumeAnalysis,
    ResumeQuality,
    SkillEvidence,
)

ACTION_VERBS = {
    "achieved", "architected", "automated", "built", "championed", "coached", "collaborated",
    "created", "delivered", "deployed", "designed", "developed", "drove", "enabled", "engineered",
    "established", "executed", "implemented", "improved", "increased", "integrated", "introduced",
    "launched", "led", "managed", "mentored", "migrated", "modernized", "optimized", "orchestrated",
    "owned", "partnered", "reduced", "refactored", "resolved", "scaled", "shipped", "simplified",
    "spearheaded", "streamlined", "supervised", "tested", "transformed", "trained", "upgraded",
    "analyzed", "analysed", "authored", "conducted", "coordinated", "directed", "evaluated",
    "generated", "guided", "maintained", "negotiated", "planned", "presented", "researched",
}
WEAK_START = re.compile(
    r"^(responsible for|worked on|worked with|helped( with| to)?|assisted( with| in)?|"
    r"duties included|involved in|tasked with|participated in)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d|%|\$")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)\+?\d[\d\s().-]{8,}\d(?!\d)")
_STATED_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
_PRESENT = {"present", "current", "now", "till date"}


def _employment(text: str) -> list[EmploymentEntry]:
    entries: list[EmploymentEntry] = []
    current: EmploymentEntry | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = RANGE.search(line)
        if m and not BULLET.match(line) and len(line) < 160:
            end = m.group(2).lower()
            current = EmploymentEntry(
                heading=line[:160], start_year=int(m.group(1)),
                end_year=None if end in _PRESENT else int(end), is_current=end in _PRESENT,
            )
            entries.append(current)
        elif current is not None and heading_of(line) is None:
            current.bullets.append(BULLET.sub("", line)[:300])
    return entries


def _highest_education(edu_text: str) -> tuple[str | None, list[str]]:
    lines = [ln.strip() for ln in edu_text.splitlines() if ln.strip()][:6]
    best: tuple[int, str] | None = None
    for label, (rank, pattern) in EDUCATION_LEVELS.items():
        if re.search(pattern, edu_text, re.IGNORECASE) and (best is None or rank > best[0]):
            best = (rank, label)
    return (best[1] if best else None), lines


def analyze_resume(text: str, now: datetime | None = None) -> ResumeAnalysis:
    sections = split_sections(text)
    words = len(text.split())

    technical: list[SkillEvidence] = []
    tools: list[SkillEvidence] = []
    categories: dict[str, list[str]] = {}
    for canonical, (group, rx) in skill_patterns().items():
        m = rx.search(text)
        if not m:
            continue
        item = SkillEvidence(skill=canonical, group=group, evidence=evidence_snippet(text, m))
        (tools if group in TOOL_GROUPS else technical).append(item)
        categories.setdefault(group, []).append(canonical)

    leadership: dict[str, str] = {}
    for category, patterns in leadership_patterns().items():
        for rx in patterns:
            m = rx.search(text)
            if m:
                leadership[category] = evidence_snippet(text, m)
                break

    exp_text = sections.get("experience", text)
    employment = _employment(exp_text)
    years = years_from_ranges(exp_text, now)
    years_source = "employment_dates" if years is not None else "unknown"
    if years is None:
        stated = [int(n) for n in _STATED_YEARS.findall(text) if 0 < int(n) <= 50]
        if stated:
            years, years_source = float(max(stated)), "stated"

    edu_text = sections.get("education", "")
    if not edu_text:
        edu_text = "\n".join(
            ln for ln in text.splitlines()
            if re.search(r"university|college|institute|school of|degree", ln, re.IGNORECASE)
        )
    level, education = _highest_education(edu_text)

    projects = [ln.strip() for ln in sections.get("projects", "").splitlines() if ln.strip()][:8]
    certs = sorted({
        m.group(0).strip().title()
        for pat in CERTIFICATIONS.values()
        for m in re.finditer(pat, text, re.IGNORECASE)
    })
    cert_lines = [ln.strip() for ln in sections.get("certifications", "").splitlines() if ln.strip()]
    certifications = list(dict.fromkeys(cert_lines + certs))[:10]

    exp_bullets = [b for e in employment for b in e.bullets] or bullets_of(exp_text)
    achievements = [ln.strip() for ln in sections.get("achievements", "").splitlines() if ln.strip()]
    achievements += [b for b in exp_bullets if _NUMBER.search(b)][:5]
    achievements = list(dict.fromkeys(achievements))[:8]

    domains = sorted({d for d in DOMAINS if re.search(rf"\b{re.escape(d)}\b", text, re.IGNORECASE)})
    contact = {
        "email": bool(_EMAIL.search(text)),
        "phone": bool(_PHONE.search(text)),
        "profile_link": bool(re.search(r"linkedin\.com|github\.com", text, re.IGNORECASE)),
    }

    # ---- quality (transparent heuristic)
    quantified = sum(1 for b in exp_bullets if _NUMBER.search(b))
    q_ratio = quantified / len(exp_bullets) if exp_bullets else 0.0
    action = sum(1 for b in exp_bullets if b.split(" ")[0].lower().strip(",.:") in ACTION_VERBS)
    a_ratio = action / len(exp_bullets) if exp_bullets else 0.0
    breakdown = {
        "core_sections": 10 * sum(1 for s in ("experience", "education", "skills") if s in sections),
        "quantified_achievements": round(25 * min(1.0, q_ratio / 0.3)),
        "action_verbs": round(15 * min(1.0, a_ratio / 0.6)),
        "length": 10 if 150 <= words <= 1200 else 5 if 80 <= words <= 1800 else 0,
        "contact_details": 5 * contact["email"] + 3 * contact["phone"] + 2 * contact["profile_link"],
        "summary": 5 if "summary" in sections else 0,
        "skills_breadth": 5 if len(technical) + len(tools) >= 8 else 3 if len(technical) + len(tools) >= 4 else 0,
    }
    quality = ResumeQuality(score=min(100, sum(breakdown.values())), breakdown=breakdown)

    weak = sum(1 for b in exp_bullets if WEAK_START.match(b))
    strengths: list[str] = []
    if years_source == "employment_dates" and years and years >= 5:
        strengths.append(f"About {years:g} years of experience evidenced by dated roles")
    if exp_bullets and q_ratio >= 0.3:
        strengths.append("Achievements are quantified with numbers or percentages")
    if len(leadership) >= 3:
        strengths.append(f"Leadership evidence in {len(leadership)} areas (e.g. {', '.join(sorted(leadership)[:3]).replace('_', ' ')})")
    if len(technical) >= 10:
        strengths.append(f"Broad technical profile ({len(technical)} recognised technologies)")
    if certifications:
        strengths.append("Certifications are listed")
    if all(s in sections for s in ("experience", "education", "skills")):
        strengths.append("Uses standard, ATS-friendly section headings")

    weaknesses: list[str] = []
    missing: list[str] = []
    ats: list[str] = []
    for s, label in (("summary", "a professional summary"), ("experience", "an experience section"),
                     ("education", "an education section"), ("skills", "a skills section")):
        if s not in sections:
            missing.append(f"No clear {s} section was detected - add {label} with a standard heading")
    if not contact["email"]:
        missing.append("No email address detected")
    if not contact["phone"]:
        missing.append("No phone number detected")
    if years_source == "unknown":
        missing.append("No dated employment history detected (use 'Mon YYYY - Mon YYYY' ranges)")
    if exp_bullets and q_ratio < 0.3:
        weaknesses.append("Few achievements include measurable results (numbers, %, scale)")
    if weak:
        weaknesses.append(f"{weak} bullet(s) start with weak phrases such as 'responsible for' or 'worked on'")
        ats.append("Start bullets with strong action verbs (e.g. built, led, reduced)")
    if words < 150:
        weaknesses.append("The resume is very short; add detail on responsibilities and outcomes")
    if words > 1200:
        weaknesses.append("The resume is long; consider tightening it to the most relevant experience")
    if not leadership:
        weaknesses.append("No leadership evidence detected (e.g. mentoring, leading a team)")
    ats += [
        "Use standard headings (Summary, Experience, Education, Skills)",
        "Use a single-column layout and avoid tables, text boxes and images for key content",
        "Mirror exact keywords from the target job description where they are truthful",
    ]

    roles = len(employment)
    top = ", ".join(s.skill for s in technical[:5])
    summary = (
        f"{years:g} years of experience ({'from dated roles' if years_source == 'employment_dates' else 'as stated'})"
        if years is not None else "Years of experience could not be determined"
    )
    summary += f"; {roles} role(s) detected" if roles else ""
    summary += f"; skills evidenced include {top}" if top else ""

    return ResumeAnalysis(
        word_count=words, sections_found=sorted(k for k in sections if k != "header"),
        technical_skills=technical, tools_and_technologies=tools, leadership_skills=leadership,
        skill_categories={g: sorted(v) for g, v in categories.items()}, employment=employment,
        years_of_experience=years, years_source=years_source,
        education=education, highest_education_level=level, projects=projects,
        certifications=certifications, achievements=achievements, domains=domains,
        contact_present=contact, experience_summary=summary + ".", quality=quality,
        strengths=strengths, weaknesses=weaknesses, missing_information=missing,
        ats_recommendations=ats,
    )
