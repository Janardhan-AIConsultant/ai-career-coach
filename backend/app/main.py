"""FastAPI application factory.

Responsibilities: logging setup, CORS (explicit origins only), correlation-ID and
secure-header middleware, sanitised error handling, router registration.
Run: ``uvicorn app.main:app --host 0.0.0.0 --port $PORT`` from ``backend/``.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    admin,
    auth,
    certificates,
    coach,
    feedback,
    guest,
    health,
    interview,
    learning,
    portfolio,
    projects,
    users,
    workspace,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.logging_config import configure_logging, correlation_id

logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(
        settings.log_level,
        settings.log_format,
        settings.log_dir if settings.log_to_file else None,
    )
    app = FastAPI(title="AI Career Coach API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Guest-Token", "X-Correlation-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cid = uuid.uuid4().hex  # never trust a client-supplied ID for log integrity
        token = correlation_id.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        response.headers["X-Correlation-ID"] = cid
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        level = logging.ERROR if exc.status_code >= 500 else logging.INFO
        logger.log(level, "request failed", exc_info=exc.__cause__ or None,
                   extra={"code": exc.code, "path": request.url.path})
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo submitted values (they may contain passwords or personal data).
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "Invalid request",
                               "fields": fields}},
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error", exc_info=exc, extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error"}},
        )

    app.include_router(health.router)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(guest.router, prefix="/api/v1")
    app.include_router(interview.router, prefix="/api/v1")
    app.include_router(coach.router, prefix="/api/v1")
    app.include_router(learning.router, prefix="/api/v1")
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(certificates.router, prefix="/api/v1")
    app.include_router(portfolio.router, prefix="/api/v1")
    app.include_router(feedback.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(workspace.build_workspace_router(workspace.user_ctx), prefix="/api/v1")
    return app


app = create_app()
