"""Models for certificates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CertType = Literal["learning_completion", "assessment", "project_completion"]


class EligibilityItem(BaseModel):
    certificate_type: CertType
    source_id: uuid.UUID
    label: str
    score: float | None = None


class IssueIn(BaseModel):
    certificate_type: CertType
    source_id: uuid.UUID
    learner_name: str | None = Field(default=None, max_length=80)  # name printed on the certificate (public)


class CertificateOut(BaseModel):
    certificate_id: str
    certificate_type: CertType
    title: str
    topic: str
    learner_name: str
    score: float | None
    status: str
    issued_at: datetime
    verification_url: str
    notice: str


class PublicCertificate(BaseModel):
    certificate_id: str
    certificate_type: CertType
    title: str
    topic: str
    learner_name: str
    score: float | None
    issued_at: datetime
    revoked_at: datetime | None = None


class VerifyOut(BaseModel):
    status: Literal["valid", "revoked", "invalid"]
    certificate: PublicCertificate | None
    notice: str


class RevokeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
