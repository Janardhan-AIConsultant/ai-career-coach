from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.assessments.bank import BY_SLUG
from app.models import Assessment, AssessmentAttempt, AssessmentQuestion, LearningRoadmap
from app.services.assessment_service import seed_assessments
from tests.career_data import JD, RESUME
from tests.guest_fixtures import Env

U = "/api/v1"
PW = "Str0ng-passw0rd"
ROOT = Path(__file__).resolve().parents[3]


def register(env: Env, email: str = "u@example.com") -> dict[str, str]:
    r = env.client.post(f"{U}/auth/register", json={"email": email, "password": PW, "display_name": "U"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def create(env: Env, h: dict[str, str], days: int = 7, **extra: Any):  # type: ignore[no-untyped-def]
    body = {"duration_days": days, "goal": "Become a stronger python and kafka engineer", **extra}
    return env.client.post(f"{U}/learning/roadmaps", headers=h, json=body)


def perfect(slug: str, detail: dict[str, Any]) -> dict[str, Any]:
    bank = {q["prompt"]: q for q in BY_SLUG[slug]["questions"]}
    out: dict[str, Any] = {}
    for q in detail["questions"]:
        k = bank[q["prompt"]]
        if k["type"] in ("mcq", "multi_select"):
            out[q["id"]] = k["correct"]
        elif k["type"] == "scenario":
            out[q["id"]] = int(max(k["correct"]["scores"].items(), key=lambda kv: kv[1])[0])
        else:
            out[q["id"]] = " ".join(w for p in k["correct"]["key_points"] for w in p["keywords"][:1]) + " " + "filler " * 40
    return out


def submit(env: Env, h: dict[str, str], slug: str, answers: dict[str, Any], **extra: Any):  # type: ignore[no-untyped-def]
    return env.client.post(f"{U}/assessments/{slug}/attempts", headers=h, json={"answers": answers, **extra})


# ---------------------------------------------------------------- access
def test_learning_requires_registered_user(env: Env) -> None:
    guest, _ = env.new_guest()
    for method, path in (("get", "/learning/roadmaps"), ("post", "/learning/roadmaps"),
                         ("get", "/assessments"), ("get", "/learning/dashboard")):
        assert getattr(env.client, method)(f"{U}{path}").status_code == 401
        assert getattr(env.client, method)(f"{U}{path}", headers=guest).status_code == 401


# ---------------------------------------------------------------- ONLY 7 / 15 / 60
def test_only_supported_durations_accepted() -> None:
    from tests.guest_fixtures import build_env

    env = next(build_env())
    h = register(env)
    for days in (7, 15, 60):
        r = create(env, h, days)
        assert r.status_code == 201 and r.json()["duration_days"] == days and r.json()["title"].startswith(f"{days}-day")
    for bad in (0, 1, 3, 14, 30, 45, 90, 365, -7, "30", "custom", None, 7.5):
        r = create(env, h, bad)  # type: ignore[arg-type]
        assert r.status_code == 422, bad
    assert env.db.query(LearningRoadmap).count() == 3  # nothing created for rejected values


def test_openapi_only_advertises_supported_durations(env: Env) -> None:
    spec = env.client.get("/openapi.json").json()
    enum = spec["components"]["schemas"]["RoadmapCreateIn"]["properties"]["duration_days"]["enum"]
    assert enum == [7, 15, 60]
    out_enum = spec["components"]["schemas"]["RoadmapOut"]["properties"]["duration_days"]["enum"]
    assert out_enum == [7, 15, 60]
    text = str(spec).lower()
    assert not re.search(r"\b30[- ]?day", text) and "custom roadmap" not in text


def test_docs_and_code_never_mention_unsupported_roadmaps() -> None:
    """Scan README/docs/source/seed data for unsupported-roadmap wording."""
    forbidden = re.compile(r"\b(30|45|90)[- ]?day roadmap|custom roadmap|custom duration|30-day", re.IGNORECASE)
    files = [*ROOT.glob("docs/*.md"), ROOT / "README.md", *(ROOT / "backend" / "app").rglob("*.py")]
    # docs may state the exclusion rule itself; only flag affirmative offers
    offenders = []
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.search(line) and not re.search(r"\b(never|not|only|no |unsupported|do not|except|reject)", line, re.IGNORECASE):
                offenders.append(f"{f.name}:{n}")
    assert offenders == []


# ---------------------------------------------------------------- generation
def test_roadmap_structure_from_goal(env: Env) -> None:
    h = register(env)
    r = create(env, h, 15).json()
    assert r["status"] == "not_started" and r["estimated_hours"] > 0
    titles = [m["title"] for m in r["modules"]]
    assert "Python" in titles and "Kafka" in titles and titles[-1] == "Capstone project"
    mod = r["modules"][0]
    assert mod["objectives"] and mod["topics"] and mod["activities"]
    a = mod["activities"][0]
    assert a["description"] and a["resources"] and a["estimated_minutes"] and a["completed_at"] is None
    assert r["completion_criteria"]["min_required_activity_percent"] == 80
    assert any(x["ref"] == "assessment:python-fundamentals" for m in r["modules"] for x in m["activities"])
    assert r["progress"]["percent_required_complete"] == 0 and not r["progress"]["criteria_met"]


def test_roadmap_from_skill_gaps(env: Env) -> None:
    h = register(env)
    rid = env.client.post(f"{U}/documents", headers=h, data={"kind": "resume", "text": RESUME}).json()["document_id"]
    jid = env.client.post(f"{U}/documents", headers=h, data={"kind": "job_description", "text": JD}).json()["document_id"]
    r = create(env, h, 60, resume_document_id=rid, job_description_document_id=jid, goal="Land the senior backend role").json()
    titles = {m["title"].lower() for m in r["modules"]}
    assert {"kubernetes", "terraform"} & titles  # JD requirements the resume does not evidence
    first = r["modules"][0]["objectives"][0]
    assert "gap" in first.lower()
    assert len(r["modules"]) <= 11  # <=10 focus modules + capstone


def test_roadmap_source_validation(env: Env) -> None:
    h = register(env)
    rid = env.client.post(f"{U}/documents", headers=h, data={"kind": "resume", "text": RESUME}).json()["document_id"]
    assert create(env, h, 7, resume_document_id=rid).status_code == 422  # needs both documents or neither
    assert create(env, h, 7, goal="get better at everything").status_code == 422  # nothing to focus on
    assert create(env, h, 7, focus_skills=["underwater basket weaving"]).status_code == 422
    ok = create(env, h, 7, goal="grow", focus_skills=["Kafka", "mentoring", "System Design"])
    assert ok.status_code == 201 and {m["title"] for m in ok.json()["modules"]} == {"Kafka", "Mentoring", "System Design"}
    other = register(env, "b@example.com")
    jid = env.client.post(f"{U}/documents", headers=h, data={"kind": "job_description", "text": JD}).json()["document_id"]
    assert create(env, other, 7, resume_document_id=rid, job_description_document_id=jid).status_code == 404


def test_roadmap_limit(env: Env) -> None:
    h = register(env)
    for _ in range(10):
        assert create(env, h).status_code == 201
    assert create(env, h).status_code == 429


# ---------------------------------------------------------------- progress
def test_start_complete_reopen_and_resume(env: Env) -> None:
    h = register(env)
    r = create(env, h, 7, goal="learn well", focus_skills=["python"]).json()
    rid = r["id"]
    acts = [a for m in r["modules"] for a in m["activities"]]
    learn = next(a for a in acts if a["kind"] == "learn")
    url = f"{U}/learning/roadmaps/{rid}/activities/{learn['id']}"
    assert env.client.post(f"{url}/complete", headers=h).status_code == 422  # not started yet
    started = env.client.post(f"{U}/learning/roadmaps/{rid}/start", headers=h).json()
    assert started["status"] == "in_progress" and started["started_at"]
    again = env.client.post(f"{U}/learning/roadmaps/{rid}/start", headers=h).json()
    assert again["started_at"] == started["started_at"]  # idempotent
    done = env.client.post(f"{url}/complete", headers=h).json()
    assert done["progress"]["completed_required"] == 1 and done["progress"]["percent_required_complete"] > 0
    assert all(a["id"] != learn["id"] for a in done["progress"]["next_activities"])  # "resume unfinished learning"
    reopened = env.client.post(f"{url}/reopen", headers=h).json()
    assert reopened["progress"]["completed_required"] == 0
    assessment = next(a for a in acts if a["kind"] == "assessment")
    r2 = env.client.post(f"{U}/learning/roadmaps/{rid}/activities/{assessment['id']}/complete", headers=h)
    assert r2.status_code == 422 and "passing the assessment" in r2.text


def test_roadmap_cannot_be_completed_by_clicking(env: Env) -> None:
    h = register(env)
    r = create(env, h, 7, goal="learn well", focus_skills=["python"]).json()
    rid = r["id"]
    env.client.post(f"{U}/learning/roadmaps/{rid}/start", headers=h)
    for m in r["modules"]:
        for a in m["activities"]:
            if a["kind"] != "assessment":
                env.client.post(f"{U}/learning/roadmaps/{rid}/activities/{a['id']}/complete", headers=h)
    mid = env.client.get(f"{U}/learning/roadmaps/{rid}", headers=h).json()
    assert mid["progress"]["percent_required_complete"] >= 80  # percentage alone is met...
    assert mid["status"] == "in_progress" and not mid["progress"]["criteria_met"]  # ...but not the assessment
    assert [q["name"] for q in mid["progress"]["requirements"] if not q["met"]] == ["Pass every assessment in the plan"]

    detail = env.client.get(f"{U}/assessments/python-fundamentals", headers=h).json()
    bad = submit(env, h, "python-fundamentals", {q["id"]: 0 if q["type"] == "mcq" else "no" for q in detail["questions"]}).json()
    assert not bad["passed"] and env.client.get(f"{U}/learning/roadmaps/{rid}", headers=h).json()["status"] == "in_progress"

    good = submit(env, h, "python-fundamentals", perfect("python-fundamentals", detail)).json()
    assert good["passed"] and good["score"] == 100.0 and good["roadmap_activities_completed"] == 1
    final = env.client.get(f"{U}/learning/roadmaps/{rid}", headers=h).json()
    assert final["status"] == "completed" and final["completed_at"] and final["progress"]["criteria_met"]
    assert env.client.post(f"{U}/learning/roadmaps/{rid}/start", headers=h).status_code == 422  # already completed


def test_passing_before_starting_does_not_complete_activity(env: Env) -> None:
    h = register(env)
    r = create(env, h, 7, goal="learn well", focus_skills=["python"]).json()
    detail = env.client.get(f"{U}/assessments/python-fundamentals", headers=h).json()
    out = submit(env, h, "python-fundamentals", perfect("python-fundamentals", detail)).json()
    assert out["passed"] and out["roadmap_activities_completed"] == 0
    assert env.client.get(f"{U}/learning/roadmaps/{r['id']}", headers=h).json()["progress"]["completed_required"] == 0


def test_roadmaps_are_private(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    r = create(env, a, 7, goal="learn well", focus_skills=["python"]).json()
    act = r["modules"][0]["activities"][0]["id"]
    for method, path in (("get", f"/learning/roadmaps/{r['id']}"), ("post", f"/learning/roadmaps/{r['id']}/start"),
                         ("post", f"/learning/roadmaps/{r['id']}/activities/{act}/complete"),
                         ("delete", f"/learning/roadmaps/{r['id']}")):
        assert getattr(env.client, method)(f"{U}{path}", headers=b).status_code == 404, path
    assert env.client.get(f"{U}/learning/roadmaps", headers=b).json() == []
    other = create(env, a, 7, goal="learn well", focus_skills=["kafka"]).json()
    wrong = other["modules"][0]["activities"][0]["id"]  # activity of another roadmap of the same user
    env.client.post(f"{U}/learning/roadmaps/{r['id']}/start", headers=a)
    assert env.client.post(f"{U}/learning/roadmaps/{r['id']}/activities/{wrong}/complete", headers=a).status_code == 404


def test_dashboard_delete_and_report(env: Env) -> None:
    h = register(env)
    r = create(env, h, 7, goal="learn well", focus_skills=["python"]).json()
    env.client.post(f"{U}/learning/roadmaps/{r['id']}/start", headers=h)
    dash = env.client.get(f"{U}/learning/dashboard", headers=h).json()
    assert dash["roadmaps"][0]["status"] == "in_progress" and dash["next_activities"] and dash["recent_attempts"] == []
    rep = env.client.post(f"{U}/learning/roadmaps/{r['id']}/report", headers=h, json={"report_format": "pdf"})
    assert rep.status_code == 201
    dl = env.client.get(f"{U}/reports/{rep.json()['report_id']}/download", headers=h)
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF-")
    assert env.client.post(f"{U}/learning/roadmaps/{r['id']}/report", headers=h, json={"report_format": "xlsx"}).status_code == 422
    assert env.client.delete(f"{U}/learning/roadmaps/{r['id']}", headers=h).status_code == 204
    assert env.client.get(f"{U}/learning/roadmaps", headers=h).json() == []
    assert env.client.get(f"{U}/learning/roadmaps/{r['id']}", headers=h).status_code == 404


# ---------------------------------------------------------------- assessments
def test_assessment_listing_seeding_and_no_answer_leak(env: Env) -> None:
    h = register(env)
    listing = env.client.get(f"{U}/assessments", headers=h).json()
    assert len(listing) == 6 and all(a["question_count"] == 6 and a["pass_score"] == 70 for a in listing)
    assert seed_assessments(env.db) == 0  # idempotent
    assert env.db.query(Assessment).count() == 6 and env.db.query(AssessmentQuestion).count() == 36
    detail = env.client.get(f"{U}/assessments/kafka-essentials", headers=h)
    raw = detail.text.lower()
    assert detail.status_code == 200 and "correct" not in raw and "explanation" not in raw and "key_points" not in raw
    assert {q["type"] for q in detail.json()["questions"]} >= {"mcq", "multi_select", "scenario", "technical"}
    assert env.client.get(f"{U}/assessments/nope", headers=h).status_code == 404


def test_server_side_scoring_ignores_client_scores(env: Env) -> None:
    h = register(env)
    detail = env.client.get(f"{U}/assessments/kafka-essentials", headers=h).json()
    empty = submit(env, h, "kafka-essentials", {}, score=100, passed=True).json()
    assert empty["score"] == 0 and not empty["passed"]  # injected score/passed fields are ignored
    assert all(r["status"] == "unanswered" for r in empty["results"])
    full = submit(env, h, "kafka-essentials", perfect("kafka-essentials", detail)).json()
    assert full["score"] == 100 and full["passed"]
    assert all(r["correct_answer"] and r["explanation"] for r in full["results"])  # revealed after submission


def test_partial_scoring_pass_mark_and_weights(env: Env) -> None:
    h = register(env)
    detail = env.client.get(f"{U}/assessments/kafka-essentials", headers=h).json()
    answers = perfect("kafka-essentials", detail)
    ids = [q["id"] for q in detail["questions"]]
    answers[ids[0]] = 0  # wrong mcq (1 point of 7)
    out = submit(env, h, "kafka-essentials", answers).json()
    assert out["score"] == 85.7 and out["passed"]  # 6 of 7 points (technical is worth 2)
    for i in ids[:5]:
        answers[i] = None
    low = submit(env, h, "kafka-essentials", answers).json()
    assert low["score"] < 70 and not low["passed"] and low["pass_score"] == 70


def test_malformed_answers_do_not_crash(env: Env) -> None:
    h = register(env)
    detail = env.client.get(f"{U}/assessments/kafka-essentials", headers=h).json()
    ids = [q["id"] for q in detail["questions"]]
    junk = {ids[0]: "text", ids[1]: [1, 2], ids[2]: {"a": 1}, ids[3]: "zzz", ids[4]: 99, ids[5]: 12}
    r = submit(env, h, "kafka-essentials", junk)
    assert r.status_code == 201 and r.json()["score"] == 0
    assert submit(env, h, "kafka-essentials", {str(uuid.uuid4()): 1}).status_code == 422
    assert submit(env, h, "kafka-essentials", {ids[5]: "x" * 5001}).status_code == 422
    assert submit(env, h, "kafka-essentials", {"not-a-uuid": 1}).status_code == 422


def test_attempt_limit_history_and_privacy(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    detail = env.client.get(f"{U}/assessments/python-fundamentals", headers=a).json()
    ok = perfect("python-fundamentals", detail)
    codes = [submit(env, a, "python-fundamentals", ok if i == 4 else {}).status_code for i in range(7)]
    assert codes == [201] * 5 + [429, 429]
    hist = env.client.get(f"{U}/assessments/attempts", headers=a).json()
    assert len(hist) == 5 and hist[0]["slug"] == "python-fundamentals" and sum(x["passed"] for x in hist) == 1
    assert len(env.client.get(f"{U}/assessments/attempts?slug=python-fundamentals&limit=2", headers=a).json()) == 2
    assert env.client.get(f"{U}/assessments/attempts", headers=b).json() == []
    attempt_id = hist[0]["attempt_id"]
    assert env.client.get(f"{U}/assessments/attempts/{attempt_id}", headers=a).json()["results"]
    assert env.client.get(f"{U}/assessments/attempts/{attempt_id}", headers=b).status_code == 404
    summary = next(x for x in env.client.get(f"{U}/assessments", headers=a).json() if x["slug"] == "python-fundamentals")
    assert summary["attempts"] == 5 and summary["best_score"] == 100
    assert submit(env, b, "python-fundamentals", ok).status_code == 201  # other users unaffected


def test_account_deletion_removes_learning_data(env: Env) -> None:
    h = register(env)
    create(env, h, 7, goal="learn well", focus_skills=["python"])
    submit(env, h, "python-fundamentals", {})
    assert env.db.query(AssessmentAttempt).count() == 1
    r = env.client.request("DELETE", f"{U}/users/me", headers=h, json={"password": PW, "confirm": True})
    assert r.status_code == 204
    assert env.db.scalar(select(LearningRoadmap)) is None and env.db.scalar(select(AssessmentAttempt)) is None
