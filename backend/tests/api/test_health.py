from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, log_format="text")))  # type: ignore[call-arg]


def test_health_both_paths() -> None:
    c = client()
    for path in ("/health", "/api/v1/health"):
        r = c.get(path)
        assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_security_headers_and_correlation_id() -> None:
    r = client().get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert len(r.headers["x-correlation-id"]) == 32


def test_cors_rejects_unlisted_origin() -> None:
    r = client().get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_allows_configured_origin() -> None:
    r = client().get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
