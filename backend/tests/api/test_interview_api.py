from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import InterviewAnswer, InterviewSession
from tests.career_data import JD, RESUME
from tests.guest_fixtures import Env

U = "/api/v1"
GOOD = ("First, Kafka orders messages only within a partition because each partition is an ordered log. "
        "Second, the message key is hashed to pick the partition, so for example the order id keeps one "
        "order's events in order. Then consumers in a consumer group read different partitions, so "
        "parallelism is bounded by partitions, and offsets track progress. The trade-off is overhead.")


def register(env: Env, email: str = "u@example.com") -> dict[str, str]:
    r = env.client.post(f"{U}/auth/register", json={"email": email, "password": "Str0ng-passw0rd", "display_name": "U"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def docs(env: Env, h: dict[str, str]) -> tuple[str, str]:
    r = env.client.post(f"{U}/documents", headers=h, data={"kind": "resume", "text": RESUME}).json()["document_id"]
    j = env.client.post(f"{U}/documents", headers=h, data={"kind": "job_description", "text": JD}).json()["document_id"]
    return r, j


def test_interview_requires_registered_user(env: Env) -> None:
    guest, _ = env.new_guest()
    for method, path in (("get", "/interview/topics"), ("post", "/interview/prepare"),
                         ("post", "/interview/mock"), ("get", "/interview/mock")):
        assert getattr(env.client, method)(f"{U}{path}").status_code == 401
        assert getattr(env.client, method)(f"{U}{path}", headers=guest).status_code == 401


def test_topics_listing(env: Env) -> None:
    h = register(env)
    body = env.client.get(f"{U}/interview/topics", headers=h).json()
    assert "kafka" in body["topics"] and "behavioural" in body["kinds"] and len(body["kinds"]) == 8


def test_prepare_returns_personalised_full_questions(env: Env) -> None:
    h = register(env)
    rid, jid = docs(env, h)
    r = env.client.post(f"{U}/interview/prepare", headers=h, json={
        "kinds": ["technical", "behavioural", "engineering_leadership"], "count": 9,
        "resume_document_id": rid, "job_description_document_id": jid})
    assert r.status_code == 200
    body = r.json()
    assert len(body["questions"]) == 9 and {q["kind"] for q in body["questions"]} == {
        "technical", "behavioural", "engineering_leadership"}
    q = body["questions"][0]
    assert q["model_answer"] and q["key_points"] and q["follow_ups"] and q["evaluation_criteria"] and q["practical_example"]
    assert body["focus_areas"]  # kubernetes/other required skills with bank topics -> something to practise
    assert any("job" in x["reason"].lower() for x in body["questions"])


def test_prepare_without_documents_and_validation(env: Env) -> None:
    h = register(env)
    assert env.client.post(f"{U}/interview/prepare", headers=h, json={"kinds": ["hr"], "count": 3}).status_code == 200
    for bad in ({"kinds": []}, {"kinds": ["astrology"]}, {"kinds": ["hr"], "count": 0}, {"kinds": ["hr"], "count": 500}):
        assert env.client.post(f"{U}/interview/prepare", headers=h, json=bad).status_code == 422


def test_prepare_report_download(env: Env) -> None:
    h = register(env)
    r = env.client.post(f"{U}/interview/prepare", headers=h, json={"kinds": ["technical"], "count": 3, "report_format": "pdf"}).json()
    dl = env.client.get(f"{U}/reports/{r['report_id']}/download", headers=h)
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF-")


def test_prepare_rejects_foreign_documents(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    rid, jid = docs(env, a)
    r = env.client.post(f"{U}/interview/prepare", headers=b, json={
        "kinds": ["technical"], "resume_document_id": rid, "job_description_document_id": jid})
    assert r.status_code == 404


def _start(env: Env, h: dict[str, str], **extra: object) -> dict:  # type: ignore[type-arg]
    r = env.client.post(f"{U}/interview/mock", headers=h, json={"kinds": ["technical"], "topics": ["kafka"], "count": 2, **extra})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def test_mock_interview_full_flow(env: Env) -> None:
    h = register(env)
    s = _start(env, h)
    assert s["status"] == "in_progress" and len(s["questions"]) == 2
    assert all("model_answer" not in q and "key_points" not in q for q in s["questions"])  # hidden until answered
    qid = s["questions"][0]["id"]
    r = env.client.post(f"{U}/interview/mock/{s['session_id']}/answers", headers=h, json={"question_id": qid, "answer": GOOD})
    assert r.status_code == 200
    fb = r.json()["feedback"]
    assert fb["model_answer"] and fb["overall_score"] > 50 and {d["name"] for d in fb["dimensions"]} >= {
        "technical_accuracy", "communication", "clarity", "problem_solving", "structured_thinking"}
    qid2 = s["questions"][1]["id"]
    env.client.post(f"{U}/interview/mock/{s['session_id']}/answers", headers=h, json={"question_id": qid2, "answer": "Not sure."})
    done = env.client.post(f"{U}/interview/mock/{s['session_id']}/complete", headers=h).json()
    assert done["answered"] == 2 and done["unanswered"] == 0 and 0 < done["overall_score"] < fb["overall_score"]
    assert done["weakest_dimensions"] and done["recommendations"] and "heuristic" in done["disclaimer"].lower()
    got = env.client.get(f"{U}/interview/mock/{s['session_id']}", headers=h).json()
    assert got["status"] == "completed" and set(got["answered_question_ids"]) == {qid, qid2}
    assert len(env.client.get(f"{U}/interview/mock", headers=h).json()) == 1
    assert env.db.query(InterviewAnswer).count() == 2


def test_mock_answer_rules(env: Env) -> None:
    h = register(env)
    s = _start(env, h)
    sid, qid = s["session_id"], s["questions"][0]["id"]
    url = f"{U}/interview/mock/{sid}/answers"
    assert env.client.post(url, headers=h, json={"question_id": qid, "answer": GOOD}).status_code == 200
    assert env.client.post(url, headers=h, json={"question_id": qid, "answer": GOOD}).status_code == 422  # once only
    assert env.client.post(url, headers=h, json={"question_id": "hr-1", "answer": "x"}).status_code == 404  # not in session
    assert env.client.post(url, headers=h, json={"question_id": qid, "answer": ""}).status_code == 422
    assert env.client.post(url, headers=h, json={"question_id": qid, "answer": "x" * 5001}).status_code == 422
    env.client.post(f"{U}/interview/mock/{sid}/complete", headers=h)
    other = s["questions"][1]["id"]
    assert env.client.post(url, headers=h, json={"question_id": other, "answer": GOOD}).status_code == 422  # completed


def test_complete_requires_an_answer(env: Env) -> None:
    h = register(env)
    s = _start(env, h)
    assert env.client.post(f"{U}/interview/mock/{s['session_id']}/complete", headers=h).status_code == 422


def test_mock_sessions_are_private(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    s = _start(env, a)
    sid, qid = s["session_id"], s["questions"][0]["id"]
    assert env.client.get(f"{U}/interview/mock/{sid}", headers=b).status_code == 404
    assert env.client.post(f"{U}/interview/mock/{sid}/answers", headers=b, json={"question_id": qid, "answer": GOOD}).status_code == 404
    assert env.client.post(f"{U}/interview/mock/{sid}/complete", headers=b).status_code == 404
    assert env.client.get(f"{U}/interview/mock", headers=b).json() == []
    assert env.client.get(f"{U}/interview/mock/{uuid.uuid4()}", headers=a).status_code == 404


def test_account_deletion_removes_interview_data(env: Env) -> None:
    h = register(env)
    s = _start(env, h)
    env.client.post(f"{U}/interview/mock/{s['session_id']}/answers", headers=h,
                    json={"question_id": s["questions"][0]["id"], "answer": GOOD})
    assert env.db.scalar(select(InterviewAnswer)) is not None
    r = env.client.request("DELETE", f"{U}/users/me", headers=h, json={"password": "Str0ng-passw0rd", "confirm": True})
    assert r.status_code == 204
    assert env.db.scalar(select(InterviewAnswer)) is None and env.db.scalar(select(InterviewSession)) is None
