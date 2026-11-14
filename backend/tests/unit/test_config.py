import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def make(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_defaults_valid() -> None:
    s = make()
    assert s.chunk_overlap < s.chunk_size
    assert s.cors_origin_list == ["http://localhost:5173"]


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValidationError):
        make(chunk_size=200, chunk_overlap=200)


def test_production_requires_strong_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        make(app_env="production", jwt_secret_key="short")
    assert make(app_env="production", jwt_secret_key="x" * 32).app_env == "production"


def test_secrets_not_in_repr() -> None:
    assert "supersecret" not in repr(make(groq_api_key="supersecret"))


def test_cors_list_parsing() -> None:
    assert make(cors_origins="http://a.com, http://b.com").cors_origin_list == [
        "http://a.com",
        "http://b.com",
    ]


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
