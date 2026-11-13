"""Fixtures for guest tests: in-memory DB/vector store/storage wired into the real app."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import (
    get_embeddings,
    get_object_storage,
    get_rag_service,
    get_vector_store,
)
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import create_app
from app.models import Base
from app.rag.embeddings import HashEmbeddings
from app.rag.vector_store import InMemoryVectorStore
from app.services.object_storage import InMemoryObjectStorage
from app.services.rag_service import RagService

RESUME = "Jane Doe\nSenior Python developer. Built FastAPI services, led 5 engineers. AWS, Docker."
JD = "Role: Backend Engineer. Required: Python, FastAPI, PostgreSQL. Preferred: Kubernetes."


@dataclass
class Env:
    client: TestClient
    db: Session
    store: InMemoryVectorStore
    storage: InMemoryObjectStorage
    settings: Settings

    def new_guest(self) -> tuple[dict[str, str], dict[str, str]]:
        """Create a session; return (auth headers, session json)."""
        r = self.client.post("/api/v1/guest/sessions")
        assert r.status_code == 201, r.text
        body = r.json()
        return {"X-Guest-Token": body["token"]}, body

    def upload_text(self, headers: dict[str, str], kind: str = "resume", text: str = RESUME) -> dict:  # type: ignore[type-arg]
        r = self.client.post("/api/v1/guest/documents", headers=headers,
                             data={"kind": kind, "text": text})
        assert r.status_code == 201, r.text
        return r.json()  # type: ignore[no-any-return]


def build_env(**overrides: object) -> Iterator[Env]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, jwt_secret_key="j" * 40, log_format="text", embedding_provider="hash",
        chunk_size=200, chunk_overlap=20, **overrides,
    )
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    store, storage = InMemoryVectorStore(), InMemoryObjectStorage()
    app = create_app(settings)
    rag = RagService(settings, HashEmbeddings(), store, None)
    app.dependency_overrides.update({
        get_settings: lambda: settings,
        get_db: lambda: db,
        get_vector_store: lambda: store,
        get_embeddings: lambda: HashEmbeddings(),
        get_object_storage: lambda: storage,
        get_rag_service: lambda: rag,
    })
    yield Env(TestClient(app), db, store, storage, settings)
    db.close()
    engine.dispose()


@pytest.fixture()
def env() -> Iterator[Env]:
    yield from build_env()
