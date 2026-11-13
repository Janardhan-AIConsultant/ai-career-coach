"""Acceptance tests: the five guest services work with NO login; registered users get the same
services with saved history; ownership isolation holds for both."""

from __future__ import annotations

import io
import uuid

import pymupdf
from docx import Document as DocxDocument
from sqlalchemy import select

from app.api.dependencies import get_llm
from app.models import CareerAnalysis, Report, Resume, SkillGapAnalysis
from tests.career_data import HOSTILE_RESUME, JD, RESUME
from tests.guest_fixtures import Env
from tests.helpers import make_pdf

G = "/api/v1/guest"
U = "/api/v1"


def guest_with_docs(env: Env, resume: str = RESUME) -> tuple[dict[str, str], str, str]:
    h, _ = env.new_guest()
    rid = env.upload_text(h, "resume", resume)["document_id"]
    jid = env.upload_text(h, "job_description", JD)["document_id"]
    return h, rid, jid


def user_with_docs(env: Env, email: str = "u@example.com") -> tuple[dict[str, str], str, str]:
    token = env.client.post(f"{U}/auth/register", json={
        "email": email, "password": "Str0ng-passw0rd", "display_name": "U"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    rid = env.client.post(f"{U}/documents", headers=h, data={"kind": "resume", "text": RESUME}).json()["document_id"]
    jid = env.client.post(f"{U}/documents", headers=h, data={"kind": "job_description", "text": JD}).json()["document_id"]
    return h, rid, jid


# ---------------------------------------------------------------- five guest services, no login
def test_all_five_guest_services_work_without_login(env: Env) -> None:
    h, rid, jid = guest_with_docs(env)
    assert "authorization" not in {k.lower() for k in h}  # only the guest capability token

    r = env.client.post(f"{G}/resume/analyze", headers=h, json={"document_id": rid})
    assert r.status_code == 200 and r.json()["analysis"]["years_of_experience"] == 10.0

    r = env.client.post(f"{G}/job-description/analyze", headers=h, json={"document_id": jid})
    assert r.status_code == 200 and r.json()["analysis"]["title"] == "Senior Backend Engineer"
    assert "kubernetes" in r.json()["analysis"]["mandatory_skills"]

    pair = {"resume_document_id": rid, "job_description_document_id": jid}
    r = env.client.post(f"{G}/career/match", headers=h, json=pair)
    body = r.json()
    assert r.status_code == 200 and 0 < body["match"]["overall_score"] <= 100
    assert "not an official ATS score" in body["match"]["disclaimer"] and body["narrative"] is None

    r = env.client.post(f"{G}/career/skill-gap", headers=h, json={**pair, "declared_absent_skills": ["kubernetes"]})
    gaps = {g["skill"]: g for g in r.json()["analysis"]["gaps"]}
    assert r.status_code == 200 and gaps["kubernetes"]["status"] == "confirmed_absent"
    assert gaps["terraform"]["status"] == "not_evidenced"

    r = env.client.post(f"{G}/resume/optimize", headers=h, json=pair)
    out = r.json()["result"]
    assert r.status_code == 200 and set(out["pending_approval_ids"]) == {"summary-1", "skills-1"}
    assert "kubernetes" not in out["optimized_resume_text"].lower()


def test_optimize_approval_flow_via_api(env: Env) -> None:
    h, rid, jid = guest_with_docs(env)
    pair = {"resume_document_id": rid, "job_description_document_id": jid}
    r = env.client.post(f"{G}/resume/optimize", headers=h, json={
        **pair, "approved_change_ids": ["summary-1"], "confirmed_skills": ["Kubernetes"]}).json()["result"]
    assert "10-year professional" in r["optimized_resume_text"] and r["pending_approval_ids"] == ["skills-1"]
    r = env.client.post(f"{G}/resume/optimize", headers=h, json={
        **pair, "approved_change_ids": ["skills-1"], "confirmed_skills": ["Kubernetes"]}).json()["result"]
    assert "Kubernetes" in r["optimized_resume_text"]


def test_services_work_on_uploaded_pdf(env: Env) -> None:
    h, _ = env.new_guest()
    pdf_resume = "Skills\nPython, FastAPI\nExperience\nEngineer (2018 - 2022)\n- Built APIs"
    rid = env.client.post(f"{G}/documents", headers=h, data={"kind": "resume"},
                          files={"file": ("cv.pdf", make_pdf(pdf_resume), "application/pdf")}).json()["document_id"]
    r = env.client.post(f"{G}/resume/analyze", headers=h, json={"document_id": rid})
    assert r.status_code == 200 and "fastapi" in {s["skill"] for s in r.json()["analysis"]["technical_skills"]}


# ---------------------------------------------------------------- reports
def test_guest_downloads_pdf_and_docx_reports(env: Env) -> None:
    h, rid, jid = guest_with_docs(env)
    pair = {"resume_document_id": rid, "job_description_document_id": jid}
    pdf_id = env.client.post(f"{G}/career/match", headers=h, json={**pair, "report_format": "pdf"}).json()["report_id"]
    docx_id = env.client.post(f"{G}/resume/analyze", headers=h,
                              json={"document_id": rid, "report_format": "docx"}).json()["report_id"]
    pdf = env.client.get(f"{G}/reports/{pdf_id}/download", headers=h)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pymupdf.open(stream=pdf.content, filetype="pdf").page_count >= 1
    docx = env.client.get(f"{G}/reports/{docx_id}/download", headers=h)
    assert "wordprocessingml" in docx.headers["content-type"]
    assert any("Resume Analysis" in p.text for p in DocxDocument(io.BytesIO(docx.content)).paragraphs)
    assert len(env.client.get(f"{G}/reports", headers=h).json()) == 2
    # report ownership + auth
    other, _ = env.new_guest()
    assert env.client.get(f"{G}/reports/{pdf_id}/download", headers=other).status_code == 404
    assert env.client.get(f"{G}/reports/{pdf_id}/download").status_code == 401
    assert env.client.get(f"{G}/reports", headers=other).json() == []


def test_optimize_creates_change_report_and_resume_file(env: Env) -> None:
    h, rid, jid = guest_with_docs(env)
    r = env.client.post(f"{G}/resume/optimize", headers=h, json={
        "resume_document_id": rid, "job_description_document_id": jid, "report_format": "docx"}).json()
    assert r["report_id"] and r["optimized_resume_report_id"] and r["report_id"] != r["optimized_resume_report_id"]
    f = env.client.get(f"{G}/reports/{r['optimized_resume_report_id']}/download", headers=h)
    text = "\n".join(p.text for p in DocxDocument(io.BytesIO(f.content)).paragraphs)
    assert "Jane Doe" in text and "Maintained Kafka consumers" in text


def test_invalid_report_format_rejected(env: Env) -> None:
    h, rid, _ = guest_with_docs(env)
    r = env.client.post(f"{G}/resume/analyze", headers=h, json={"document_id": rid, "report_format": "xlsx"})
    assert r.status_code == 422


# ---------------------------------------------------------------- isolation
def test_guest_cannot_analyse_another_guests_documents(env: Env) -> None:
    a, a_rid, a_jid = guest_with_docs(env)
    b, _, b_jid = guest_with_docs(env)
    pair_a = {"resume_document_id": a_rid, "job_description_document_id": a_jid}
    for path, body in ((f"{G}/resume/analyze", {"document_id": a_rid}),
                       (f"{G}/job-description/analyze", {"document_id": a_jid}),
                       (f"{G}/career/match", pair_a), (f"{G}/career/skill-gap", pair_a),
                       (f"{G}/resume/optimize", pair_a)):
        assert env.client.post(path, headers=b, json=body).status_code == 404, path
    mixed = {"resume_document_id": a_rid, "job_description_document_id": b_jid}
    assert env.client.post(f"{G}/career/match", headers=b, json=mixed).status_code == 404
    assert env.client.post(f"{G}/career/match", headers=a, json={
        "resume_document_id": a_rid, "job_description_document_id": a_jid}).status_code == 200


def test_document_kind_mixups_and_unknown_ids_404(env: Env) -> None:
    h, rid, jid = guest_with_docs(env)
    assert env.client.post(f"{G}/job-description/analyze", headers=h, json={"document_id": rid}).status_code == 404
    assert env.client.post(f"{G}/resume/analyze", headers=h, json={"document_id": jid}).status_code == 404
    assert env.client.post(f"{G}/resume/analyze", headers=h, json={"document_id": str(uuid.uuid4())}).status_code == 404
    assert env.client.post(f"{G}/resume/analyze", headers=h, json={"document_id": "nope"}).status_code == 422


def test_services_require_auth(env: Env) -> None:
    rid = str(uuid.uuid4())
    for path in ("resume/analyze", "job-description/analyze"):
        assert env.client.post(f"{G}/{path}", json={"document_id": rid}).status_code == 401
        assert env.client.post(f"{U}/{path}", json={"document_id": rid}).status_code == 401
    h, _ = env.new_guest()  # a guest token is not a user credential
    assert env.client.post(f"{U}/resume/analyze", headers=h, json={"document_id": rid}).status_code == 401
    assert env.client.get(f"{U}/documents", headers=h).status_code == 401


def test_expired_guest_session_blocks_services(env: Env) -> None:
    from datetime import UTC, datetime, timedelta

    from app.models import GuestSession

    h, rid, _ = guest_with_docs(env)
    g = env.db.scalar(select(GuestSession))
    assert g is not None
    g.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    env.db.commit()
    assert env.client.post(f"{G}/resume/analyze", headers=h, json={"document_id": rid}).status_code == 401


# ---------------------------------------------------------------- prompt injection
def test_hostile_resume_has_no_effect_and_is_flagged(env: Env) -> None:
    h, _ = env.new_guest()
    flagged = env.upload_text(h, "resume", HOSTILE_RESUME)
    assert flagged["injection_flagged"] is True
    jid = env.upload_text(h, "job_description", JD)["document_id"]
    clean_rid = env.upload_text(h, "resume", RESUME)["document_id"]
    pair = lambda r: {"resume_document_id": r, "job_description_document_id": jid}
    hostile = env.client.post(f"{G}/career/match", headers=h, json=pair(flagged["document_id"])).json()
    clean = env.client.post(f"{G}/career/match", headers=h, json=pair(clean_rid)).json()
    assert hostile["match"]["overall_score"] == clean["match"]["overall_score"]


# ---------------------------------------------------------------- registered users
def test_registered_user_services_persist_history_and_reports(env: Env) -> None:
    h, rid, jid = user_with_docs(env)
    pair = {"resume_document_id": rid, "job_description_document_id": jid}
    assert env.client.post(f"{U}/resume/analyze", headers=h, json={"document_id": rid}).status_code == 200
    assert env.client.post(f"{U}/job-description/analyze", headers=h, json={"document_id": jid}).status_code == 200
    m = env.client.post(f"{U}/career/match", headers=h, json={**pair, "report_format": "pdf"}).json()
    assert env.client.post(f"{U}/career/skill-gap", headers=h, json=pair).status_code == 200
    assert env.client.post(f"{U}/resume/optimize", headers=h, json=pair).status_code == 200

    resume = env.db.scalar(select(Resume))
    assert resume is not None and resume.analysis and resume.owner_user_id is not None
    ca = env.db.scalar(select(CareerAnalysis))
    assert ca is not None and ca.overall_score == m["match"]["overall_score"] and ca.scoring_version == "v1"
    assert env.db.scalar(select(SkillGapAnalysis)) is not None
    rep = env.db.scalar(select(Report))
    assert rep is not None and rep.owner_user_id is not None and rep.expires_at is None  # no guest expiry
    assert env.client.get(f"{U}/reports/{m['report_id']}/download", headers=h).status_code == 200
    assert len(env.client.get(f"{U}/reports", headers=h).json()) == 1


def test_user_cannot_use_another_users_documents_or_reports(env: Env) -> None:
    a, a_rid, a_jid = user_with_docs(env, "a@example.com")
    b, _, _ = user_with_docs(env, "b@example.com")
    pair = {"resume_document_id": a_rid, "job_description_document_id": a_jid}
    assert env.client.post(f"{U}/career/match", headers=b, json=pair).status_code == 404
    rid = env.client.post(f"{U}/career/match", headers=a, json={**pair, "report_format": "pdf"}).json()["report_id"]
    assert env.client.get(f"{U}/reports/{rid}/download", headers=b).status_code == 404
    assert env.client.delete(f"{U}/documents/{a_rid}", headers=b).status_code == 404
    assert env.client.get(f"{U}/documents", headers=b).json()[0]["document_id"] != a_rid
    assert env.client.delete(f"{U}/documents/{a_rid}", headers=a).status_code == 204


# ---------------------------------------------------------------- optional LLM narrative
def test_narrative_only_when_requested_and_llm_available(env: Env) -> None:
    class Fake:
        calls = 0

        def invoke(self, system: str, user: str) -> str:
            Fake.calls += 1
            return "A concise, grounded summary."

    env.client.app.dependency_overrides[get_llm] = lambda: Fake()  # type: ignore[attr-defined]
    h, rid, jid = guest_with_docs(env)
    pair = {"resume_document_id": rid, "job_description_document_id": jid}
    assert env.client.post(f"{G}/career/match", headers=h, json=pair).json()["narrative"] is None
    assert Fake.calls == 0  # off by default: no LLM cost
    r = env.client.post(f"{G}/career/match", headers=h, json={**pair, "include_narrative": True}).json()
    assert r["narrative"] == "A concise, grounded summary." and Fake.calls == 1
    # the numeric score never depends on the LLM
    assert r["match"]["overall_score"] == env.client.post(f"{G}/career/match", headers=h, json=pair).json()["match"]["overall_score"]
