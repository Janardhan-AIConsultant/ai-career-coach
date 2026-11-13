from fastapi.testclient import TestClient

from app.api.dependencies import get_vector_store
from app.core.config import Settings, get_settings
from app.main import create_app
from app.rag.vector_store import InMemoryVectorStore


def _client(**kw: object) -> TestClient:
    s = Settings(_env_file=None, log_format="text", embedding_provider="hash", **kw)  # type: ignore[call-arg]
    app = create_app(s)
    app.dependency_overrides[get_settings] = lambda: s
    return TestClient(app)


def test_llm_health_reports_configuration_only_without_leaking_key() -> None:
    r = _client().get("/api/v1/health/llm")
    assert r.status_code == 503 and r.json() == {"status": "not_configured"}
    r = _client(groq_api_key="gsk_supersecret").get("/health/llm")
    assert r.status_code == 200 and r.json() == {"status": "configured"}
    assert "gsk_" not in r.text


def test_vector_store_health_ok_with_local_persistence(tmp_path: object) -> None:
    c = _client(chroma_persist_path=str(tmp_path))
    r = c.get("/api/v1/health/vector-store")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_vector_store_health_unavailable_is_sanitised() -> None:
    class Broken(InMemoryVectorStore):
        def healthcheck(self) -> bool:
            return False

    c = _client()
    c.app.dependency_overrides[get_vector_store] = lambda: Broken()  # type: ignore[attr-defined]
    c.app.state.vector_store = Broken()  # type: ignore[attr-defined]
    r = c.get("/health/vector-store")
    assert r.status_code == 503 and r.json() == {"status": "unavailable"}
