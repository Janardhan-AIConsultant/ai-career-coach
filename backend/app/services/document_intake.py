"""Document intake: validate -> extract -> index -> persist rows, for guests and users alike.

Order matters for safety: nothing is written to the database until validation, extraction and
vector indexing succeed; if the DB commit then fails, the vectors are removed (compensation).
Original upload bytes are not stored; only extracted text (needed for later analysis) and vectors
are kept, and both are deleted with the owner's data. Text and filenames are never logged.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.constants import DOCUMENT_KINDS
from app.core.exceptions import DatabaseError, InputValidationError, RateLimitExceededError
from app.guardrails.file_validation import sanitize_filename
from app.models import Document, JobDescription, Resume
from app.rag.vector_store import VectorStore
from app.services.principal import Principal
from app.services.rag_service import RagService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadedFile:
    data: bytes
    filename: str
    content_type: str | None


@dataclass(frozen=True)
class IntakeResult:
    document_id: uuid.UUID
    kind: str
    chunk_count: int
    injection_flagged: bool


def add_document(
    db: Session,
    rag: RagService,
    store: VectorStore,
    principal: Principal,
    kind: str,
    *,
    file: UploadedFile | None,
    text: str | None,
    max_documents: int,
    expires_at: datetime | None,
) -> IntakeResult:
    if kind not in DOCUMENT_KINDS:
        raise InputValidationError("Unknown document kind")
    if (file is None) == (text is None):
        raise InputValidationError("Provide exactly one of a file or pasted text")

    existing = db.scalar(
        select(func.count()).select_from(Document).where(
            principal.owns(Document), Document.deleted_at.is_(None)
        )
    )
    if (existing or 0) >= max_documents:
        raise RateLimitExceededError("Document quota reached for this session")

    document_id = uuid.uuid4()
    owner = principal.vector_owner
    if file is not None:
        result = rag.ingest_file(owner, str(document_id), file.data, file.filename, file.content_type)
        filename, ctype, raw = sanitize_filename(file.filename), file.content_type, file.data
    else:
        assert text is not None
        result = rag.ingest_text(owner, str(document_id), text)
        filename, ctype, raw = "pasted-text.txt", "text/plain", text.encode("utf-8")

    try:
        db.add(
            Document(
                id=document_id, kind=kind, filename=filename,
                content_type=(ctype or "application/octet-stream")[:100], size_bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(), expires_at=expires_at,
                **principal.owner_columns,
            )
        )
        db.flush()  # Document must exist before the child row references it
        child = Resume if kind == "resume" else JobDescription
        db.add(child(document_id=document_id, parsed={"text": result.text},
                     **principal.owner_columns))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        store.delete_document(owner, str(document_id))  # compensate: no orphan vectors
        logger.exception("failed to persist document")
        raise DatabaseError() from exc

    return IntakeResult(document_id, kind, result.chunk_count, bool(result.injection_flags))
