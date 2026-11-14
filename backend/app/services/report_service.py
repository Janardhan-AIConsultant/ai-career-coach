"""Report persistence and ownership-checked retrieval.

Report bytes go to object storage; metadata to the ``reports`` table. Ids are random UUIDv4 and
are never sufficient alone: every lookup is scoped to the requesting principal and expiry, and a
miss returns ``NotFoundError`` (404) so ids of other users' reports cannot be probed.
Generating report *content* (PDF/DOCX rendering) arrives with the career-intelligence phase.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import REPORT_FORMATS, REPORT_TYPES
from app.core.exceptions import InputValidationError, NotFoundError
from app.guardrails.file_validation import sanitize_filename
from app.models import Report
from app.services.object_storage import ObjectStorage
from app.services.principal import Principal

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def storage_key(principal: Principal, report_id: uuid.UUID, fmt: str) -> str:
    return f"{principal.kind}/{principal.id}/{report_id}.{fmt}"


def create_report(
    db: Session,
    storage: ObjectStorage,
    principal: Principal,
    *,
    report_type: str,
    file_format: str,
    data: bytes,
    filename: str,
    max_bytes: int,
    expires_at: datetime | None,
) -> Report:
    if report_type not in REPORT_TYPES or file_format not in REPORT_FORMATS:
        raise InputValidationError("Unsupported report type or format")
    if not data or len(data) > max_bytes:
        raise InputValidationError("Report size is not allowed")
    report_id = uuid.uuid4()
    key = storage_key(principal, report_id, file_format)
    storage.put(key, data)
    report = Report(
        id=report_id, report_type=report_type, file_format=file_format,
        filename=sanitize_filename(filename), content_type=CONTENT_TYPES[file_format],
        size_bytes=len(data), storage_key=key, expires_at=expires_at, **principal.owner_columns,
    )
    db.add(report)
    db.commit()
    return report


def get_report_bytes(
    db: Session, storage: ObjectStorage, principal: Principal, report_id: uuid.UUID
) -> tuple[Report, bytes]:
    report = db.scalar(
        select(Report).where(
            Report.id == report_id, principal.owns(Report), Report.deleted_at.is_(None)
        )
    )
    if report is None or (report.expires_at and _aware(report.expires_at) <= datetime.now(UTC)):
        raise NotFoundError()
    return report, storage.get(report.storage_key)
