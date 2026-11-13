"""Authentication/authorization dependency behaviour via a throwaway router."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import AdminUser, CurrentGuest, CurrentUser
from app.core.config import Settings
from app.core.security import create_access_token
from app.main import create_app
from tests.conftest import JWT_SECRET, make_guest, make_user


@pytest.fixture()
def probe(client: TestClient) -> TestClient:
    router = APIRouter()

    @router.get("/_probe/user")
    def user_ep(user: CurrentUser) -> dict[str, str]:
        return {"email": user.email}

    @router.get("/_probe/admin")
    def admin_ep(user: AdminUser) -> dict[str, str]:
        return {"email": user.email}

    @router.get("/_probe/guest")
    def guest_ep(guest: CurrentGuest) -> dict[str, str]:
        return {"id": str(guest.id)}

    client.app.include_router(router)  # type: ignore[attr-defined]
    return client


def bearer(user_id: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, JWT_SECRET, 5)}"}  # type: ignore[arg-type]


def test_user_requires_token(probe: TestClient) -> None:
    r = probe.get("/_probe/user")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


def test_user_with_valid_token(probe: TestClient, db_session: Session) -> None:
    u = make_user(db_session)
    r = probe.get("/_probe/user", headers=bearer(u.id))
    assert r.status_code == 200 and r.json() == {"email": "u@example.com"}


def test_deleted_or_inactive_user_rejected(probe: TestClient, db_session: Session) -> None:
    u = make_user(db_session)
    u.is_active = False
    db_session.commit()
    assert probe.get("/_probe/user", headers=bearer(u.id)).status_code == 401
    u.is_active, u.deleted_at = True, datetime.now(UTC)
    db_session.commit()
    assert probe.get("/_probe/user", headers=bearer(u.id)).status_code == 401


def test_admin_endpoint_forbidden_for_regular_user(probe: TestClient, db_session: Session) -> None:
    u = make_user(db_session)
    assert probe.get("/_probe/admin", headers=bearer(u.id)).status_code == 403
    admin = make_user(db_session, "a@example.com", role="admin")
    assert probe.get("/_probe/admin", headers=bearer(admin.id)).status_code == 200


def test_guest_cannot_use_user_endpoint(probe: TestClient, db_session: Session) -> None:
    _, raw = make_guest(db_session)
    r = probe.get("/_probe/user", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 401
    assert probe.get("/_probe/admin", headers={"X-Guest-Token": raw}).status_code == 401


def test_guest_valid_token(probe: TestClient, db_session: Session) -> None:
    g, raw = make_guest(db_session)
    r = probe.get("/_probe/guest", headers={"X-Guest-Token": raw})
    assert r.status_code == 200 and r.json()["id"] == str(g.id)


def test_guest_missing_unknown_and_session_id_as_token_rejected(
    probe: TestClient, db_session: Session
) -> None:
    g, _ = make_guest(db_session)
    assert probe.get("/_probe/guest").status_code == 401
    assert probe.get("/_probe/guest", headers={"X-Guest-Token": "nope"}).status_code == 401
    # a known session ID is not a credential
    assert probe.get("/_probe/guest", headers={"X-Guest-Token": str(g.id)}).status_code == 401


def test_guest_expired_session(probe: TestClient, db_session: Session) -> None:
    g, raw = make_guest(db_session)
    g.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    r = probe.get("/_probe/guest", headers={"X-Guest-Token": raw})
    assert r.status_code == 401 and r.json()["error"]["code"] == "guest_session_expired"


def test_guest_deleted_session(probe: TestClient, db_session: Session) -> None:
    g, raw = make_guest(db_session)
    g.deleted_at = datetime.now(UTC)
    db_session.commit()
    assert probe.get("/_probe/guest", headers={"X-Guest-Token": raw}).status_code == 401


def test_guest_quota_enforced(probe: TestClient, db_session: Session) -> None:
    _, raw = make_guest(db_session)  # max_requests_per_session=3 in test settings
    codes = [probe.get("/_probe/guest", headers={"X-Guest-Token": raw}).status_code
             for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_guest_isolation_between_sessions(probe: TestClient, db_session: Session) -> None:
    a, raw_a = make_guest(db_session)
    b, raw_b = make_guest(db_session)
    ids = {probe.get("/_probe/guest", headers={"X-Guest-Token": t}).json()["id"]
           for t in (raw_a, raw_b)}
    assert ids == {str(a.id), str(b.id)}


def test_unhandled_error_is_sanitised(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/_boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    r = TestClient(app, raise_server_exceptions=False).get("/_boom")
    assert r.status_code == 500 and "secret" not in r.text
