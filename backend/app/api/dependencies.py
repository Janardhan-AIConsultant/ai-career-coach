"""FastAPI dependencies: DB session, current user, admin guard, guest session.

Authorization always reloads the user from the database; roles in tokens are never trusted.
Guests authenticate with the secret ``X-Guest-Token`` header (never a URL parameter); the
token hash is looked up server-side and expiry is enforced.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    GuestSessionExpiredError,
    RateLimitExceededError,
)
from app.core.security import decode_access_claims, hash_guest_token
from app.models import GuestSession, User
from app.rag.embeddings import Embeddings, create_embeddings
from app.rag.vector_store import VectorStore, create_vector_store
from app.services.llm import GroqLLM, LLMClient
from app.services.object_storage import ObjectStorage, create_object_storage
from app.services.rag_service import RagService
from app.utils.rate_limit import ProcessingGate, SlidingWindowLimiter


def get_embeddings(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> Embeddings:
    """Shared, process-wide embedding client (immutable config; holds no user data)."""
    if not hasattr(request.app.state, "embeddings"):
        request.app.state.embeddings = create_embeddings(settings)
    return request.app.state.embeddings  # type: ignore[no-any-return]


def get_vector_store(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> VectorStore:
    if not hasattr(request.app.state, "vector_store"):
        request.app.state.vector_store = create_vector_store(settings, embeddings)
    return request.app.state.vector_store  # type: ignore[no-any-return]


DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite returns naive datetimes


def get_current_user(
    db: DbSession,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError()
    claims = decode_access_claims(
        authorization[7:].strip(), settings.jwt_secret_key.get_secret_value()
    )
    user = db.scalar(select(User).where(User.id == claims.user_id, User.deleted_at.is_(None)))
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid token")
    if user.tokens_valid_after is not None and claims.issued_at < int(
        _aware(user.tokens_valid_after).timestamp()
    ):
        raise AuthenticationError("Token revoked")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise AuthorizationError()
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_guest_session(
    db: DbSession,
    settings: SettingsDep,
    x_guest_token: Annotated[str | None, Header()] = None,
) -> GuestSession:
    if not x_guest_token:
        raise GuestSessionExpiredError()
    session = db.scalar(
        select(GuestSession).where(
            GuestSession.token_hash == hash_guest_token(x_guest_token),
            GuestSession.deleted_at.is_(None),
        )
    )
    if session is None or _aware(session.expires_at) <= datetime.now(UTC):
        raise GuestSessionExpiredError()
    if session.request_count >= settings.max_requests_per_session:
        raise RateLimitExceededError("Guest session request quota exceeded")
    session.request_count += 1
    db.commit()
    return session


CurrentGuest = Annotated[GuestSession, Depends(get_guest_session)]


def state_singleton(request: Request, name: str, factory: Callable[[], Any]) -> Any:
    if not hasattr(request.app.state, name):
        setattr(request.app.state, name, factory())
    return getattr(request.app.state, name)


def get_object_storage(request: Request, settings: SettingsDep) -> ObjectStorage:
    return state_singleton(request, "object_storage", lambda: create_object_storage(settings))  # type: ignore[no-any-return]


def get_llm(request: Request, settings: SettingsDep) -> LLMClient | None:
    """Shared Groq client, or None when no API key is configured."""
    return state_singleton(  # type: ignore[no-any-return]
        request, "llm",
        lambda: GroqLLM(settings) if settings.groq_api_key.get_secret_value() else None,
    )


def get_rag_service(
    request: Request,
    settings: SettingsDep,
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
    store: Annotated[VectorStore, Depends(get_vector_store)],
    llm: Annotated[LLMClient | None, Depends(get_llm)],
) -> RagService:
    def build() -> RagService:
        return RagService(settings, embeddings, store, llm)

    return state_singleton(request, "rag_service", build)  # type: ignore[no-any-return]


def get_processing_gate(request: Request, settings: SettingsDep) -> ProcessingGate:
    return state_singleton(  # type: ignore[no-any-return]
        request, "processing_gate", lambda: ProcessingGate(settings.max_concurrent_ingestions)
    )


def limit_guest_session_creation(request: Request, settings: SettingsDep) -> None:
    """Per-client-IP cap on new guest sessions (X-Forwarded-For is deliberately not trusted)."""
    limiter: SlidingWindowLimiter = state_singleton(
        request, "session_limiter",
        lambda: SlidingWindowLimiter(settings.guest_sessions_per_ip_per_hour, 3600),
    )
    limiter.check(request.client.host if request.client else "unknown")
