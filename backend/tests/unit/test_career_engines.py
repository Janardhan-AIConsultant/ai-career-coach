from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.career.jd_analysis import analyze_job_description
from app.career.matching import ScoringConfig, match
from app.career.optimization import optimize_resume, rewrite_weak_bullet
from app.career.resume_analysis import analyze_resume
from app.career.skill_gap import analyze_skill_gaps
from app.career.text_utils import years_from_ranges
from tests.career_data import HOSTILE_RESUME, JD, RESUME

NOW = datetime(2026, 6, 1, tzinfo=UTC)


# ---------------------------------------------------------------- resume analysis
def test_resume_skills_have_evidence_and_groups() -> None:
    a = analyze_resume(RESUME, NOW)
    skills = {s.skill: s for s in a.technical_skills}
    assert {"python", "fastapi", "java", "spring boot", "postgresql", "kafka", "aws"} <= set(skills)
    assert skills["fastapi"].group == "backend" and "FastAPI" in skills["fastapi"].evidence
    assert {t.skill for t in a.tools_and_technologies} >= {"docker", "git"}
    assert "microservices" in a.skill_categories["microservices"]


def test_skills_not_in_resume_are_not_invented() -> None:
    names = {s.skill for s in analyze_resume(RESUME, NOW).technical_skills}
    assert not names & {"kubernetes", "terraform", "react", "langgraph", "rabbitmq"}


def test_word_boundaries_java_vs_javascript() -> None:
    names = {s.skill for s in analyze_resume("Skills\nJavaScript, TypeScript and MySQL", NOW).technical_skills}
    assert "javascript" in names and "java" not in names and "mysql" in names and "sql" not in names


def test_special_character_skills() -> None:
    names = {s.skill for s in analyze_resume("Skills\nC++, C#, .NET, Node.js", NOW).technical_skills}
    assert {"c++", "c#", ".net", "node.js"} <= names


def test_years_from_dates_union_and_present() -> None:
    a = analyze_resume(RESUME, NOW)
    # 2019-present (2026) = 7, 2015-2018 = 3  -> 10
    assert a.years_of_experience == 10.0 and a.years_source == "employment_dates"
    assert years_from_ranges("2015 - 2018\n2017 - 2020", NOW) == 5.0  # overlap not double counted


def test_stated_years_fallback_and_unknown() -> None:
    assert analyze_resume("I have 8 years of experience in Python.", NOW).years_source == "stated"
    assert analyze_resume("Python developer.", NOW).years_of_experience is None


def test_leadership_evidence() -> None:
    lead = analyze_resume(RESUME, NOW).leadership_skills
    assert {"team_management", "mentoring", "stakeholder_communication", "delivery_management"} <= set(lead)


def test_education_certs_domains_sections() -> None:
    a = analyze_resume(RESUME, NOW)
    assert a.highest_education_level == "bachelor's" and any("B.Tech" in e for e in a.education)
    assert any("Aws Certified" in c or "AWS Certified" in c for c in a.certifications)
    assert "fintech" in a.domains
    assert {"summary", "experience", "education", "skills", "projects"} <= set(a.sections_found)
    assert len(a.employment) == 2 and a.employment[0].is_current


def test_contact_info_reported_as_booleans_only() -> None:
    a = analyze_resume(RESUME, NOW)
    assert a.contact_present == {"email": True, "phone": True, "profile_link": True}
    dumped = a.model_dump_json()
    assert "jane.doe@example.com" not in dumped and "98765" not in dumped


def test_quality_score_is_transparent_and_bounded() -> None:
    q = analyze_resume(RESUME, NOW).quality
    assert 0 <= q.score <= 100 and q.score == sum(q.breakdown.values())
    weak = analyze_resume("Worked on stuff.", NOW).quality
    assert weak.score < q.score


def test_weaknesses_and_missing_info_reported() -> None:
    a = analyze_resume("Python developer. Worked on things.", NOW)
    assert any("experience section" in m for m in a.missing_information)
    assert any("email" in m for m in a.missing_information)
    b = analyze_resume(RESUME, NOW)
    assert any("weak phrases" in w for w in b.weaknesses)  # 'responsible for' / 'worked on'
    assert any("Reduced API latency" in x for x in b.achievements)


# ---------------------------------------------------------------- JD analysis
def test_jd_basic_fields() -> None:
    j = analyze_job_description(JD)
    assert j.title == "Senior Backend Engineer" and j.company == "Acme Corp"
    assert j.min_years_experience == 6.0 and j.required_education_level == "bachelor's"
    assert "fintech" in j.domain_knowledge
    assert {"mentoring", "stakeholder_communication"} <= set(j.leadership_expectations)
    assert any("microservices" in r for r in j.responsibilities)


def test_jd_skill_levels() -> None:
    j = analyze_job_description(JD)
    assert {"python", "fastapi", "postgresql", "kafka", "rabbitmq", "kubernetes"} <= set(j.mandatory_skills)
    assert {"langgraph", "docker", "terraform"} <= set(j.preferred_skills)
    assert not set(j.mandatory_skills) & set(j.preferred_skills)


def test_jd_highest_level_wins_and_optional_default() -> None:
    j = analyze_job_description("About us\nWe use Redis internally.\n\nPreferred\n- Redis\n\nRequired\n- Redis")
    assert "redis" in j.mandatory_skills
    k = analyze_job_description("About us\nWe also use Jenkins in our company.")
    assert "jenkins" in k.optional_skills


def test_sample_files_from_original_project() -> None:
    data = Path(__file__).resolve().parents[3] / "data"
    j = analyze_job_description((data / "sample_job_description.txt").read_text(encoding="utf-8"))
    assert {"langchain", "rag"} <= set(j.mandatory_skills)
    assert "langgraph" in j.preferred_skills
    r = analyze_resume((data / "sample_resume.txt").read_text(encoding="utf-8"), NOW)
    assert "python" in {s.skill for s in r.technical_skills}


# ---------------------------------------------------------------- matching
def _pair(resume: str = RESUME, jd: str = JD):  # type: ignore[no-untyped-def]
    return analyze_resume(resume, NOW), analyze_job_description(jd)


def test_match_is_deterministic_and_has_disclaimer() -> None:
    r, j = _pair()
    a, b = match(r, j), match(r, j)
    assert a == b and 0 <= a.overall_score <= 100
    assert "not an official ATS score" in a.disclaimer and a.scoring_version == "v1"


def test_match_classification_with_evidence() -> None:
    m = match(*_pair())
    matching = {s.skill: s for s in m.matching_skills}
    assert {"python", "fastapi", "postgresql", "kafka", "docker"} <= set(matching)
    assert matching["python"].resume_evidence
    assert "kubernetes" in {s.skill for s in m.missing_skills} | {s.skill for s in m.partial_skills}
    # RabbitMQ requested; resume has Kafka (same group) -> partial, not missing
    partial = {s.skill: s for s in m.partial_skills}
    assert partial["rabbitmq"].related_resume_skill == "kafka"
    assert "langgraph" in {s.skill for s in m.partial_skills} | {s.skill for s in m.missing_skills}


def test_perfect_and_empty_matches() -> None:
    jd = "Required\n- Python\n- FastAPI"
    good = match(*_pair("Skills\nPython, FastAPI", jd))
    none = match(*_pair("Skills\nCobol", jd))
    assert good.overall_score == 100.0 and none.overall_score == 0.0


def test_programming_language_partial_credit_is_lower() -> None:
    lang = match(*_pair("Skills\nJava", "Required\n- Python"))
    msg = match(*_pair("Skills\nRabbitMQ", "Required\n- Kafka"))
    assert lang.overall_score == 25.0 and msg.overall_score == 50.0


def test_inapplicable_categories_excluded_and_weights_renormalised() -> None:
    m = match(*_pair("Skills\nPython", "Required\n- Python"))
    scores = {c.category: c.score for c in m.category_scores}
    assert scores["technical"] == 100.0 and scores["leadership"] is None and scores["education"] is None
    assert m.overall_score == 100.0


def test_weights_are_configurable() -> None:
    r, j = _pair()
    default = match(r, j)
    heavy = match(r, j, ScoringConfig(weights={**default.weights, "technical": 0.0, "experience": 1.0}))
    assert heavy.overall_score != default.overall_score
    exp = next(c for c in heavy.category_scores if c.category == "experience")
    assert exp.score == 100.0  # 10 years evidenced vs 6 requested


def test_experience_shortfall_education_and_certs() -> None:
    jd = "Required\n- 10 years of experience\n- Master's degree\n- AWS Certified Solutions Architect"
    m = match(*_pair(RESUME, jd))
    by = {c.category: c for c in m.category_scores}
    assert by["education"].score == 0.0 and by["certifications"].score == 100.0
    assert by["experience"].score == 100.0  # 10 years >= 10
    assert "master" in by["education"].detail.lower()


def test_hostile_resume_text_cannot_change_score() -> None:
    clean, hostile = match(*_pair(RESUME)), match(*_pair(HOSTILE_RESUME))
    assert hostile.overall_score == clean.overall_score
    assert {s.skill for s in hostile.matching_skills} == {s.skill for s in clean.matching_skills}


def test_recommendations_flag_missing_mandatory() -> None:
    recs = " ".join(match(*_pair()).recommendations)
    assert "kubernetes" in recs.lower() and "only if you truly have it" in recs


# ---------------------------------------------------------------- skill gaps
def test_skill_gaps_severity_timeline_and_content() -> None:
    r, j = _pair()
    g = analyze_skill_gaps(match(r, j), j)
    k8s = next(x for x in g.gaps if x.skill == "kubernetes")
    assert k8s.severity == "critical" and k8s.suggested_timeline_days == 60 and k8s.kind == "technical"
    assert k8s.status == "not_evidenced" and k8s.learning_recommendations and k8s.practical_exercises
    assert all(x.suggested_timeline_days in (7, 15, 60) for x in g.gaps)
    assert g.gaps == sorted(g.gaps, key=lambda x: ({"critical": 0, "high": 1, "medium": 2, "low": 3}[x.severity], x.kind, x.skill))
    rabbit = next(x for x in g.gaps if x.skill == "rabbitmq")
    assert rabbit.status == "partial" and "kafka" in rabbit.current_evidence


def test_declared_absent_vs_not_evidenced() -> None:
    r, j = _pair()
    g = analyze_skill_gaps(match(r, j), j, {"Kubernetes"})
    by = {x.skill: x.status for x in g.gaps}
    assert by["kubernetes"] == "confirmed_absent" and by["terraform"] == "not_evidenced"


def test_leadership_gaps() -> None:
    r, j = _pair("Skills\nPython\nExperience\n2020 - 2024\n- Built APIs", JD)
    g = analyze_skill_gaps(match(r, j), j)
    lead = [x for x in g.gaps if x.kind == "leadership"]
    assert {x.skill for x in lead} >= {"mentoring", "stakeholder communication"}
    assert all(x.severity == "high" and x.learning_recommendations for x in lead)


def test_no_gaps_message() -> None:
    r, j = _pair("Skills\nPython", "Required\n- Python")
    assert analyze_skill_gaps(match(r, j), j).summary.startswith("No gaps")


# ---------------------------------------------------------------- optimisation
def _opt(**kw):  # type: ignore[no-untyped-def]
    r, j = _pair()
    return optimize_resume(RESUME, r, j, match(r, j), **kw)


def test_safe_weak_bullet_rewrites() -> None:
    assert rewrite_weak_bullet("Responsible for maintaining Kafka consumers") == "Maintained Kafka consumers"
    assert rewrite_weak_bullet("Worked on improving test coverage") == "Contributed to improving test coverage"
    assert rewrite_weak_bullet("Responsible for the billing module") is None  # no safe rewrite
    assert rewrite_weak_bullet("Helped with deployments") is None  # would overstate ownership


def test_minor_changes_applied_significant_pending_by_default() -> None:
    o = _opt()
    minors = [c for c in o.changes if c.change_type == "minor"]
    assert minors and all(c.applied for c in minors)
    assert "Maintained Kafka consumers" in o.optimized_resume_text
    assert "Responsible for maintaining Kafka" not in o.optimized_resume_text
    assert set(o.pending_approval_ids) == {"summary-1", "skills-1"}
    assert all(not c.applied for c in o.changes if c.change_type == "significant")
    assert "Backend engineer and team lead" in o.optimized_resume_text  # original summary untouched


def test_significant_changes_applied_only_when_approved() -> None:
    o = _opt(approved_ids={"summary-1"})
    assert "10-year professional" in o.optimized_resume_text and o.pending_approval_ids == ["skills-1"]
    both = _opt(approved_ids={"summary-1", "skills-1"})
    assert both.pending_approval_ids == []
    skills_line = next(c.after for c in both.changes if c.id == "skills-1")
    assert skills_line.split(", ")[0] in {"python", "fastapi", "postgresql", "kafka"}  # JD-relevant first


def test_never_adds_unconfirmed_skills() -> None:
    o = _opt(approved_ids={"summary-1", "skills-1"})
    low = o.optimized_resume_text.lower()
    assert "kubernetes" not in low and "terraform" not in low and "rabbitmq" not in low
    assert {"kubernetes", "terraform", "langgraph"} <= set(o.needs_confirmation)
    assert any("kubernetes" in q.lower() for q in o.clarification_questions)


def test_confirmed_skills_are_added_and_sanitised() -> None:
    o = _opt(approved_ids={"skills-1"}, confirmed_skills=["Kubernetes", "x; DROP TABLE users", "  ", "a" * 80])
    skills = next(c.after for c in o.changes if c.id == "skills-1")
    assert "Kubernetes" in skills and "DROP" not in skills and "a" * 80 not in skills
    assert "kubernetes" not in o.needs_confirmation


def test_no_invented_numbers() -> None:
    import re

    o = _opt(approved_ids={"summary-1", "skills-1"})
    allowed = set(re.findall(r"\d+", RESUME)) | {"10"}  # 10 = years computed from the resume's dates
    produced = set(re.findall(r"\d+", o.optimized_resume_text))
    assert produced <= allowed


def test_decline_minor_change() -> None:
    o = _opt(declined_ids={"bullet-1"})
    c = next(x for x in o.changes if x.id == "bullet-1")
    assert not c.applied and c.before in o.optimized_resume_text


def test_clarification_for_missing_metrics_and_before_after() -> None:
    o = _opt()
    assert any("measurable result" in q for q in o.clarification_questions)
    assert all(c.before != c.after for c in o.changes if c.change_type == "minor")
    assert "Only facts already in your resume" in o.note


def test_keyword_recommendations() -> None:
    k = _opt().keyword_recommendations
    assert "python" in k["emphasise"] and "kubernetes" in k["missing_requires_confirmation"]
    assert any(x.startswith("rabbitmq") for x in k["partially_evidenced"])


def test_hostile_resume_does_not_alter_optimisation_behaviour() -> None:
    r, j = _pair(HOSTILE_RESUME)
    o = optimize_resume(HOSTILE_RESUME, r, j, match(r, j))
    assert "kubernetes" not in o.optimized_resume_text.lower()
    assert {c.id for c in o.changes if c.change_type == "significant"} == {"summary-1", "skills-1"}


@pytest.mark.parametrize("fn", [analyze_resume, analyze_job_description])
def test_empty_ish_input_does_not_crash(fn) -> None:  # type: ignore[no-untyped-def]
    fn("x")
