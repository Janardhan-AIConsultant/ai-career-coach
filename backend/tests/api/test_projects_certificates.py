from __future__ import annotations

import unicodedata
import uuid
from typing import Any

import pymupdf
import segno
from sqlalchemy import select

from app.api.routes.projects import get_repo_fetcher
from app.core.exceptions import ServiceBusyError
from app.core.security import create_access_token
from app.models import AuditLog, Certificate, ProjectEvaluation, ProjectSubmission, User
from app.projects.catalog import BY_ID
from tests.api.test_learning_api import create as create_roadmap
from tests.api.test_learning_api import perfect
from tests.career_data import JD, RESUME
from tests.conftest import make_user
from tests.guest_fixtures import Env
from tests.project_data import FakeFetcher, good_readme, ideal_evidence, poor_evidence

U = "/api/v1"
PW = "Str0ng-passw0rd"
RAG = BY_ID["rag-qa-api"]


def register(env: Env, email: str = "u@example.com") -> dict[str, str]:
    r = env.client.post(f"{U}/auth/register", json={"email": email, "password": PW, "display_name": "Jane Learner"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_headers(env: Env) -> dict[str, str]:
    admin = make_user(env.db, "admin@example.com", role="admin")
    token = create_access_token(admin.id, "j" * 40, 30)  # "j" * 40 is the JWT secret of the `env` fixture
    return {"Authorization": f"Bearer {token}"}


def use_fetcher(env: Env, fetcher: Any) -> None:
    env.client.app.dependency_overrides[get_repo_fetcher] = lambda: fetcher  # type: ignore[attr-defined]


def submit_project(env: Env, h: dict[str, str], repo: str = "https://github.com/acme/demo", **extra: Any):  # type: ignore[no-untyped-def]
    return env.client.post(f"{U}/projects/submissions", headers=h, json={"template_id": "rag-qa-api", "repo_url": repo, **extra})


def passed_project(env: Env, h: dict[str, str], repo: str = "https://github.com/acme/demo") -> dict[str, Any]:
    use_fetcher(env, FakeFetcher(ideal_evidence(RAG)))
    sid = submit_project(env, h, repo).json()["id"]
    r = env.client.post(f"{U}/projects/submissions/{sid}/evaluate", headers=h)
    assert r.status_code == 200 and r.json()["latest_evaluation"]["passed"], r.text
    return r.json()  # type: ignore[no-any-return]


def passed_assessment(env: Env, h: dict[str, str], slug: str = "python-fundamentals") -> dict[str, Any]:
    detail = env.client.get(f"{U}/assessments/{slug}", headers=h).json()
    r = env.client.post(f"{U}/assessments/{slug}/attempts", headers=h, json={"answers": perfect(slug, detail)})
    assert r.json()["passed"]
    return r.json()  # type: ignore[no-any-return]


def completed_roadmap(env: Env, h: dict[str, str]) -> str:
    r = create_roadmap(env, h, 7, goal="learn well", focus_skills=["python"]).json()
    env.client.post(f"{U}/learning/roadmaps/{r['id']}/start", headers=h)
    for m in r["modules"]:
        for a in m["activities"]:
            if a["kind"] != "assessment":
                env.client.post(f"{U}/learning/roadmaps/{r['id']}/activities/{a['id']}/complete", headers=h)
    passed_assessment(env, h)
    assert env.client.get(f"{U}/learning/roadmaps/{r['id']}", headers=h).json()["status"] == "completed"
    return r["id"]  # type: ignore[no-any-return]


def issue(env: Env, h: dict[str, str], ctype: str, source: str, **extra: Any):  # type: ignore[no-untyped-def]
    return env.client.post(f"{U}/certificates", headers=h, json={"certificate_type": ctype, "source_id": source, **extra})


def pdf_text(data: bytes) -> str:
    doc = pymupdf.open(stream=data, filetype="pdf")
    return " ".join(unicodedata.normalize("NFKC", "\n".join(str(doc.load_page(i).get_text()) for i in range(doc.page_count))).split())


# =============================================================== projects
def test_projects_require_registered_user(env: Env) -> None:
    guest, _ = env.new_guest()
    for path in ("/projects/catalog", "/projects/submissions", "/certificates", "/certificates/eligibility"):
        assert env.client.get(f"{U}{path}").status_code == 401
        assert env.client.get(f"{U}{path}", headers=guest).status_code == 401


def test_catalog_and_recommendations(env: Env) -> None:
    h = register(env)
    cat = env.client.get(f"{U}/projects/catalog", headers=h).json()
    assert len(cat) >= 6 and {"requirements", "expected_outcomes", "technologies", "milestones", "description"} <= set(cat[0])
    rid = create_roadmap(env, h, 15, goal="learn well", focus_skills=["kafka", "rag"]).json()["id"]
    recs = env.client.get(f"{U}/projects/recommendations?roadmap_id={rid}", headers=h).json()
    assert {recs[0]["template"]["id"], recs[1]["template"]["id"]} == {"rag-qa-api", "event-driven-orders"}
    assert recs[0]["matched_skills"] and "Practises your focus areas" in recs[0]["reason"]
    assert env.client.get(f"{U}/projects/recommendations?roadmap_id={uuid.uuid4()}", headers=h).status_code == 404
    doc = env.client.post(f"{U}/documents", headers=h, data={"kind": "resume", "text": RESUME}).json()["document_id"]
    jd = env.client.post(f"{U}/documents", headers=h, data={"kind": "job_description", "text": JD}).json()["document_id"]
    by_gap = env.client.get(f"{U}/projects/recommendations?resume_document_id={doc}&job_description_document_id={jd}", headers=h).json()
    assert by_gap[0]["matched_skills"]  # kubernetes/terraform/rabbitmq gaps -> cloud/event projects
    assert env.client.get(f"{U}/projects/recommendations?resume_document_id={doc}", headers=h).status_code == 422


def test_submission_validation(env: Env) -> None:
    h = register(env)
    use_fetcher(env, FakeFetcher(ideal_evidence(RAG)))
    post = lambda **b: env.client.post(f"{U}/projects/submissions", headers=h, json=b)
    assert post(template_id="nope", repo_url="https://github.com/a/b").status_code == 404
    assert post(template_id="rag-qa-api").status_code == 422  # needs repo or docs
    assert post(template_id="rag-qa-api", documentation_text="only docs").status_code == 422  # code project needs repo
    for bad in ("http://github.com/a/b", "https://evil.example/a/b", "https://github.com/a/b/tree/x", "file:///etc/passwd"):
        assert post(template_id="rag-qa-api", repo_url=bad).status_code == 422, bad
    assert post(template_id="rag-qa-api", repo_url="https://github.com/a/b", documentation_url="http://x.example").status_code == 422
    ok = post(template_id="team-playbook", documentation_text=good_readme(BY_ID["team-playbook"]))
    assert ok.status_code == 201 and ok.json()["status"] == "submitted"
    assert FakeFetcher.__name__ and env.db.query(ProjectSubmission).count() == 1


def test_evaluation_pass_and_fail_flows(env: Env) -> None:
    h = register(env)
    use_fetcher(env, FakeFetcher(poor_evidence()))
    sid = submit_project(env, h, "https://github.com/acme/poor").json()["id"]
    r = env.client.post(f"{U}/projects/submissions/{sid}/evaluate", headers=h).json()
    assert r["status"] == "needs_work" and not r["latest_evaluation"]["passed"]
    ev = r["latest_evaluation"]
    assert ev["code_executed"] is False and "NOT executed" in ev["details"]["disclaimer"] and ev["details"]["improvements"]
    use_fetcher(env, FakeFetcher(ideal_evidence(RAG)))
    r2 = env.client.post(f"{U}/projects/submissions/{sid}/evaluate", headers=h).json()
    assert r2["status"] == "passed" and r2["latest_evaluation"]["overall_score"] > ev["overall_score"]
    assert {c["name"] for c in r2["latest_evaluation"]["details"]["criteria"]} == {
        "requirement_coverage", "architecture", "code_quality", "documentation", "testing", "completeness"}
    assert all(e.code_executed is False for e in env.db.scalars(select(ProjectEvaluation)).all())


def test_evaluation_limits_and_upstream_errors(env: Env) -> None:
    h = register(env)
    use_fetcher(env, FakeFetcher(ideal_evidence(RAG)))
    sid = submit_project(env, h).json()["id"]
    assert [env.client.post(f"{U}/projects/submissions/{sid}/evaluate", headers=h).status_code for _ in range(4)] == [200, 200, 200, 429]
    sid2 = submit_project(env, h, "https://github.com/acme/other").json()["id"]
    use_fetcher(env, FakeFetcher(ServiceBusyError("GitHub is temporarily unavailable")))
    r = env.client.post(f"{U}/projects/submissions/{sid2}/evaluate", headers=h)
    assert r.status_code == 503 and "token" not in r.text.lower()
    assert env.db.query(ProjectEvaluation).filter(ProjectEvaluation.submission_id == uuid.UUID(sid2)).count() == 0


def test_same_repo_cannot_be_reused_by_another_learner(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    passed_project(env, a, "https://github.com/acme/shared")
    r = submit_project(env, b, "https://github.com/Acme/Shared.git")
    assert r.status_code == 409 and "already been submitted" in r.json()["error"]["message"]
    assert submit_project(env, a, "https://github.com/acme/shared").status_code == 201  # owner may resubmit
    assert submit_project(env, b, "https://github.com/acme/different").status_code == 201


def test_submissions_are_private(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    use_fetcher(env, FakeFetcher(ideal_evidence(RAG)))
    sid = submit_project(env, a).json()["id"]
    for method, path in (("get", f"/projects/submissions/{sid}"), ("post", f"/projects/submissions/{sid}/evaluate"),
                         ("delete", f"/projects/submissions/{sid}")):
        assert getattr(env.client, method)(f"{U}{path}", headers=b).status_code == 404
    assert env.client.get(f"{U}/projects/submissions", headers=b).json() == []
    assert env.client.delete(f"{U}/projects/submissions/{sid}", headers=a).status_code == 204
    assert env.client.get(f"{U}/projects/submissions", headers=a).json() == []


# =============================================================== certificates: evidence required
def test_no_certificate_without_verified_evidence(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    for ctype in ("learning_completion", "assessment", "project_completion"):
        assert issue(env, a, ctype, str(uuid.uuid4())).status_code == 404  # unknown evidence
    # roadmap exists but is not completed -> refused even though the user "clicks"
    r = create_roadmap(env, a, 7, goal="learn well", focus_skills=["python"]).json()
    assert issue(env, a, "learning_completion", r["id"]).status_code == 422
    env.client.post(f"{U}/learning/roadmaps/{r['id']}/start", headers=a)
    assert issue(env, a, "learning_completion", r["id"]).status_code == 422
    # failed attempt
    failed = env.client.post(f"{U}/assessments/python-fundamentals/attempts", headers=a, json={"answers": {}}).json()
    assert not failed["passed"] and issue(env, a, "assessment", failed["attempt_id"]).status_code == 422
    # failed project
    use_fetcher(env, FakeFetcher(poor_evidence()))
    sid = submit_project(env, a, "https://github.com/acme/poor").json()["id"]
    ev_id = env.client.post(f"{U}/projects/submissions/{sid}/evaluate", headers=a).json()["latest_evaluation"]["id"]
    assert issue(env, a, "project_completion", ev_id).status_code == 422
    # someone else's evidence
    good = passed_assessment(env, b)
    assert issue(env, a, "assessment", good["attempt_id"]).status_code == 404
    assert env.db.query(Certificate).count() == 0
    # a client cannot smuggle in its own score/code/status
    ok = issue(env, b, "assessment", good["attempt_id"], score=100, status="valid", certificate_id="ACC-AAAA-AAAA-AAAA")
    assert ok.status_code == 201 and ok.json()["score"] == good["score"] and ok.json()["certificate_id"] != "ACC-AAAA-AAAA-AAAA"


def test_learning_completion_certificate(env: Env) -> None:
    h = register(env)
    rid = completed_roadmap(env, h)
    elig = env.client.get(f"{U}/certificates/eligibility", headers=h).json()
    assert {"certificate_type": "learning_completion", "source_id": rid} .items() <= next(
        i for i in elig if i["certificate_type"] == "learning_completion").items()
    r = issue(env, h, "learning_completion", rid, learner_name="Jane Q. Learner")
    assert r.status_code == 201
    c = r.json()
    import re

    assert re.fullmatch(r"ACC-[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){2}", c["certificate_id"])
    assert c["title"] == "Learning Completion Certificate" and c["learner_name"] == "Jane Q. Learner" and c["score"] is None
    assert c["verification_url"].endswith(f"/verify/{c['certificate_id']}") and "not an externally accredited" in c["notice"]
    assert issue(env, h, "learning_completion", rid).status_code == 409  # one per achievement
    assert not [i for i in env.client.get(f"{U}/certificates/eligibility", headers=h).json() if i["source_id"] == rid]
    assert env.db.query(AuditLog).filter(AuditLog.action == "certificate.issued").count() == 1


def test_assessment_certificate_uses_best_attempt_only_once(env: Env) -> None:
    h = register(env)
    first = passed_assessment(env, h)
    elig = [i for i in env.client.get(f"{U}/certificates/eligibility", headers=h).json() if i["certificate_type"] == "assessment"]
    assert len(elig) == 1 and elig[0]["score"] == 100
    c = issue(env, h, "assessment", first["attempt_id"]).json()
    assert c["score"] == 100 and c["topic"] == "Python Fundamentals" and c["title"] == "Assessment Certificate"
    second = passed_assessment(env, h)  # another passing attempt: same achievement
    assert issue(env, h, "assessment", second["attempt_id"]).status_code == 409


def test_project_certificate(env: Env) -> None:
    h = register(env)
    sub = passed_project(env, h)
    r = issue(env, h, "project_completion", sub["latest_evaluation"]["id"])
    assert r.status_code == 201 and r.json()["topic"] == "RAG question-answering API" and r.json()["score"] == sub["latest_evaluation"]["overall_score"]
    assert issue(env, h, "project_completion", sub["latest_evaluation"]["id"]).status_code == 409


def test_certificate_name_sanitised_and_defaulted(env: Env) -> None:
    h = register(env)
    ids = [passed_assessment(env, h, s)["attempt_id"] for s in ("python-fundamentals", "kafka-essentials", "postgresql-essentials")]
    assert issue(env, h, "assessment", ids[0]).json()["learner_name"] == "Jane Learner"  # default = display name
    assert issue(env, h, "assessment", ids[1], learner_name="  A\x00B\n<script>  C ").json()["learner_name"] == "A B script C"
    assert issue(env, h, "assessment", ids[2], learner_name="\x00\x01").status_code == 422
    assert issue(env, h, "assessment", ids[2], learner_name="x" * 81).status_code == 422


def test_daily_certificate_limit() -> None:
    from tests.guest_fixtures import build_env

    env = next(build_env(certificates_per_day=1))
    h = register(env)
    a, b = passed_assessment(env, h, "python-fundamentals"), passed_assessment(env, h, "kafka-essentials")
    assert issue(env, h, "assessment", a["attempt_id"]).status_code == 201
    assert issue(env, h, "assessment", b["attempt_id"]).status_code == 429


# =============================================================== verification
def _cert(env: Env, h: dict[str, str]) -> dict[str, Any]:
    return issue(env, h, "assessment", passed_assessment(env, h)["attempt_id"]).json()  # type: ignore[no-any-return]


def test_public_verification_valid_revoked_invalid(env: Env) -> None:
    h = register(env)
    c = _cert(env, h)
    code = c["certificate_id"]
    r = env.client.get(f"{U}/certificates/verify/{code}")  # no authentication at all
    body = r.json()
    assert r.status_code == 200 and body["status"] == "valid" and body["certificate"]["learner_name"] == "Jane Learner"
    assert body["certificate"]["topic"] == "Python Fundamentals" and "not an externally accredited" in body["notice"]
    dumped = r.text.lower()
    assert "u@example.com" not in dumped and "user_id" not in dumped and "password" not in dumped
    assert env.client.get(f"{U}/certificates/verify/{code.lower()}").json()["status"] == "valid"  # case-insensitive
    for bad in ("ACC-AAAA-AAAA-AAAA", "nonsense", "ACC-1234", "' OR 1=1 --", "ACC-IIII-LLLL-OOOO"):
        r = env.client.get(f"{U}/certificates/verify/{bad}")
        assert r.status_code == 404 and r.json()["status"] == "invalid" and r.json()["certificate"] is None, bad
    adm = admin_headers(env)
    rv = env.client.post(f"{U}/admin/certificates/{code}/revoke", headers=adm, json={"reason": "Issued in error"})
    assert rv.status_code == 200 and rv.json()["status"] == "revoked"
    after = env.client.get(f"{U}/certificates/verify/{code}")
    assert after.status_code == 200 and after.json()["status"] == "revoked" and after.json()["certificate"]["revoked_at"]
    assert "Issued in error" not in after.text  # the reason is internal


def test_verification_is_rate_limited() -> None:
    from tests.guest_fixtures import build_env

    env = next(build_env(verify_requests_per_minute=3))
    codes = [env.client.get(f"{U}/certificates/verify/ACC-AAAA-AAAA-AAA{i}").status_code for i in range(5)]
    assert codes == [404, 404, 404, 429, 429]


# =============================================================== revocation and audit
def test_revocation_is_admin_only_and_audited(env: Env) -> None:
    h = register(env)
    code = _cert(env, h)["certificate_id"]
    url = f"{U}/admin/certificates/{code}/revoke"
    body = {"reason": "Policy violation"}
    guest, _ = env.new_guest()
    assert env.client.post(url, json=body).status_code == 401
    assert env.client.post(url, headers=guest, json=body).status_code == 401
    assert env.client.post(url, headers=h, json=body).status_code == 403  # the owner is not an admin
    assert env.client.get(f"{U}/admin/certificates", headers=h).status_code == 403
    adm = admin_headers(env)
    assert env.client.post(url, headers=adm, json={"reason": "x"}).status_code == 422
    assert env.client.post(f"{U}/admin/certificates/ACC-ZZZZ-ZZZZ-ZZZZ/revoke", headers=adm, json=body).status_code == 404
    assert env.client.post(url, headers=adm, json=body).status_code == 200
    assert env.client.post(url, headers=adm, json=body).status_code == 409  # already revoked
    row = env.db.scalar(select(Certificate))
    assert row is not None and row.status == "revoked" and row.revoked_reason == "Policy violation" and row.revoked_at
    audit = env.db.scalars(select(AuditLog).where(AuditLog.action == "certificate.revoked")).all()
    assert len(audit) == 1 and audit[0].entity_id == code and audit[0].actor_user_id is not None
    assert "Policy violation" not in str(audit[0].details)
    assert len(env.client.get(f"{U}/admin/certificates", headers=adm).json()) == 1
    assert env.client.get(f"{U}/certificates/{code}/download", headers=h).status_code == 409  # revoked: no download


# =============================================================== PDF
def test_certificate_pdf_contents_and_ownership(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    good = passed_assessment(env, a)
    c = issue(env, a, "assessment", good["attempt_id"], learner_name="Zoë Müller-Ñ").json()
    r = env.client.get(f"{U}/certificates/{c['certificate_id']}/download", headers=a)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF-")
    assert "attachment" in r.headers["content-disposition"] and r.headers["x-content-type-options"] == "nosniff"
    text = pdf_text(r.content)
    for expected in ("AI CAREER COACH", "Certificate of Assessment", "Zoë Müller-Ñ", "Python Fundamentals", "Score: 100%",
                     f"Certificate ID: {c['certificate_id']}", c["verification_url"], "not an externally accredited"):
        assert expected in text, expected
    assert env.client.get(f"{U}/certificates/{c['certificate_id']}/download", headers=b).status_code == 404
    assert env.client.get(f"{U}/certificates/{c['certificate_id']}/download").status_code == 401
    assert env.client.get(f"{U}/certificates/ACC-AAAA-AAAA-AAAA/download", headers=a).status_code == 404


def test_certificate_pdf_has_qr_for_the_verification_url(env: Env) -> None:
    h = register(env)
    c = _cert(env, h)
    data = env.client.get(f"{U}/certificates/{c['certificate_id']}/download", headers=h).content
    page = pymupdf.open(stream=data, filetype="pdf").load_page(0)
    dark = sum(1 for row in segno.make(c["verification_url"], error="m").matrix for cell in row if cell)
    black_squares = [d for d in page.get_drawings() if d.get("fill") == (0.0, 0.0, 0.0)]
    assert dark > 100 and len(black_squares) >= 1  # one vector shape holding every dark module
    assert sum(len(d["items"]) for d in black_squares) >= dark


def test_other_certificate_types_render(env: Env) -> None:
    h = register(env)
    lc = issue(env, h, "learning_completion", completed_roadmap(env, h)).json()
    pc = issue(env, h, "project_completion", passed_project(env, h)["latest_evaluation"]["id"]).json()
    for c, label in ((lc, "Certificate of Learning Completion"), (pc, "Certificate of Project Completion")):
        text = pdf_text(env.client.get(f"{U}/certificates/{c['certificate_id']}/download", headers=h).content)
        assert label in text and c["certificate_id"] in text


# =============================================================== privacy
def test_account_deletion_removes_certificates_and_projects(env: Env) -> None:
    h = register(env)
    code = _cert(env, h)["certificate_id"]
    passed_project(env, h)
    assert env.client.get(f"{U}/certificates/verify/{code}").json()["status"] == "valid"
    r = env.client.request("DELETE", f"{U}/users/me", headers=h, json={"password": PW, "confirm": True})
    assert r.status_code == 204
    assert env.client.get(f"{U}/certificates/verify/{code}").status_code == 404  # erased
    assert env.db.query(Certificate).count() == 0 and env.db.query(ProjectSubmission).count() == 0
    assert env.db.query(ProjectEvaluation).count() == 0
    user = env.db.scalar(select(User))
    assert user is not None and user.display_name == "Deleted user"
