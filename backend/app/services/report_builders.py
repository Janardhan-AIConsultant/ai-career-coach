"""Turn analysis results into ``ReportDoc`` structures (content only, no layout)."""

from __future__ import annotations

from app.schemas.career import (
    SCORE_DISCLAIMER,
    JobDescriptionAnalysis,
    MatchResult,
    OptimizationResult,
    ResumeAnalysis,
    SkillGapAnalysis,
)
from app.services.report_render import ReportDoc, Section


def _kv(items: dict[str, list[str]]) -> list[str]:
    return [f"{k.replace('_', ' ').title()}: {', '.join(v)}" for k, v in items.items() if v]


def resume_analysis_doc(a: ResumeAnalysis) -> ReportDoc:
    return ReportDoc("Resume Analysis", None, [
        Section("Overview", [a.experience_summary, f"Resume quality (heuristic): {a.quality.score}/100. {a.quality.note}"]),
        Section("Strengths", bullets=a.strengths or ["No standout strengths detected automatically"]),
        Section("Weaknesses", bullets=a.weaknesses or ["None detected"]),
        Section("Missing information", bullets=a.missing_information or ["None detected"]),
        Section("ATS-friendly recommendations", bullets=a.ats_recommendations),
        Section("Skills by category", bullets=_kv(a.skill_categories)),
        Section("Leadership evidence", bullets=[f"{k.replace('_', ' ').title()}: {v}" for k, v in a.leadership_skills.items()] or ["None detected"]),
        Section("Education and certifications", bullets=[*a.education, *a.certifications] or ["None detected"]),
    ])


def jd_analysis_doc(j: JobDescriptionAnalysis) -> ReportDoc:
    return ReportDoc("Job Description Analysis", None, [
        Section("Role", [f"Title: {j.title or 'not stated'}", f"Company: {j.company or 'not stated'}",
                         f"Minimum experience: {j.min_years_experience:g} years" if j.min_years_experience else "Minimum experience: not stated"]),
        Section("Mandatory skills", bullets=j.mandatory_skills or ["None detected"]),
        Section("Preferred skills", bullets=j.preferred_skills or ["None detected"]),
        Section("Optional skills", bullets=j.optional_skills or ["None detected"]),
        Section("Responsibilities", bullets=j.responsibilities or ["None detected"]),
        Section("Leadership expectations", bullets=[c.replace("_", " ") for c in j.leadership_expectations] or ["None detected"]),
        Section("Education", bullets=j.education_requirements or ["Not stated"]),
    ])


def match_doc(m: MatchResult) -> ReportDoc:
    table = [["Category", "Score", "Weight", "Detail"]] + [
        [c.category.title(), "n/a" if c.score is None else f"{c.score:g}", f"{c.weight:g}", c.detail]
        for c in m.category_scores
    ]
    return ReportDoc("Resume and Job Match", SCORE_DISCLAIMER, [
        Section("Overall estimated match", [f"{m.overall_score:g} / 100 (scoring {m.scoring_version})"]),
        Section("Category scores", table=table),
        Section("Matching skills", bullets=[f"{s.skill} - {s.resume_evidence}" for s in m.matching_skills] or ["None"]),
        Section("Partially matching skills", bullets=[f"{s.skill} (you show {s.related_resume_skill})" for s in m.partial_skills] or ["None"]),
        Section("Missing skills", bullets=[f"{s.skill} ({s.level})" for s in m.missing_skills] or ["None"]),
        Section("Recommendations", bullets=m.recommendations),
    ])


def skill_gap_doc(g: SkillGapAnalysis) -> ReportDoc:
    sections = [Section("Summary", [g.summary, g.note])]
    for gap in g.gaps:
        sections.append(Section(
            f"{gap.skill} ({gap.kind}, {gap.severity})",
            [f"Status: {gap.status.replace('_', ' ')}", f"Current evidence: {gap.current_evidence}",
             f"Required: {gap.required_competency}", f"Suggested timeline: {gap.suggested_timeline_days} days"],
            [*[f"Learn: {r}" for r in gap.learning_recommendations],
             *[f"Practise: {e}" for e in gap.practical_exercises]]))
    return ReportDoc("Skill Gap Analysis", None, sections)


def optimization_doc(o: OptimizationResult) -> ReportDoc:
    table = [["Section", "Type", "Applied", "Before", "After"]] + [
        [c.section, c.change_type, "yes" if c.applied else "pending approval", c.before[:200] or "-", c.after[:200]]
        for c in o.changes
    ]
    return ReportDoc("Resume Optimisation", o.note, [
        Section("Before and after", table=table),
        Section("Keyword recommendations", bullets=_kv(o.keyword_recommendations)),
        Section("Questions for you", bullets=o.clarification_questions or ["None"]),
    ])


def optimized_resume_doc(o: OptimizationResult) -> ReportDoc:
    """The optimised resume itself, as paragraphs (ATS-friendly: no tables or columns)."""
    paras = [p.strip() for p in o.optimized_resume_text.split("\n\n") if p.strip()]
    return ReportDoc("Resume", None, [Section("", paragraphs=paras)])


def interview_doc(questions: list) -> ReportDoc:  # type: ignore[type-arg]
    """Interview preparation pack (questions are ``PreparedQuestion`` models)."""
    sections = []
    for i, q in enumerate(questions, 1):
        sections.append(Section(
            f"{i}. [{q.kind.replace('_', ' ')} / {q.topic.replace('_', ' ')}] {q.question}",
            [f"Why this question: {q.reason}", f"Model answer: {q.model_answer}",
             f"Practical example: {q.practical_example}"],
            [*[f"Key point: {k}" for k in q.key_points], *[f"Follow-up: {f}" for f in q.follow_ups],
             *[f"Evaluation: {c}" for c in q.evaluation_criteria]]))
    return ReportDoc("Interview Preparation", "Model answers are study aids; adapt them to your own experience.", sections)


def roadmap_doc(r) -> ReportDoc:  # type: ignore[no-untyped-def]
    """Learning roadmap (``RoadmapOut``) as a printable plan."""
    sections = [Section("Overview", [
        f"Goal: {r.goal}", f"Duration: {r.duration_days} days; about {r.estimated_hours or 0:g} hours in total",
        f"Status: {r.status.replace('_', ' ')}", r.completion_criteria.get("description", "")])]
    for m in r.modules:
        sections.append(Section(
            f"Module {m.position}: {m.title}", [],
            [*[f"Objective: {o}" for o in m.objectives],
             *[f"Day {a.day_number} [{a.kind}] {a.title} ({a.estimated_minutes} min)" for a in m.activities]]))
    return ReportDoc(r.title, "Platform learning plan; completion is verified by assessments, not by this document.", sections)


def portfolio_doc(p) -> ReportDoc:  # type: ignore[no-untyped-def]
    """Owner's portfolio (``PortfolioOut``): learning evidence only."""
    s = p.stats
    overview = (
        f"{s.learning_paths_completed} learning plan(s) completed, {s.activities_completed} activities "
        f"(about {s.estimated_learning_hours:g} study hours), {s.assessments_passed} assessment(s) passed, "
        f"{s.certificates} certificate(s), {s.projects_passed} project(s) reviewed."
    )
    sections = [Section("Overview", [overview])]
    if p.skills:
        sections.append(Section("Skill evidence", table=[["Skill", "Evidence level", "Based on"]] + [
            [k.skill, k.highest.replace("demonstrated", "practically demonstrated"),
             "; ".join(sorted({e["kind"].replace("_", " ") for e in k.evidence}))] for k in p.skills]))
    visible = [i for i in p.timeline if i.is_visible]
    sections.append(Section("Achievement timeline", bullets=[
        f"{i.achieved_at:%Y-%m-%d} [{i.kind.replace('_', ' ')} / {i.evidence_level}] {i.title}" for i in visible] or ["No achievements yet"]))
    certs = [i for i in visible if i.kind == "certificate"]
    if certs:
        sections.append(Section("Certificates", bullets=[f"{i.title} - ID {i.details['certificate_id']} - {i.details['verification_url']}" for i in certs]))
    projects = [i for i in visible if i.kind == "project"]
    if projects:
        sections.append(Section("Projects", bullets=[f"{i.title}" + (f" - {i.details['repo_url']}" if i.details.get("repo_url") else "") for i in projects]))
    return ReportDoc("Career Achievement Portfolio", p.disclaimer, sections)
