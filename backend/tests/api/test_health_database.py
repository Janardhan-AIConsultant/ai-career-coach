from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


def test_database_health_ok(client: TestClient) -> None:
    for path in ("/health/database", "/api/v1/health/database"):
        r = client.get(path)
        assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_database_health_unavailable_hides_details(
    client: TestClient, db_session: Session, monkeypatch: object
) -> None:
    def fail(*_: object, **__: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("password=hunter2 host=internal"))

    monkeypatch.setattr(db_session, "execute", fail)  # type: ignore[attr-defined]
    r = client.get("/health/database")
    assert r.status_code == 503 and r.json() == {"status": "unavailable"}
