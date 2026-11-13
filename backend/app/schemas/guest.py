"""Request/response models for guest endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class GuestSessionOut(BaseModel):
    session_id: uuid.UUID
    token: str  # shown once; send as the X-Guest-Token header, never in a URL
    expires_at: datetime
    max_requests: int
    max_documents: int
    max_upload_mb: int


class DocumentOut(BaseModel):
    document_id: uuid.UUID
    kind: str
    chunk_count: int | None = None
    injection_flagged: bool | None = None
    filename: str | None = None
    created_at: datetime | None = None
