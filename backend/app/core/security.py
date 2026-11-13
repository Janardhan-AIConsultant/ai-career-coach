"""Security primitives: password hashing, access tokens, guest capability tokens.

* Passwords: Argon2id (``argon2-cffi``); ``verify_password`` returns False on mismatch.
* Access tokens: HS256 JWT with ``sub``, ``jti``, ``iat``, ``exp``. Roles are NOT trusted from
  the token; authorization reloads the user from the database.
* Guest tokens: 256-bit random capability; only its SHA-256 is stored server-side, so a DB leak
  does not expose usable tokens. A browser-supplied session ID alone is never authentication.
Errors: invalid/expired tokens raise ``AuthenticationError`` (not retryable).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.exceptions import AuthenticationError

_hasher = PasswordHasher()
MIN_SECRET_LENGTH = 32


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, secret: str, expires_minutes: int) -> str:
    if len(secret) < MIN_SECRET_LENGTH:
        raise ValueError("JWT secret must be at least 32 characters")
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "typ": "access",
    }
    return jwt.encode(claims, secret, algorithm="HS256")


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    issued_at: int  # epoch seconds


def decode_access_token(token: str, secret: str) -> uuid.UUID:
    return decode_access_claims(token, secret).user_id


def decode_access_claims(token: str, secret: str) -> AccessClaims:
    try:
        claims = jwt.decode(
            token, secret, algorithms=["HS256"], options={"require": ["exp", "sub", "iat"]}
        )
        if claims.get("typ") != "access":
            raise AuthenticationError("Invalid token")
        return AccessClaims(uuid.UUID(claims["sub"]), int(claims["iat"]))
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token expired") from exc
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise AuthenticationError("Invalid token") from exc


def new_guest_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``. Give the raw token to the client once; store the hash."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_guest_token(raw)


def hash_guest_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
