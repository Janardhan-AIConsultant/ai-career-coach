"""Shared fixtures: in-memory SQLite DB, app with overridden settings/DB, helpers."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import hash_password, new_guest_token
from app.main import create_app
from app.models import Base, GuestSession, User
from tests.guest_fixtures import env  # noqa: F401  (registers the `env` fixture)

JWT_SECRET = "t" * 40


@pytest.fixture()
def settings() -> Settings:
    return Settings(_env_file=None, jwt_secret_key=JWT_SECRET, log_format="text",
                    max_requests_per_session=3)  # type: ignore[call-arg]


@pytest.fixture()
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(settings: Settings, db_session: Session) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def make_user(db: Session, email: str = "u@example.com", role: str = "user") -> User:
    user = User(email=email, password_hash=hash_password("password123"), display_name="U",
                role=role)
    db.add(user)
    db.commit()
    return user


def make_guest(db: Session, minutes: int = 60) -> tuple[GuestSession, str]:
    raw, hashed = new_guest_token()
    guest = GuestSession(token_hash=hashed, expires_at=datetime.now(UTC) + timedelta(minutes=minutes))
    db.add(guest)
    db.commit()
    return guest, raw
