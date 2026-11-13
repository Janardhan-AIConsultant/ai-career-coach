"""Health endpoints. Public, so they return status only (no infrastructure details).

``/health`` and ``/api/v1/health`` are liveness. Database / vector-store / LLM probes
are added in Phase 3 when those components exist (no fake "ok" responses).
"""

import logging

from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DbSession, SettingsDep, get_embeddings, get_vector_store
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/database")
def health_database(db: DbSession, response: Response) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("database health check failed")
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ok"}


@router.get("/health/vector-store")
def health_vector_store(request: Request, settings: SettingsDep, response: Response) -> dict[str, str]:
    try:
        store = get_vector_store(request, settings, get_embeddings(request, settings))
        ok = store.healthcheck()
    except AppError:
        logger.exception("vector store health check failed")
        ok = False
    if not ok:
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ok"}


@router.get("/health/llm")
def health_llm(settings: SettingsDep, response: Response) -> dict[str, str]:
    """Configuration check only: it never calls Groq, so it costs no tokens or rate limit."""
    if not settings.groq_api_key.get_secret_value():
        response.status_code = 503
        return {"status": "not_configured"}
    return {"status": "configured"}
