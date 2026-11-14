from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models import AuditLog, Portfolio, PortfolioAchievement, Report
from tests.api.test_projects_certificates import (
    admin_headers,
    completed_roadmap,
    issue,
    passed_assessment,
    passed_project,
    pdf_text,
    register,
)
from tests.guest_fixtures import Env

U = "/api/v1"


def publish(env: Env, h: dict[str, str], name: str = "Jane L.", **extra: Any):  # type: ignore[no-untyped-def]
    return env.client.put(f"{U}/portfolio/settings", headers=h, json={
        "visibility": "public", "consent_public": True, "display_name": name, **extra})


def full_portfolio(env: Env, h: dict[str, str]) -> dict[str, Any]:
    """One of each achievement kind."""
    completed_roadmap(env, h)  # roadmap + python assessment attempt
    cert = issue(env, h, "assessment", passed_assessment(env, h, "kafka-essentials")["attempt_id"]).json()
    passed_project(env, h)
    return {"cert": cert, "view": env.client.get(f"{U}/portfolio", headers=h).json()}


def public(env: Env, slug: str):  # type: ignore[no-untyped-def]
    return env.client.get(f"{U}/portfolio/public/{slug}")


# ---------------------------------------------------------------- access
def test_owner_routes_require_a_user_token(env: Env) -> None:
    guest, _ = env.new_guest()
    for method, path in (("get", "/portfolio"), ("put", "/portfolio/settings"), ("get", "/portfolio/linkedin-summary"),
                         ("get", "/portfolio/resume-section"), ("post", "/portfolio/report"), ("post", "/portfolio/rotate-slug")):
        assert getattr(env.client, method)(f"{U}{path}").status_code == 401, path
        assert getattr(env.client, method)(f"{U}{path}", headers=guest).status_code == 401, path


def test_new_portfolio_is_private_and_empty(env: Env) -> None:
    h = register(env)
    p = env.client.get(f"{U}/portfolio", headers=h).json()
    assert p["settings"]["visibility"] == "private" and p["settings"]["public_url"] is None
    assert p["timeline"] == [] and p["skills"] == [] and p["stats"]["certificates"] == 0
    assert "NOT professional employment experience" in p["disclaimer"]
    assert not p["settings"]["resume_integration_approved"]


# ---------------------------------------------------------------- aggregation and evidence levels
def test_aggregates_every_achievement_kind_with_evidence_levels(env: Env) -> None:
    h = register(env)
    v = full_portfolio(env, h)["view"]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for item in v["timeline"]:
        by_kind.setdefault(item["kind"], []).append(item)
    assert set(by_kind) == {"learning_path", "assessment", "certificate", "project"}
    assert by_kind["learning_path"][0]["evidence_level"] == "learned"
    assert {i["evidence_level"] for i in by_kind["assessment"]} == {"assessed"}
    assert by_kind["project"][0]["evidence_level"] == "demonstrated"
    assert by_kind["project"][0]["details"]["review"].endswith("code was not executed.")
    cert = by_kind["certificate"][0]
    assert cert["details"]["certificate_id"].startswith("ACC-") and cert["details"]["verification_url"].endswith(cert["details"]["certificate_id"])
    assert [i["achieved_at"] for i in v["timeline"]] == sorted((i["achieved_at"] for i in v["timeline"]), reverse=True)
    s = v["stats"]
    assert (s["learning_paths_completed"], s["assessments_passed"], s["certificates"], s["projects_passed"]) == (1, 2, 1, 1)
    assert s["activities_completed"] > 0 and s["estimated_learning_hours"] > 0


def test_skill_evidence_classification(env: Env) -> None:
    h = register(env)
    skills = {s["skill"]: s for s in full_portfolio(env, h)["view"]["skills"]}
    assert skills["python"]["levels"] == ["learned", "assessed", "demonstrated"]  # roadmap + assessment + the RAG project uses Python
    assert skills["kafka"]["levels"] == ["assessed"]  # assessment (+ its certificate), no project covers it
    assert skills["rag"]["levels"] == ["demonstrated"]  # only the project evidences it
    assert all(s["highest"] in {"learned", "assessed", "demonstrated"} and s["evidence"] for s in skills.values())
    # a skill is only "demonstrated" through a passed project (or that project's certificate)
    for name, s in skills.items():
        for e in s["evidence"]:
            if e["level"] == "demonstrated":
                assert e["kind"] in {"project", "certificate"}, name


def test_portfolio_updates_automatically_without_reading_it(env: Env) -> None:
    h = register(env)
    env.client.get(f"{U}/portfolio", headers=h)  # portfolio exists, nothing in it yet
    assert env.db.query(PortfolioAchievement).count() == 0
    passed_assessment(env, h)  # qualifying event -> hook, no portfolio request in between
    rows = env.db.scalars(select(PortfolioAchievement)).all()
    assert [r.kind for r in rows] == ["assessment"]
    issue(env, h, "assessment", env.client.get(f"{U}/assessments/attempts", headers=h).json()[0]["attempt_id"])
    assert sorted(r.kind for r in env.db.scalars(select(PortfolioAchievement)).all()) == ["assessment", "certificate"]


def test_items_disappear_when_their_evidence_does(env: Env) -> None:
    h = register(env)
    env.client.get(f"{U}/portfolio", headers=h)
    cert = issue(env, h, "assessment", passed_assessment(env, h)["attempt_id"]).json()
    sub = passed_project(env, h)
    assert env.db.query(PortfolioAchievement).count() == 3
    env.client.post(f"{U}/admin/certificates/{cert['certificate_id']}/revoke", headers=admin_headers(env), json={"reason": "revoked in test"})
    assert "certificate" not in {r.kind for r in env.db.scalars(select(PortfolioAchievement)).all()}
    assert env.client.delete(f"{U}/projects/submissions/{sub['id']}", headers=h).status_code == 204
    assert {r.kind for r in env.db.scalars(select(PortfolioAchievement)).all()} == {"assessment"}


def test_nothing_can_be_added_or_edited_by_hand(env: Env) -> None:
    h = register(env)
    view = env.client.get(f"{U}/portfolio", headers=h).json()
    for method, path in (("post", "/portfolio/items"), ("put", "/portfolio/items"), ("post", "/portfolio")):
        assert getattr(env.client, method)(f"{U}{path}", headers=h, json={"kind": "employment", "title": "CTO at Google"}).status_code in {404, 405}
    env.client.put(f"{U}/portfolio/settings", headers=h, json={"timeline": [{"kind": "employment", "title": "CTO"}], "skills": [{"skill": "x"}]})
    assert env.client.get(f"{U}/portfolio", headers=h).json()["timeline"] == view["timeline"] == []
    passed_assessment(env, h)
    item = env.client.get(f"{U}/portfolio", headers=h).json()["timeline"][0]
    r = env.client.patch(f"{U}/portfolio/items/{item['id']}", headers=h, json={"is_visible": True, "title": "CEO", "evidence_level": "demonstrated"})
    after = env.client.get(f"{U}/portfolio", headers=h).json()["timeline"][0]
    assert r.status_code == 200 and after["title"] == item["title"] and after["evidence_level"] == "assessed"


# ---------------------------------------------------------------- publishing and consent
def test_publishing_requires_consent_and_a_display_name(env: Env) -> None:
    h = register(env)
    put = lambda **b: env.client.put(f"{U}/portfolio/settings", headers=h, json=b)
    assert put(visibility="public", display_name="Jane").status_code == 422  # no consent
    assert put(visibility="public", consent_public=True).status_code == 422  # no name
    assert put(visibility="public", consent_public=True, display_name="<>").status_code == 422  # name empties out
    assert env.client.get(f"{U}/portfolio", headers=h).json()["settings"]["visibility"] == "private"
    r = publish(env, h, name="  Jane <b>L.</b> ")
    s = r.json()["settings"]
    assert r.status_code == 200 and s["visibility"] == "public" and s["display_name"] == "Jane bL./b" and s["consent_at"]
    assert len(s["public_slug"]) == 10 and s["public_url"].endswith(f"/portfolio/{s['public_slug']}")
    assert env.db.query(AuditLog).filter(AuditLog.action == "portfolio.published").count() == 1


def test_public_view_contents_and_privacy(env: Env) -> None:
    h = register(env)
    data = full_portfolio(env, h)
    s = publish(env, h, headline="Backend learner", summary="I study backend engineering.").json()["settings"]
    r = public(env, s["public_slug"])  # no authentication
    body = r.json()
    assert r.status_code == 200 and body["display_name"] == "Jane L." and body["headline"] == "Backend learner"
    assert body["summary"] == "I study backend engineering." and "NOT professional employment" in body["disclaimer"]
    kinds = {i["kind"] for i in body["timeline"]}
    assert kinds == {"learning_path", "assessment", "certificate", "project"} and body["skills"]
    cert = next(i for i in body["timeline"] if i["kind"] == "certificate")
    assert cert["details"]["verification_url"].endswith(data["cert"]["certificate_id"])
    assert next(i for i in body["timeline"] if i["kind"] == "project")["details"]["repo_url"] == "https://github.com/acme/demo"
    raw = r.text.lower()
    for leaked in ("u@example.com", "user_id", "password", "token_hash", "owner_user_id", "portfolio_id", "source_id"):
        assert leaked not in raw
    assert "id" not in {k for item in body["timeline"] for k in item}  # no internal ids at all


def test_private_withdrawn_unknown_and_malformed_slugs_are_indistinguishable(env: Env) -> None:
    h = register(env)
    slug = publish(env, h).json()["settings"]["public_slug"]
    assert public(env, slug).status_code == 200
    env.client.put(f"{U}/portfolio/settings", headers=h, json={"visibility": "private"})  # consent withdrawn
    withdrawn, unknown, bad = public(env, slug), public(env, "aaaaaaaaaa"), public(env, "<script>")
    assert withdrawn.status_code == unknown.status_code == bad.status_code == 404
    assert withdrawn.json() == unknown.json() == bad.json()
    assert env.db.query(AuditLog).filter(AuditLog.action == "portfolio.unpublished").count() == 1
    again = publish(env, h).json()["settings"]
    assert again["public_slug"] == slug and public(env, slug).status_code == 200  # same URL on republish


def test_rotating_the_slug_invalidates_the_old_url(env: Env) -> None:
    h = register(env)
    old = publish(env, h).json()["settings"]["public_slug"]
    new = env.client.post(f"{U}/portfolio/rotate-slug", headers=h).json()["settings"]["public_slug"]
    assert new != old and public(env, old).status_code == 404 and public(env, new).status_code == 200


# ---------------------------------------------------------------- selective visibility
def test_hidden_items_and_sections_are_not_public(env: Env) -> None:
    h = register(env)
    full_portfolio(env, h)
    slug = publish(env, h, summary="My summary").json()["settings"]["public_slug"]
    timeline = env.client.get(f"{U}/portfolio", headers=h).json()["timeline"]
    project = next(i for i in timeline if i["kind"] == "project")
    env.client.patch(f"{U}/portfolio/items/{project['id']}", headers=h, json={"is_visible": False})
    body = public(env, slug).json()
    assert "project" not in {i["kind"] for i in body["timeline"]}
    assert not any(project["title"] in str(s["evidence"]) for s in body["skills"])  # skills derive from shown items only
    owner = env.client.get(f"{U}/portfolio", headers=h).json()
    assert any(i["kind"] == "project" and not i["is_visible"] for i in owner["timeline"])  # owner still sees it

    def sections(**s: bool) -> dict[str, Any]:
        env.client.put(f"{U}/portfolio/settings", headers=h, json={"section_visibility": s})
        return public(env, slug).json()  # type: ignore[no-any-return]

    assert "certificate" not in {i["kind"] for i in sections(certificates=False)["timeline"]}
    sections(certificates=True)
    no_scores = sections(scores=False)
    assert all("score" not in i["details"] for i in no_scores["timeline"])
    sections(scores=True)
    assert sections(summary=False)["summary"] is None
    assert sections(timeline=False)["timeline"] == [] and sections(skills=False)["skills"] == []
    assert env.client.put(f"{U}/portfolio/settings", headers=h, json={"section_visibility": {"employment": True}}).status_code == 422


def test_only_owner_can_change_own_items(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    passed_assessment(env, a)
    item = env.client.get(f"{U}/portfolio", headers=a).json()["timeline"][0]
    assert env.client.patch(f"{U}/portfolio/items/{item['id']}", headers=b, json={"is_visible": False}).status_code == 404
    assert env.client.get(f"{U}/portfolio", headers=b).json()["timeline"] == []


def test_markup_is_stripped_from_owner_text(env: Env) -> None:
    h = register(env)
    s = publish(env, h, headline="<img src=x onerror=alert(1)>Dev", summary="<script>alert(1)</script>Hello\x00 world").json()["settings"]
    assert "<" not in str(s) and ">" not in str(s) and s["summary"] == "scriptalert(1)/scriptHello world"


def test_public_endpoint_rate_limited() -> None:
    from tests.guest_fixtures import build_env

    env = next(build_env(portfolio_requests_per_minute=3))
    assert [public(env, "aaaaaaaaaa").status_code for _ in range(5)] == [404, 404, 404, 429, 429]


# ---------------------------------------------------------------- resume integration, LinkedIn, PDF
def test_resume_integration_needs_explicit_approval(env: Env) -> None:
    h = register(env)
    cert = issue(env, h, "assessment", passed_assessment(env, h)["attempt_id"]).json()
    assert env.client.get(f"{U}/portfolio/resume-section", headers=h).status_code == 409  # not approved
    assert env.client.post(f"{U}/portfolio/resume-integration", headers=h, json={"approve": True}).status_code == 204
    text = env.client.get(f"{U}/portfolio/resume-section", headers=h).json()["text"]
    assert "not employment experience" in text and cert["certificate_id"] in text and "Passed assessment: Python Fundamentals" in text
    item = next(i for i in env.client.get(f"{U}/portfolio", headers=h).json()["timeline"] if i["kind"] == "certificate")
    env.client.patch(f"{U}/portfolio/items/{item['id']}", headers=h, json={"is_visible": False})
    assert cert["certificate_id"] not in env.client.get(f"{U}/portfolio/resume-section", headers=h).json()["text"]
    env.client.post(f"{U}/portfolio/resume-integration", headers=h, json={"approve": False})
    assert env.client.get(f"{U}/portfolio/resume-section", headers=h).status_code == 409
    actions = {a.action for a in env.db.scalars(select(AuditLog)).all()}
    assert {"portfolio.resume_integration_approved", "portfolio.resume_integration_withdrawn"} <= actions


def test_linkedin_summary_is_honest_and_respects_visibility(env: Env) -> None:
    h = register(env)
    full_portfolio(env, h)
    out = env.client.get(f"{U}/portfolio/linkedin-summary", headers=h).json()
    assert len(out["about"]) <= 2600 and "not employment" in out["about"] and "1 platform certificate" in out["about"]
    assert "python (learned, assessed, practically demonstrated)" in out["about"]
    cert = out["certifications"][0]
    assert cert["issuing_organization"] == "AI Career Coach (platform-issued)" and cert["credential_id"].startswith("ACC-")
    assert cert["credential_url"].endswith(cert["credential_id"]) and len(cert["issue_date"]) == 7
    assert any("do not add them under Experience" in n for n in out["notes"]) and any("Nothing is posted" in n for n in out["notes"])
    item = next(i for i in env.client.get(f"{U}/portfolio", headers=h).json()["timeline"] if i["kind"] == "certificate")
    env.client.patch(f"{U}/portfolio/items/{item['id']}", headers=h, json={"is_visible": False})
    again = env.client.get(f"{U}/portfolio/linkedin-summary", headers=h).json()
    assert again["certifications"] == [] and "0 platform certificate" in again["about"]


def test_portfolio_pdf_export(env: Env) -> None:
    h = register(env)
    full_portfolio(env, h)
    r = env.client.post(f"{U}/portfolio/report", headers=h, json={"report_format": "pdf"})
    assert r.status_code == 201
    dl = env.client.get(f"{U}/reports/{r.json()['report_id']}/download", headers=h)
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF-")
    text = pdf_text(dl.content)
    for expected in ("Career Achievement Portfolio", "NOT professional employment experience", "Skill evidence",
                     "Achievement timeline", "Certificates", "ACC-", "practically demonstrated"):
        assert expected in text, expected
    assert env.client.post(f"{U}/portfolio/report", headers=h, json={"report_format": "xlsx"}).status_code == 422
    assert env.db.scalar(select(Report).where(Report.report_type == "portfolio")) is not None


# ---------------------------------------------------------------- erasure
def test_account_deletion_removes_portfolio_and_public_page(env: Env) -> None:
    h = register(env)
    full_portfolio(env, h)
    slug = publish(env, h).json()["settings"]["public_slug"]
    assert public(env, slug).status_code == 200
    r = env.client.request("DELETE", f"{U}/users/me", headers=h, json={"password": "Str0ng-passw0rd", "confirm": True})
    assert r.status_code == 204 and public(env, slug).status_code == 404
    assert env.db.query(Portfolio).count() == 0 and env.db.query(PortfolioAchievement).count() == 0
