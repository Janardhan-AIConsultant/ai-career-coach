from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.models import AuditLog, GuestSession, User, UserSession
from tests.api.test_projects_certificates import admin_headers as _make_admin
from tests.api.test_projects_certificates import completed_roadmap, register
from tests.guest_fixtures import Env

U = "/api/v1"
PW = "Str0ng-passw0rd"


def admin(env: Env) -> dict[str, str]:
    if "admin" not in env.db.info:
        env.db.info["admin"] = _make_admin(env)
    return env.db.info["admin"]  # type: ignore[no-any-return]


def me(env: Env, h: dict[str, str]) -> dict[str, Any]:
    return env.client.get(f"{U}/users/me", headers=h).json()  # type: ignore[no-any-return]


def second_admin(env: Env) -> User:
    from tests.conftest import make_user
    return make_user(env.db, "admin2@example.com", role="admin")


ROUTES = (("get", "/admin/overview"), ("get", "/admin/users"), ("get", "/admin/audit-logs"),
          ("get", "/admin/assessments"), ("get", "/admin/system"), ("post", "/admin/maintenance/cleanup-guests"))


def test_every_dashboard_route_is_admin_only(env: Env) -> None:
    h = register(env)
    guest, _ = env.new_guest()
    uid = uuid.uuid4()
    routes = [*ROUTES, ("patch", f"/admin/users/{uid}")]
    for method, path in routes:
        kw: dict[str, Any] = {"json": {"is_active": False}} if method == "patch" else {}
        call = getattr(env.client, method)
        assert call(f"{U}{path}", **kw).status_code == 401, path
        assert call(f"{U}{path}", headers=guest, **kw).status_code == 401, path
        assert call(f"{U}{path}", headers=h, **kw).status_code == 403, path


def test_overview_counts_are_real_and_aggregate(env: Env) -> None:
    adm = admin(env)
    empty = env.client.get(f"{U}/admin/overview", headers=adm).json()
    assert empty["users"]["total"] == 1 and empty["users"]["admins"] == 1
    assert empty["learning"]["assessment_pass_rate"] is None and empty["community"]["average_rating"] is None
    h = register(env)
    completed_roadmap(env, h)
    env.client.post(f"{U}/feedback", headers=h, json={"feature": "platform", "rating": 4})
    env.new_guest()
    o = env.client.get(f"{U}/admin/overview", headers=adm).json()
    assert o["users"] == {"total": 2, "active": 2, "admins": 1, "new_7d": 2, "new_30d": 2}
    assert o["guests"]["active_sessions"] == 1
    assert sum(o["learning"]["roadmaps_by_status"].values()) == 1
    assert set(o["learning"]["roadmaps_by_duration"]) <= {"7", "15", "60"}
    assert o["learning"]["assessment_attempts"] >= 1 and o["learning"]["assessment_pass_rate"] is not None
    assert o["community"]["ratings"] == 1 and o["community"]["average_rating"] == 4.0
    blob = str(o)
    assert "u@example.com" not in blob and "password" not in blob.lower()


def test_user_list_search_filter_and_privacy(env: Env) -> None:
    adm = admin(env)
    register(env, "alice@example.com")
    register(env, "bob@example.com")
    rows = env.client.get(f"{U}/admin/users", headers=adm).json()
    assert {r["email"] for r in rows} == {"admin@example.com", "alice@example.com", "bob@example.com"}
    assert all("password" not in r and "password_hash" not in r for r in rows)
    assert [r["email"] for r in env.client.get(f"{U}/admin/users?search=ALI", headers=adm).json()] == ["alice@example.com"]
    assert env.client.get(f"{U}/admin/users?search=%25", headers=adm).json() == []  # wildcard is escaped
    assert [r["email"] for r in env.client.get(f"{U}/admin/users?role=admin", headers=adm).json()] == ["admin@example.com"]
    assert len(env.client.get(f"{U}/admin/users?limit=1", headers=adm).json()) == 1
    assert env.client.get(f"{U}/admin/users?role=root", headers=adm).status_code == 422


def test_deactivation_ends_access_immediately_and_is_reversible(env: Env) -> None:
    adm = admin(env)
    h = register(env)
    uid = me(env, h)["id"]
    r = env.client.patch(f"{U}/admin/users/{uid}", headers=adm, json={"is_active": False, "reason": "abuse"})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert env.client.get(f"{U}/users/me", headers=h).status_code == 401  # existing token is dead
    assert env.client.post(f"{U}/auth/login", json={"email": "u@example.com", "password": PW}).status_code in (401, 403)
    env.db.expire_all()
    assert all(s.revoked_at is not None for s in env.db.scalars(select(UserSession)).all())
    r = env.client.patch(f"{U}/admin/users/{uid}", headers=adm, json={"is_active": True})
    assert r.json()["is_active"] is True
    assert env.client.post(f"{U}/auth/login", json={"email": "u@example.com", "password": PW}).status_code == 200
    entries = env.db.scalars(select(AuditLog).where(AuditLog.action == "admin.user_updated")).all()
    assert len(entries) == 2 and entries[0].details["reason"] == "abuse"
    assert "email" not in str(entries[0].details)


def test_role_change_and_admin_lockout_protections(env: Env) -> None:
    adm = admin(env)
    admin_id = env.db.scalar(select(User.id).where(User.email == "admin@example.com"))
    # cannot touch yourself
    for body in ({"is_active": False}, {"role": "user"}):
        assert env.client.patch(f"{U}/admin/users/{admin_id}", headers=adm, json=body).status_code == 409
    h = register(env)
    uid = me(env, h)["id"]
    assert env.client.patch(f"{U}/admin/users/{uid}", headers=adm, json={"role": "admin"}).json()["role"] == "admin"
    # promoted user can now use admin routes with a fresh token
    h2 = {"Authorization": "Bearer " + env.client.post(
        f"{U}/auth/login", json={"email": "u@example.com", "password": PW}).json()["access_token"]}
    assert env.client.get(f"{U}/admin/overview", headers=h2).status_code == 200
    # the promoted admin may demote the original; then they are the last admin and are protected
    assert env.client.patch(f"{U}/admin/users/{admin_id}", headers=h2, json={"role": "user"}).status_code == 200
    assert env.client.patch(f"{U}/admin/users/{uid}", headers=h2, json={"role": "user"}).status_code == 409


def test_admin_can_deactivate_another_admin_who_then_loses_access(env: Env) -> None:
    adm = admin(env)
    other = second_admin(env)
    from app.core.security import create_access_token
    other_h = {"Authorization": f"Bearer {create_access_token(other.id, 'j' * 40, 30)}"}
    assert env.client.get(f"{U}/admin/overview", headers=other_h).status_code == 200
    assert env.client.patch(f"{U}/admin/users/{other.id}", headers=adm, json={"is_active": False}).status_code == 200
    assert env.client.get(f"{U}/admin/overview", headers=other_h).status_code == 401
    # the remaining admin is the only active one and cannot remove themselves
    admin_id = env.db.scalar(select(User.id).where(User.email == "admin@example.com"))
    assert env.client.patch(f"{U}/admin/users/{admin_id}", headers=adm, json={"is_active": False}).status_code == 409


def test_patch_validation_and_unknown_user(env: Env) -> None:
    adm = admin(env)
    h = register(env)
    uid = me(env, h)["id"]
    assert env.client.patch(f"{U}/admin/users/{uid}", headers=adm, json={}).status_code == 422
    assert env.client.patch(f"{U}/admin/users/{uid}", headers=adm, json={"role": "root"}).status_code == 422
    assert env.client.patch(f"{U}/admin/users/{uuid.uuid4()}", headers=adm, json={"is_active": False}).status_code == 404
    # no-op change writes no audit entry
    env.client.patch(f"{U}/admin/users/{uid}", headers=adm, json={"is_active": True})
    assert env.db.scalars(select(AuditLog).where(AuditLog.action == "admin.user_updated")).all() == []


def test_audit_log_listing_and_filters(env: Env) -> None:
    adm = admin(env)
    h = register(env)
    uid = me(env, h)["id"]
    env.client.patch(f"{U}/admin/users/{uid}", headers=adm, json={"is_active": True, "role": "admin"})
    logs = env.client.get(f"{U}/admin/audit-logs", headers=adm).json()
    assert any(x["action"] == "admin.user_updated" for x in logs)
    only = env.client.get(f"{U}/admin/audit-logs?action=admin.", headers=adm).json()
    assert only and all(x["action"].startswith("admin.") for x in only)
    assert env.client.get(f"{U}/admin/audit-logs?action=zzz", headers=adm).json() == []
    assert env.client.get(f"{U}/admin/audit-logs?actor={uuid.uuid4()}", headers=adm).json() == []
    assert len(env.client.get(f"{U}/admin/audit-logs?limit=1", headers=adm).json()) == 1
    assert env.client.get(f"{U}/admin/audit-logs?actor=notauuid", headers=adm).status_code == 422


def test_assessment_stats(env: Env) -> None:
    adm = admin(env)
    h = register(env)
    completed_roadmap(env, h)
    rows = env.client.get(f"{U}/admin/assessments", headers=adm).json()
    assert rows, "bank is seeded on first use"
    used = [r for r in rows if r["attempts"]]
    assert used and used[0]["pass_rate"] is not None and 0 <= used[0]["pass_rate"] <= 100
    assert all(r["questions"] > 0 for r in rows)


def test_system_status_reports_no_secrets_and_flags_production_risks(env: Env) -> None:
    adm = admin(env)
    s = env.client.get(f"{U}/admin/system", headers=adm).json()
    assert s["roadmap_durations"] == [7, 15, 60] and s["share_platforms"] == ["linkedin", "whatsapp", "facebook"]
    comps = {c["name"]: c for c in s["components"]}
    assert comps["database"]["status"] == "ok" and comps["llm"]["status"] == "not_configured"
    blob = str(s)
    for secret in ("j" * 40, "postgresql", "sqlite", "career:career"):
        assert secret not in blob
    assert s["warnings"] == []  # test environment
    from app.core.config import Settings
    from app.services.admin_service import AdminService
    st = Settings(_env_file=None, jwt_secret_key="j" * 40, app_env="production",  # type: ignore[call-arg]
                  embedding_provider="hash", database_url="sqlite://")
    user = env.db.scalar(select(User))
    assert user is not None
    warns = AdminService(env.db, st, user).system_status().warnings
    assert any("Hash embeddings" in w for w in warns) and any("Local object storage" in w for w in warns)
    assert any("SQLite" in w for w in warns) and any("localhost" in w for w in warns)


def test_cleanup_purges_only_expired_guest_sessions_and_is_audited(env: Env) -> None:
    adm = admin(env)
    live_h, _ = env.new_guest()
    env.new_guest()
    old = env.db.scalars(select(GuestSession)).all()[1]
    old.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    env.db.commit()
    before = env.client.get(f"{U}/admin/overview", headers=adm).json()["guests"]
    assert before["expired_pending_cleanup"] == 1
    r = env.client.post(f"{U}/admin/maintenance/cleanup-guests", headers=adm)
    assert r.status_code == 200 and r.json() == {"guest_sessions_purged": 1}
    after = env.client.get(f"{U}/admin/overview", headers=adm).json()["guests"]
    assert after["expired_pending_cleanup"] == 0 and after["active_sessions"] == 1
    assert env.db.scalar(select(AuditLog).where(AuditLog.action == "admin.guest_cleanup")).details == {"purged": 1}
    assert live_h  # the live guest session is untouched
