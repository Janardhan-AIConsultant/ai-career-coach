"""Auth endpoints: register, login, refresh, logout.

The access token is returned in the JSON body (the SPA keeps it in memory). The refresh token is
an HttpOnly cookie scoped to ``/api/v1/auth``; cookie-based endpoints (refresh/logout) also
verify the browser ``Origin`` header against the configured origins as CSRF defence in depth.
In production the cookie is ``Secure; SameSite=None`` (frontend and API are on different sites).
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response

from app.api.dependencies import DbSession, SettingsDep, state_singleton
from app.core.config import Settings
from app.core.exceptions import AuthorizationError
from app.schemas.auth import LoginIn, RegisterIn, TokenOut
from app.services import auth_service
from app.utils.rate_limit import SlidingWindowLimiter

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/api/v1/auth"


def _limit(request: Request, name: str, key: str, limit: int, window: float) -> None:
    limiter: SlidingWindowLimiter = state_singleton(
        request, f"limiter_{name}", lambda: SlidingWindowLimiter(limit, window)
    )
    limiter.check(key)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _require_trusted_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_origin_list:
        raise AuthorizationError("Origin not allowed")


def _set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    production = settings.app_env == "production"
    response.set_cookie(
        REFRESH_COOKIE, token, max_age=settings.refresh_token_expire_days * 86400,
        httponly=True, secure=production, samesite="none" if production else "lax",
        path=COOKIE_PATH,
    )


def _token_response(response: Response, settings: Settings,
                    tokens: auth_service.IssuedTokens) -> TokenOut:
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return TokenOut(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: DbSession,
             settings: SettingsDep) -> TokenOut:
    _limit(request, "register", _client_ip(request), settings.registrations_per_ip_per_hour, 3600)
    tokens = auth_service.register(
        db, settings, email=body.email, password=body.password, display_name=body.display_name
    )
    return _token_response(response, settings, tokens)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, response: Response, db: DbSession,
          settings: SettingsDep) -> TokenOut:
    n, window = settings.login_attempts_per_15_min, 900
    _limit(request, "login_ip", _client_ip(request), n * 3, window)
    email_key = hashlib.sha256(auth_service.normalize_email(body.email).encode()).hexdigest()
    _limit(request, "login_email", email_key, n, window)
    tokens = auth_service.login(db, settings, email=body.email, password=body.password)
    return _token_response(response, settings, tokens)


@router.post("/refresh", response_model=TokenOut)
def refresh(
    request: Request, response: Response, db: DbSession, settings: SettingsDep,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenOut:
    _require_trusted_origin(request, settings)
    tokens = auth_service.refresh(db, settings, refresh_token)
    return _token_response(response, settings, tokens)


@router.post("/logout", status_code=204)
def logout(
    request: Request, db: DbSession, settings: SettingsDep,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    _require_trusted_origin(request, settings)
    auth_service.logout(db, refresh_token)
    response = Response(status_code=204)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response
