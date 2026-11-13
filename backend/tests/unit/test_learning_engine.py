import pytest

from app.assessments.bank import ASSESSMENTS, BY_SLUG, SKILL_ASSESSMENTS
from app.assessments.scoring import correct_display, score_question
from app.core.exceptions import InputValidationError
from app.learning.curriculum import (
    CAPSTONE_DAYS,
    FOCUS_LIMIT,
    FocusItem,
    build_roadmap,
    validate_duration,
)

FOCUS = [FocusItem("python", "programming_languages", "gap"), FocusItem("kafka", "messaging", "gap"),
         FocusItem("postgresql", "databases", "gap"), FocusItem("rag", "rag", "gap"),
         FocusItem("react", "frontend", "gap"), FocusItem("docker", "devops_tools", "gap"),
         FocusItem("aws", "cloud", "gap"), FocusItem("mentoring", "leadership", "gap"),
         FocusItem("fastapi", "backend", "gap"), FocusItem("redis", "databases", "gap"),
         FocusItem("terraform", "devops_tools", "gap"), FocusItem("java", "programming_languages", "gap")]


# ---------------------------------------------------------------- roadmap durations
@pytest.mark.parametrize("days", [7, 15, 60])
def test_supported_durations_build(days: int) -> None:
    plan = build_roadmap(days, "goal", FOCUS)
    assert plan.title.startswith(f"{days}-day roadmap") and plan.duration_days == days
    all_days = sorted({a.day for m in plan.modules for a in m.activities})
    assert all_days == list(range(1, days + 1))  # every day has work, none beyond the duration
    assert plan.estimated_hours > 0
    assert len([m for m in plan.modules if m.title != "Capstone project"]) <= FOCUS_LIMIT[days]


@pytest.mark.parametrize("days", [-7, 0, 1, 3, 14, 30, 45, 90, 365])
def test_unsupported_durations_rejected(days: int) -> None:
    with pytest.raises(InputValidationError) as e:
        validate_duration(days)
    assert "7, 15 or 60" in e.value.message
    with pytest.raises(InputValidationError):
        build_roadmap(days, "goal", FOCUS)


def test_capstone_only_for_longer_plans() -> None:
    assert CAPSTONE_DAYS == {7: 0, 15: 2, 60: 7}
    short = build_roadmap(7, "g", FOCUS)
    assert not any(m.title == "Capstone project" for m in short.modules)
    for days, n in ((15, 2), (60, 7)):
        cap = next(m for m in build_roadmap(days, "g", FOCUS).modules if m.title == "Capstone project")
        assert len(cap.activities) == n and all(a.kind == "project" for a in cap.activities)


def test_each_module_has_learning_exercise_and_ends_with_assessment_or_review() -> None:
    plan = build_roadmap(15, "g", FOCUS)
    for m in plan.modules:
        if m.title == "Capstone project":
            continue
        kinds = [a.kind for a in m.activities]
        assert "learn" in kinds and "exercise" in kinds and kinds[-1] in {"assessment", "review"}
        last_day = max(a.day for a in m.activities)
        assert {a.kind for a in m.activities if a.day == last_day} & {"assessment", "review"}
    python = next(m for m in plan.modules if m.title == "Python")
    assert python.activities[-1].ref == "assessment:python-fundamentals"
    assert all(r and not r.startswith("http") for m in plan.modules for a in m.activities for r in a.resources)


def test_completion_criteria_require_assessments() -> None:
    plan = build_roadmap(15, "g", FOCUS)
    crit = plan.completion_criteria
    assert crit["min_required_activity_percent"] == 80 and "assessment:python-fundamentals" in crit["assessments_must_be_passed"]  # type: ignore[operator]
    assert "cannot be finished by clicking alone" in str(crit["description"])


def test_roadmap_needs_focus_and_handles_small_plans() -> None:
    with pytest.raises(InputValidationError):
        build_roadmap(7, "g", [])
    one = build_roadmap(7, "g", FOCUS[:1])
    assert len(one.modules) == 1 and max(a.day for a in one.modules[0].activities) == 7
    assert any(a.kind == "learn" for a in one.modules[0].activities)  # days beyond topics -> practice only


# ---------------------------------------------------------------- bank integrity
def test_bank_integrity() -> None:
    assert len({a["slug"] for a in ASSESSMENTS}) == len(ASSESSMENTS)
    for a in ASSESSMENTS:
        qs = a["questions"]
        assert len(qs) == 6 and len({q["key"] for q in qs}) == 6
        assert {q["type"] for q in qs} >= {"mcq", "multi_select", "scenario", "technical"}
        for q in qs:
            assert q["explanation"] and q["prompt"] and q["points"] >= 1
            n = len(q["options"] or [])
            if q["type"] == "mcq":
                assert 0 <= q["correct"] < n >= 2
            elif q["type"] == "multi_select":
                assert q["correct"] and all(0 <= i < n for i in q["correct"])
            elif q["type"] == "scenario":
                assert max(q["correct"]["scores"].values()) == 1.0 and all(0 <= int(k) < n for k in q["correct"]["scores"])
            else:
                kps = q["correct"]["key_points"]
                assert len(kps) >= 2 and all(k == k.lower() for p in kps for k in p["keywords"])
    assert set(SKILL_ASSESSMENTS.values()) <= set(BY_SLUG)


def _perfect(q: dict) -> object:  # type: ignore[type-arg]
    if q["type"] in ("mcq", "multi_select"):
        return q["correct"]
    if q["type"] == "scenario":
        return int(max(q["correct"]["scores"].items(), key=lambda kv: kv[1])[0])
    return " ".join(k for p in q["correct"]["key_points"] for k in p["keywords"][:1]) + " " + "filler " * 40


@pytest.mark.parametrize("q", [q for a in ASSESSMENTS for q in a["questions"]], ids=lambda q: q["key"])
def test_every_question_can_be_fully_answered(q) -> None:  # type: ignore[no-untyped-def]
    r = score_question(q["type"], q["options"], q["correct"], _perfect(q))
    assert r.points == 1.0 and r.status == "correct"
    assert correct_display(q["type"], q["options"], q["correct"])


# ---------------------------------------------------------------- scoring rules
OPTS = ["a", "b", "c", "d"]


def test_mcq_and_invalid_formats() -> None:
    assert score_question("mcq", OPTS, 1, 1).points == 1.0
    assert score_question("mcq", OPTS, 1, 2).status == "incorrect"
    for bad in ("1", 1.0, True, -1, 9, [1], {"a": 1}):
        assert score_question("mcq", OPTS, 1, bad).status == "invalid", bad
    for empty in (None, "", []):
        assert score_question("mcq", OPTS, 1, empty).status == "unanswered"


def test_multi_select_partial_credit_with_penalty() -> None:
    right = [0, 2]
    s = lambda a: score_question("multi_select", OPTS, right, a)
    assert s([0, 2]).points == 1.0 and s([2, 0]).points == 1.0
    assert s([0]).points == 0.5 and s([0]).status == "partial"
    assert s([0, 1]).points == 0.0  # one right minus one wrong
    assert s([0, 1, 2, 3]).points == 0.0 and s([1, 3]).status == "incorrect"
    assert s([0, 0, 2]).points == 1.0  # duplicates ignored
    for bad in ("0", [0, "2"], [0, 9], [True], [0, 1, 2, 3, 0]):
        assert s(bad).status == "invalid", bad


def test_scenario_partial_scores() -> None:
    key = {"scores": {"0": 0.0, "1": 1.0, "2": 0.25, "3": 0.0}}
    assert score_question("scenario", OPTS, key, 1).points == 1.0
    r = score_question("scenario", OPTS, key, 2)
    assert r.points == 0.25 and r.status == "partial"
    assert score_question("scenario", OPTS, key, 0).status == "incorrect"


def test_free_text_rubric() -> None:
    key = {"key_points": [{"text": "A", "keywords": ["gil"]}, {"text": "B", "keywords": ["process"]}], "min_words": 6}
    full = score_question("technical", None, key, "The GIL limits threads so use a process pool for cpu work")
    assert full.points == 1.0 and "keyword rubric" in full.feedback
    half = score_question("technical", None, key, "The GIL limits threads here and elsewhere in code")
    assert half.points == 0.5 and "Missing: B" in half.feedback
    short = score_question("technical", None, key, "gil process")  # keyword dump below min words -> capped
    assert short.points == 0.5
    assert score_question("practical", None, key, 42).status == "invalid"
