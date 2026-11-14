import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_guest_token,
    hash_password,
    new_guest_token,
    verify_password,
)

SECRET = "s" * 40


def test_password_hash_and_verify() -> None:
    h = hash_password("correct horse")
    assert h != "correct horse" and h.startswith("$argon2id$")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "not-a-hash")


def test_short_password_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("short")


def test_access_token_roundtrip() -> None:
    uid = uuid.uuid4()
    assert decode_access_token(create_access_token(uid, SECRET, 5), SECRET) == uid


def test_token_wrong_secret_rejected() -> None:
    token = create_access_token(uuid.uuid4(), SECRET, 5)
    with pytest.raises(AuthenticationError):
        decode_access_token(token, "z" * 40)


def test_expired_token_rejected() -> None:
    past = datetime.now(UTC) - timedelta(minutes=5)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "iat": past, "exp": past + timedelta(minutes=1), "typ": "access"},
        SECRET, algorithm="HS256",
    )
    with pytest.raises(AuthenticationError, match="expired"):
        decode_access_token(token, SECRET)


def test_alg_none_and_garbage_rejected() -> None:
    forged = jwt.encode({"sub": str(uuid.uuid4()), "exp": 9999999999, "iat": 1, "typ": "access"},
                        key="", algorithm="none")
    for bad in (forged, "garbage"):
        with pytest.raises(AuthenticationError):
            decode_access_token(bad, SECRET)


def test_weak_secret_refused() -> None:
    with pytest.raises(ValueError):
        create_access_token(uuid.uuid4(), "short", 5)


def test_guest_token_hashing() -> None:
    raw, hashed = new_guest_token()
    assert hashed == hash_guest_token(raw) and raw != hashed and len(raw) >= 43
    assert new_guest_token()[0] != raw
