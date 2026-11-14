"""Job-specific resume optimisation that cannot fabricate.

Every proposed change is built only from text already in the resume, evidence the analysis
detected, or skills the user explicitly confirmed. Changes are classified:
* ``minor`` (wording of an existing bullet): applied by default, can be declined.
* ``significant`` (new/rewritten summary, skills section): applied ONLY when the caller passes the
  change id in ``approved_ids``; otherwise listed as pending approval.
Metrics are never invented: bullets without numbers produce clarification questions instead.
"""

from __future__ import annotations

import re

from app.career.resume_analysis import WEAK_START
from app.career.text_utils import heading_of, split_sections
from app.schemas.career import (
    Change,
    JobDescriptionAnalysis,
    MatchResult,
    OptimizationResult,
    ResumeAnalysis,
)

_IRREGULAR = {"building": "built", "leading": "led", "running": "ran", "writing": "wrote",
              "driving": "drove", "overseeing": "oversaw", "making": "made", "setting": "set"}
_KNOWN_PAST = {
    "managed", "developed", "designed", "maintained", "implemented", "delivered", "created",
    "deployed", "optimized", "coordinated", "owned", "improved", "tested", "integrated", "automated",
    "migrated", "monitored", "configured", "analyzed", "supported", "reviewed", "planned",
}
_NUMBER = re.compile(r"\d|%|\$")
_GERUND = re.compile(r"^responsible for\s+(\w+ing)\b(.*)$", re.IGNORECASE)
_WORKED_ON = re.compile(r"^worked on\s+(.*)$", re.IGNORECASE)


def _past_tense(gerund: str) -> str | None:
    g = gerund.lower()
    if g in _IRREGULAR:
        return _IRREGULAR[g]
    stem = g[:-3]
    for cand in (stem + "ed", stem + "d", stem[:-1] + "ed" if len(stem) > 1 and stem[-1] == stem[-2] else ""):
        if cand in _KNOWN_PAST:
            return cand
    return None


def rewrite_weak_bullet(bullet: str) -> str | None:
    """Return a stronger, meaning-preserving rewrite, or None when no safe rewrite exists."""
    m = _GERUND.match(bullet)
    if m:
        verb = _past_tense(m.group(1))
        if verb:
            return f"{verb.capitalize()}{m.group(2)}".strip()
    w = _WORKED_ON.match(bullet)
    if w:
        return f"Contributed to {w.group(1)}".strip()
    return None


def _replace_section_body(text: str, section: str, new_body: str) -> str | None:
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if heading_of(ln) == section), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if heading_of(lines[i])), len(lines))
    return "\n".join([*lines[: start + 1], new_body, "", *lines[end:]]).rstrip() + "\n"


def _clean_confirmed(items: list[str]) -> list[str]:
    out = []
    for it in items:
        it = re.sub(r"\s+", " ", it).strip()
        if 1 <= len(it) <= 50 and re.fullmatch(r"[\w .+#/&()-]+", it):
            out.append(it)
    return list(dict.fromkeys(out))


def optimize_resume(
    text: str, resume: ResumeAnalysis, jd: JobDescriptionAnalysis, match: MatchResult, *,
    confirmed_skills: list[str] | None = None, approved_ids: set[str] | None = None,
    declined_ids: set[str] | None = None,
) -> OptimizationResult:
    approved, declined = approved_ids or set(), declined_ids or set()
    confirmed = _clean_confirmed(confirmed_skills or [])
    changes: list[Change] = []
    out_text = text

    # ---- minor: weak bullets (only where a safe rewrite exists)
    questions: list[str] = []
    bullet_no = 0
    for entry in resume.employment:
        for b in entry.bullets:
            if WEAK_START.match(b):
                bullet_no += 1
                new = rewrite_weak_bullet(b)
                if new and new != b:
                    cid = f"bullet-{bullet_no}"
                    applied = cid not in declined
                    changes.append(Change(
                        id=cid, section="experience", change_type="minor", before=b, after=new,
                        reason="Stronger action verb; same meaning, no new facts", applied=applied))
                    if applied and b in out_text:
                        out_text = out_text.replace(b, new, 1)
                else:
                    questions.append(f"What was your specific role or outcome in: '{b[:90]}'? (this helps replace a vague opening)")
    no_metric = [b for e in resume.employment for b in e.bullets if not _NUMBER.search(b) and len(b) > 25]
    for b in no_metric[:4]:
        questions.append(f"If accurate, can you add a measurable result (number, %, scale) to: '{b[:90]}'?")

    # ---- significant: skills section (evidenced first, JD-relevant first, then confirmed)
    jd_skills = {r.skill for r in jd.skills}
    evidenced = [s.skill for s in [*resume.technical_skills, *resume.tools_and_technologies]]
    ordered = [s for s in evidenced if s in jd_skills] + [s for s in evidenced if s not in jd_skills]
    ordered += [c for c in confirmed if c.lower() not in {e.lower() for e in ordered}]
    if ordered:
        old_skills = _section_text(text, "skills")
        new_line = ", ".join(ordered)
        approved_skills = "skills-1" in approved
        changes.append(Change(
            id="skills-1", section="skills", change_type="significant", before=old_skills,
            after=new_line, applied=approved_skills,
            reason="Lists skills evidenced in your resume, JD-relevant first"
                   + (f"; includes {len(confirmed)} skill(s) you confirmed" if confirmed else "")))
        if approved_skills:
            replaced = _replace_section_body(out_text, "skills", new_line)
            out_text = replaced if replaced is not None else out_text.rstrip() + f"\n\nSkills\n{new_line}\n"

    # ---- significant: professional summary built from evidenced facts only
    relevant = [m.skill for m in match.matching_skills][:4] or ordered[:4]
    parts = []
    if resume.years_of_experience:
        parts.append(f"{resume.years_of_experience:g}-year professional")
    else:
        parts.append("Professional")
    if relevant:
        parts[-1] += f" with hands-on experience in {', '.join(relevant)}"
    lead = [c.replace("_", " ") for c in list(resume.leadership_skills)[:2]]
    if lead:
        parts.append(f"demonstrated {' and '.join(lead)}")
    if resume.domains:
        parts.append(f"domain exposure: {', '.join(resume.domains[:2])}")
    target = f" Targeting {jd.title}." if jd.title else ""
    summary = "; ".join(parts) + "." + target
    old_summary = _section_text(text, "summary")
    approved_summary = "summary-1" in approved
    changes.append(Change(
        id="summary-1", section="summary", change_type="significant", before=old_summary,
        after=summary, applied=approved_summary,
        reason="Summary assembled only from facts detected in your resume"))
    if approved_summary:
        replaced = _replace_section_body(out_text, "summary", summary)
        if replaced is None:
            lines = out_text.splitlines()
            idx = next((i for i, ln in enumerate(lines) if heading_of(ln)), len(lines))
            out_text = "\n".join([*lines[:idx], "Summary", summary, "", *lines[idx:]])
        else:
            out_text = replaced

    keywords = {
        "emphasise": [m.skill for m in match.matching_skills],
        "partially_evidenced": [f"{m.skill} (you show {m.related_resume_skill})" for m in match.partial_skills],
        "missing_requires_confirmation": [m.skill for m in match.missing_skills],
    }
    needs = [m.skill for m in match.missing_skills if m.skill.lower() not in {c.lower() for c in confirmed}]
    for s in needs[:5]:
        questions.append(f"Do you have real experience with {s}? If yes, confirm it and tell us where you used it.")
    pending = [c.id for c in changes if c.change_type == "significant" and not c.applied]

    return OptimizationResult(
        optimized_resume_text=out_text, changes=changes, keyword_recommendations=keywords,
        needs_confirmation=needs, clarification_questions=questions[:10], pending_approval_ids=pending,
    )


def _section_text(text: str, section: str) -> str:
    return split_sections(text).get(section, "")

