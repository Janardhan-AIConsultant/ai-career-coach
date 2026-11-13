"""Application settings.

Purpose: single typed source of configuration, loaded from environment / ``.env``.
Inputs: environment variables (see ``.env.example``). Output: ``Settings`` via ``get_settings()``.
Errors: invalid values raise ``pydantic.ValidationError`` at startup (fail fast).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings. Secrets use ``SecretStr`` so they never appear in repr/logs."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_env: Literal["development", "test", "production"] = "development"

    # LLM (Groq)
    groq_api_key: SecretStr = SecretStr("")
    llm_model: str = "llama-3.1-8b-instant"
    llm_temperature: float = Field(0.2, ge=0.0, le=1.0)
    api_timeout: float = Field(30.0, gt=0)

    # Embeddings / vector store
    embedding_provider: str = "local-hf"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chroma_api_key: SecretStr = SecretStr("")
    chroma_tenant: str = ""
    chroma_database: str = ""
    chroma_host: str = ""  # local Chroma server (docker compose); empty => cloud/persistent
    chroma_port: int = 8000

    # Database / auth
    database_url: str = "postgresql+psycopg://career:career@localhost:5432/career_coach"
    jwt_secret_key: SecretStr = SecretStr("")
    access_token_expire_minutes: int = Field(30, gt=0)
    refresh_token_expire_days: int = Field(14, gt=0)
    login_attempts_per_15_min: int = Field(10, ge=1)
    registrations_per_ip_per_hour: int = Field(10, ge=1)

    # Guest sessions and uploads
    guest_session_expire_minutes: int = Field(60, gt=0)
    max_upload_size_mb: int = Field(5, gt=0, le=50)
    max_requests_per_session: int = Field(50, gt=0)

    guest_max_documents: int = Field(10, ge=1)
    user_max_documents: int = Field(50, ge=1)
    guest_sessions_per_ip_per_hour: int = Field(20, ge=1)
    max_concurrent_ingestions: int = Field(2, ge=1)
    max_report_bytes: int = Field(5 * 1024 * 1024, ge=1024)

    # AI coach / interview
    coach_messages_per_hour: int = Field(60, ge=1)
    coach_history_messages: int = Field(10, ge=0, le=50)
    coach_history_chars: int = Field(6000, ge=500)
    coach_max_message_chars: int = Field(4000, ge=100)
    coach_max_conversations: int = Field(100, ge=1)
    coach_max_messages: int = Field(200, ge=2)
    interview_answer_max_chars: int = Field(5000, ge=100)

    # Projects / certificates
    github_token: SecretStr = SecretStr("")  # optional: raises GitHub API rate limits
    project_pass_score: float = Field(70.0, ge=0, le=100)
    max_projects_per_user: int = Field(20, ge=1)
    certificates_per_day: int = Field(20, ge=1)
    verify_requests_per_minute: int = Field(60, ge=1)
    portfolio_requests_per_minute: int = Field(60, ge=1)

    # RAG
    chunk_size: int = Field(800, ge=100)
    chunk_overlap: int = Field(150, ge=0)
    retrieval_top_k: int = Field(6, ge=1, le=50)

    llm_max_tokens: int = Field(1024, ge=64, le=8192)
    llm_max_retries: int = Field(3, ge=0, le=6)
    max_context_chars: int = Field(12000, ge=500)
    max_document_chars: int = Field(100_000, ge=1000)
    max_pdf_pages: int = Field(50, ge=1)
    chroma_persist_path: str = "chroma_db"

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    log_dir: str = "logs"
    log_to_file: bool = False  # rotating file for local dev; console only in cloud

    # Web
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"

    # Object storage abstraction
    object_storage_backend: Literal["local", "s3"] = "local"
    object_storage_path: str = "storage"

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.app_env == "production" and len(self.jwt_secret_key.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings (immutable config only; no user data is cached)."""
    return Settings()
