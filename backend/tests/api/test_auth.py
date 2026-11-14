"""Registration, login, refresh rotation, logout, account management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.models import Document, User, UserSession
from app.rag.vector_store import Owner
from tests.guest_fixtures import RESUME, Env

PW = "Str0ng-passw0rd"
BASE = "/api/v1"


def register(env: Env, email: str = "Jane@Example.com", password: str = PW, **extra: object):  # type: ignore[no-untyped-def]
    return env.client.post(f"{BASE}/auth/register",
                           json={"email": email, "password": password, "display_name": "Jane", **extra})


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(env: Env, email: str = "jane@example.com", password: str = PW):  # type: ignore[no-untyped-def]
    return env.client.post(f"{BASE}/auth/login", json={"email": email, "password": password})


# ---------------------------------------------------------------- register


def test_register_success(env: Env) -> None:
    r = register(env)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 30 * 60
    assert PW not in r.text
    user = env.db.scalar(select(User))
    assert user is not None and user.email == "jane@example.com" and user.role == "user"
    assert user.password_hash.startswith("$argon2id$") and PW not in user.password_hash
    cookie = r.headers["set-cookie"].lower()
    assert "refresh_token=" in cookie and "httponly" in cookie and "path=/api/v1/auth" in cookie
    assert env.client.get(f"{BASE}/users/me", headers=auth(body["access_token"])).json()["email"] == "jane@example.com"


def test_register_cannot_choose_role(env: Env) -> None:
    r = register(env, role="admin", is_active=False)
    assert r.status_code == 201
    assert env.db.scalar(select(User)).role == "user"  # type: ignore[union-attr]


def test_duplicate_email_case_insensitive(env: Env) -> None:
    assert register(env, "a@example.com").status_code == 201
    r = register(env, "A@EXAMPLE.COM")
    assert r.status_code == 409 and r.json()["error"]["code"] == "registration_failed"


@pytest.mark.parametrize(
    "pw", ["short1", "alllettersnodigit", "1234567890123", "x" * 129 + "1"]
)
def test_weak_passwords_rejected_without_echo(env: Env, pw: str) -> None:
    r = register(env, password=pw)
    assert r.status_code == 422 and pw not in r.text
    assert r.json()["error"]["code"] == "validation_error"


def test_invalid_email_rejected(env: Env) -> None:
    assert register(env, "not-an-email").status_code == 422


def test_registration_rate_limited_per_ip() -> None:
    from tests.guest_fixtures import build_env

    e = next(build_env(registrations_per_ip_per_hour=2))
    codes = [register(e, f"u{i}@example.com").status_code for i in range(4)]
    assert codes == [201, 201, 429, 429]


# ---------------------------------------------------------------- login


def test_login_success_and_audit(env: Env) -> None:
    register(env)
    r = login(env)
    assert r.status_code == 200 and "access_token" in r.json()
    assert login(env, "JANE@example.com").status_code == 200  # case-insensitive


def test_login_failures_are_indistinguishable(env: Env) -> None:
    register(env)
    wrong_pw = login(env, password="Wrong-passw0rd!")
    unknown = login(env, "nobody@example.com")
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()
    assert "set-cookie" not in wrong_pw.headers


def test_inactive_user_cannot_login(env: Env) -> None:
    register(env)
    user = env.db.scalar(select(User))
    assert user is not None
    user.is_active = False
    env.db.commit()
    assert login(env).status_code == 401


def test_login_rate_limited_per_email() -> None:
    from tests.guest_fixtures import build_env

    e = next(build_env(login_attempts_per_15_min=3))
    register(e)
    codes = [login(e, password="Wrong-passw0rd!").status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    assert login(e).status_code == 429  # even the right password is throttled


# ---------------------------------------------------------------- tokens


def test_protected_endpoints_reject_bad_tokens(env: Env) -> None:
    token = register(env).json()["access_token"]
    assert env.client.get(f"{BASE}/users/me").status_code == 401
    assert env.client.get(f"{BASE}/users/me", headers=auth(token + "x")).status_code == 401
    assert env.client.get(f"{BASE}/users/me", headers={"Authorization": token}).status_code == 401
    forged = jwt.encode({"sub": str(uuid.uuid4()), "iat": 1, "exp": 9999999999, "typ": "access"},
                        "z" * 40, algorithm="HS256")
    assert env.client.get(f"{BASE}/users/me", headers=auth(forged)).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(env: Env) -> None:
    r = register(env)
    refresh_cookie = r.cookies.get("refresh_token")
    assert refresh_cookie
    assert env.client.get(f"{BASE}/users/me", headers=auth(refresh_cookie)).status_code == 401


def test_refresh_rotates_and_detects_reuse(env: Env) -> None:
    register(env)
    old = env.client.cookies.get("refresh_token")
    r = env.client.post(f"{BASE}/auth/refresh")
    assert r.status_code == 200
    new = env.client.cookies.get("refresh_token")
    assert new and new != old
    assert env.client.get(f"{BASE}/users/me", headers=auth(r.json()["access_token"])).status_code == 200
    # replay the rotated-out token (attacker): rejected, and the whole family is revoked
    env.client.cookies.clear()
    env.client.cookies.set("refresh_token", old, path="/api/v1/auth")
    assert env.client.post(f"{BASE}/auth/refresh").status_code == 401
    env.client.cookies.clear()
    env.client.cookies.set("refresh_token", new, path="/api/v1/auth")
    assert env.client.post(f"{BASE}/auth/refresh").status_code == 401


def test_refresh_without_cookie_and_expired(env: Env) -> None:
    assert env.client.post(f"{BASE}/auth/refresh").status_code == 401
    register(env)
    sess = env.db.scalar(select(UserSession))
    assert sess is not None
    sess.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    env.db.commit()
    assert env.client.post(f"{BASE}/auth/refresh").status_code == 401


def test_refresh_and_logout_reject_foreign_origin(env: Env) -> None:
    register(env)
    evil = {"Origin": "https://evil.example"}
    assert env.client.post(f"{BASE}/auth/refresh", headers=evil).status_code == 403
    assert env.client.post(f"{BASE}/auth/logout", headers=evil).status_code == 403
    ok = {"Origin": "http://localhost:5173"}
    assert env.client.post(f"{BASE}/auth/refresh", headers=ok).status_code == 200


def test_logout_revokes_refresh_token(env: Env) -> None:
    register(env)
    old = env.client.cookies.get("refresh_token")
    assert env.client.post(f"{BASE}/auth/logout").status_code == 204
    env.client.cookies.set("refresh_token", old, path="/api/v1/auth")
    assert env.client.post(f"{BASE}/auth/refresh").status_code == 401
    assert env.client.post(f"{BASE}/auth/logout").status_code == 204  # idempotent


def test_refresh_tokens_stored_hashed(env: Env) -> None:
    register(env)
    raw = env.client.cookies.get("refresh_token")
    sess = env.db.scalar(select(UserSession))
    assert sess is not None and raw and raw not in sess.refresh_token_hash and len(sess.refresh_token_hash) == 64


# ---------------------------------------------------------------- account


def test_profile_roundtrip_and_validation(env: Env) -> None:
    h = auth(register(env).json()["access_token"])
    assert env.client.get(f"{BASE}/users/me/profile", headers=h).json()["headline"] is None
    r = env.client.put(f"{BASE}/users/me/profile", headers=h, json={
        "headline": "Backend dev", "career_goal": "Staff engineer", "target_role": "Architect",
        "years_experience": 8})
    assert r.status_code == 200
    assert env.client.get(f"{BASE}/users/me/profile", headers=h).json()["years_experience"] == 8
    assert env.client.put(f"{BASE}/users/me/profile", headers=h,
                          json={"years_experience": -1}).status_code == 422
    assert env.client.patch(f"{BASE}/users/me", headers=h, json={"display_name": "J"}).json()["display_name"] == "J"


def test_profiles_are_per_user(env: Env) -> None:
    a = auth(register(env, "a@example.com").json()["access_token"])
    b = auth(register(env, "b@example.com").json()["access_token"])
    env.client.put(f"{BASE}/users/me/profile", headers=a, json={"headline": "A's headline"})
    assert env.client.get(f"{BASE}/users/me/profile", headers=b).json()["headline"] is None


def test_change_password_revokes_other_sessions_and_old_tokens(env: Env) -> None:
    token = register(env).json()["access_token"]
    other = login(env)  # second device
    other_refresh = env.client.cookies.get("refresh_token")
    new_pw = "Another-passw0rd"
    assert env.client.post(f"{BASE}/users/me/password", headers=auth(token),
                           json={"current_password": "wrong", "new_password": new_pw}).status_code == 401
    assert env.client.post(f"{BASE}/users/me/password", headers=auth(token),
                           json={"current_password": PW, "new_password": "weak"}).status_code == 422
    assert env.client.post(f"{BASE}/users/me/password", headers=auth(token),
                           json={"current_password": PW, "new_password": new_pw}).status_code == 204
    assert login(env, password=PW).status_code == 401
    assert login(env, password=new_pw).status_code == 200
    env.client.cookies.clear()
    env.client.cookies.set("refresh_token", other_refresh, path="/api/v1/auth")
    assert env.client.post(f"{BASE}/auth/refresh").status_code == 401  # revoked
    assert other.status_code == 200
    # a token issued before the change is rejected (use an obviously stale one)
    user = env.db.scalar(select(User))
    assert user is not None
    stale = jwt.encode({"sub": str(user.id), "iat": int(datetime.now(UTC).timestamp()) - 3600,
                        "exp": int(datetime.now(UTC).timestamp()) + 3600, "typ": "access"},
                       "j" * 40, algorithm="HS256")
    assert env.client.get(f"{BASE}/users/me", headers=auth(stale)).status_code == 401


def test_delete_account_removes_data_and_frees_email(env: Env) -> None:
    token = register(env).json()["access_token"]
    user = env.db.scalar(select(User))
    assert user is not None
    # give the user some data: a document row + vectors
    env.store.add_chunks(Owner("user", str(user.id)), "d1", [__import__("app.rag.chunking", fromlist=["Chunk"]).Chunk(0, "resume text")], [[0.1] * 384])
    env.db.add(Document(kind="resume", filename="a.txt", content_type="text/plain", size_bytes=1,
                        sha256="0" * 64, owner_user_id=user.id))
    env.db.commit()
    h = auth(token)
    assert env.client.request("DELETE", f"{BASE}/users/me", headers=h,
                              json={"password": "wrong", "confirm": True}).status_code == 401
    assert env.client.request("DELETE", f"{BASE}/users/me", headers=h,
                              json={"password": PW, "confirm": False}).status_code == 422
    assert env.store.count(Owner("user", str(user.id))) == 1  # nothing deleted yet
    assert env.client.request("DELETE", f"{BASE}/users/me", headers=h,
                              json={"password": PW, "confirm": True}).status_code == 204
    assert env.store.count(Owner("user", str(user.id))) == 0
    assert env.db.query(Document).filter(Document.owner_user_id == user.id).count() == 0
    assert env.client.get(f"{BASE}/users/me", headers=h).status_code == 401
    assert login(env).status_code == 401
    assert "jane" not in user.email and user.display_name == "Deleted user"
    assert register(env).status_code == 201  # email can be reused


# ---------------------------------------------------------------- guest import


def _user_and_guest(env: Env) -> tuple[dict[str, str], dict[str, str], dict[str, str], str]:
    token = register(env).json()["access_token"]
    guest_headers, gbody = env.new_guest()
    env.upload_text(guest_headers, "resume", RESUME)
    env.upload_text(guest_headers, "job_description", "Python backend role")
    return auth(token), guest_headers, gbody, token


def test_guest_import_requires_consent_and_guest_token(env: Env) -> None:
    uh, gh, _, _ = _user_and_guest(env)
    url = f"{BASE}/users/me/import-guest-session"
    assert env.client.post(url, headers={**uh, **gh}, json={"consent": False}).status_code == 422
    assert env.client.post(url, headers=uh, json={"consent": True}).status_code == 401  # no guest token
    assert env.client.post(url, headers=gh, json={"consent": True}).status_code == 401  # not logged in
    assert env.client.post(url, headers={**uh, "X-Guest-Token": "guess"}, json={"consent": True}).status_code == 401


def test_guest_import_preserves_ownership_and_moves_vectors(env: Env) -> None:
    uh, gh, gbody, _ = _user_and_guest(env)
    user = env.db.scalar(select(User))
    assert user is not None
    guest_owner, user_owner = Owner("guest", gbody["session_id"]), Owner("user", str(user.id))
    before = env.store.count(guest_owner)
    assert before > 0
    r = env.client.post(f"{BASE}/users/me/import-guest-session", headers={**uh, **gh},
                        json={"consent": True})
    assert r.status_code == 200 and r.json() == {"documents": 2, "reports": 0}
    assert env.store.count(guest_owner) == 0 and env.store.count(user_owner) == before
    docs = env.db.query(Document).all()
    assert len(docs) == 2 and all(d.owner_user_id == user.id and d.guest_session_id is None
                                  and d.expires_at is None for d in docs)
    # the guest token is dead afterwards and cannot import again
    assert env.client.get(f"{BASE}/guest/documents", headers=gh).status_code == 401
    assert env.client.post(f"{BASE}/users/me/import-guest-session", headers={**uh, **gh},
                           json={"consent": True}).status_code == 401


def test_guest_import_survives_cleanup(env: Env) -> None:
    from app.services import guest_service

    uh, gh, _gbody, _ = _user_and_guest(env)
    env.client.post(f"{BASE}/users/me/import-guest-session", headers={**uh, **gh}, json={"consent": True})
    guest_service.cleanup_expired(env.db, env.store, env.storage)  # deleted_at set -> purged
    assert env.db.query(Document).count() == 2  # imported documents untouched
    user = env.db.scalar(select(User))
    assert user is not None and env.store.count(Owner("user", str(user.id))) > 0


def test_guest_import_cannot_take_another_users_guest_data(env: Env) -> None:
    uh_a, gh_a, _, _ = _user_and_guest(env)
    token_b = register(env, "b@example.com").json()["access_token"]
    _, gh_b = env.new_guest()[0], None
    # B only holds B's own guest token; A's guest data stays with A's guest session
    gb_headers, _ = env.new_guest()
    env.upload_text(gb_headers, text="b private")
    r = env.client.post(f"{BASE}/users/me/import-guest-session",
                        headers={**auth(token_b), **gb_headers}, json={"consent": True})
    assert r.status_code == 200 and r.json()["documents"] == 1
    assert env.db.query(Document).filter(Document.owner_user_id.is_(None)).count() == 2  # A's still guest-owned
    assert gh_b is None and uh_a and gh_a


def test_guest_import_commit_failure_restores_vectors(env: Env) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    from app.core.exceptions import DatabaseError
    from app.models import GuestSession
    from app.services import account_service

    _, gh, gbody, _ = _user_and_guest(env)
    user = env.db.scalar(select(User))
    guest = env.db.get(GuestSession, uuid.UUID(gbody["session_id"]))
    assert user is not None and guest is not None
    guest_owner = Owner("guest", gbody["session_id"])
    before = env.store.count(guest_owner)

    def fail() -> None:
        raise SQLAlchemyError("boom")

    original = env.db.commit
    env.db.commit = fail  # type: ignore[method-assign]
    with pytest.raises(DatabaseError):
        account_service.import_guest_session(env.db, env.store, user, guest, True)
    env.db.commit = original  # type: ignore[method-assign]
    assert env.store.count(guest_owner) == before
    assert env.store.count(Owner("user", str(user.id))) == 0
    assert gh


# ---------------------------------------------------------------- misc


def test_auth_responses_not_cacheable_and_secure_headers(env: Env) -> None:
    r = register(env)
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"


def test_secrets_not_logged(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    caplog.set_level(logging.DEBUG)
    token = register(env).json()["access_token"]
    login(env, password="Wrong-passw0rd!")
    login(env)
    env.client.post(f"{BASE}/auth/refresh")
    assert PW not in caplog.text and "Wrong-passw0rd" not in caplog.text
    assert token not in caplog.text and "jane@example.com" not in caplog.text.lower()
