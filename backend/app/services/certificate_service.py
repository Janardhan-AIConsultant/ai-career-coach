"""Certificates: eligibility from verified evidence, issuing, public verification, revocation.

Certificates are issued only when the server verifies the evidence itself:
* learning_completion: the user's roadmap is ``completed`` and its criteria (>=80% required
  activities AND every assessment passed) are still met.
* assessment: the user's own attempt passed the assessment's pass mark.
* project_completion: the user's own project evaluation passed (static evidence review).
There is no endpoint that issues a certificate from a client claim. One certificate per evidence
source (database unique constraint). Certificates are platform-issued, not externally accredited.
Verification is public but returns only the certificate facts and the learner name the owner chose.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    InputValidationError,
    NotFoundError,
    RateLimitExceededError,
)
from app.models import (
    Assessment,
    AssessmentAttempt,
    AuditLog,
    Certificate,
    LearningRoadmap,
    ProjectEvaluation,
    ProjectSubmission,
    User,
)
from app.schemas.certificates import (
    CertificateOut,
    EligibilityItem,
    PublicCertificate,
    VerifyOut,
)
from app.services.certificate_pdf import CertificateData, render_certificate
from app.services.learning_service import LearningService

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32 (no I, L, O, U)
CODE_RE = re.compile(r"^ACC-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_MARKUP = re.compile(r"[<>]")
TITLES = {"learning_completion": "Learning Completion Certificate", "assessment": "Assessment Certificate",
          "project_completion": "Project Completion Certificate"}
NOTICE = "Platform-issued certificate; not an externally accredited qualification."


def new_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    return f"ACC-{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def clean_name(name: str | None, fallback: str) -> str:
    cleaned = " ".join(_MARKUP.sub("", _CTRL.sub(" ", name or "")).split())[:80]
    if name and not cleaned:
        raise InputValidationError("Learner name is not valid")
    return cleaned or fallback[:80]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def certificate_out(c: Certificate, base_url: str) -> CertificateOut:
    return CertificateOut(
        certificate_id=c.certificate_code, certificate_type=c.certificate_type, title=c.title, topic=c.topic,
        learner_name=c.learner_name, score=c.score, status=c.status, issued_at=_aware(c.issued_at),
        verification_url=f"{base_url.rstrip('/')}/verify/{c.certificate_code}", notice=NOTICE)


class CertificateService:
    def __init__(self, db: Session, settings: Settings, user: User | None = None) -> None:
        self._db, self._s, self._user = db, settings, user

    # ------------------------------------------------------------ evidence lookups (user-scoped)
    def _roadmap_evidence(self, roadmap_id: uuid.UUID, learning: LearningService) -> tuple[LearningRoadmap, str]:
        assert self._user is not None
        r = self._db.scalar(select(LearningRoadmap).where(
            LearningRoadmap.id == roadmap_id, LearningRoadmap.user_id == self._user.id,
            LearningRoadmap.deleted_at.is_(None)))
        if r is None:
            raise NotFoundError("Roadmap not found")
        progress = learning.get(r.id).progress
        if r.status != "completed" or not progress.criteria_met:
            raise InputValidationError("The roadmap's completion requirements are not met")
        return r, f"roadmap:{r.id}"

    def _attempt_evidence(self, attempt_id: uuid.UUID) -> tuple[AssessmentAttempt, Assessment, str]:
        assert self._user is not None
        a = self._db.scalar(select(AssessmentAttempt).where(
            AssessmentAttempt.id == attempt_id, AssessmentAttempt.user_id == self._user.id))
        if a is None:
            raise NotFoundError("Assessment attempt not found")
        asm = self._db.get(Assessment, a.assessment_id)
        assert asm is not None
        if not a.passed or a.score < asm.pass_score:
            raise InputValidationError("This attempt did not meet the assessment's pass criteria")
        return a, asm, f"assessment:{asm.id}"

    def _project_evidence(self, evaluation_id: uuid.UUID) -> tuple[ProjectEvaluation, ProjectSubmission, str]:
        assert self._user is not None
        ev = self._db.get(ProjectEvaluation, evaluation_id)
        sub = self._db.get(ProjectSubmission, ev.submission_id) if ev else None
        if ev is None or sub is None or sub.user_id != self._user.id or sub.deleted_at is not None:
            raise NotFoundError("Project evaluation not found")
        if not ev.passed:
            raise InputValidationError("This project evaluation did not meet the requirements")
        return ev, sub, f"project:{sub.id}"

    # ------------------------------------------------------------ eligibility
    def eligibility(self, learning: LearningService) -> list[EligibilityItem]:
        assert self._user is not None
        have = set(self._db.scalars(select(Certificate.source_key).where(
            Certificate.user_id == self._user.id, Certificate.status == "valid")).all())
        items: list[EligibilityItem] = []
        for r in self._db.scalars(select(LearningRoadmap).where(
                LearningRoadmap.user_id == self._user.id, LearningRoadmap.status == "completed",
                LearningRoadmap.deleted_at.is_(None))).all():
            if f"roadmap:{r.id}" not in have:
                items.append(EligibilityItem(certificate_type="learning_completion", source_id=r.id, label=r.title))
        best: dict[uuid.UUID, AssessmentAttempt] = {}
        for a in self._db.scalars(select(AssessmentAttempt).where(
                AssessmentAttempt.user_id == self._user.id, AssessmentAttempt.passed.is_(True))).all():
            if a.assessment_id not in best or a.score > best[a.assessment_id].score:
                best[a.assessment_id] = a
        for aid, a in best.items():
            asm = self._db.get(Assessment, aid)
            if asm and a.score >= asm.pass_score and f"assessment:{aid}" not in have:
                items.append(EligibilityItem(certificate_type="assessment", source_id=a.id, label=asm.title, score=a.score))
        for ev in self._db.scalars(select(ProjectEvaluation).join(
                ProjectSubmission, ProjectSubmission.id == ProjectEvaluation.submission_id).where(
                ProjectSubmission.user_id == self._user.id, ProjectSubmission.deleted_at.is_(None),
                ProjectEvaluation.passed.is_(True))).all():
            sub = self._db.get(ProjectSubmission, ev.submission_id)
            if sub and f"project:{sub.id}" not in have and not any(i.source_id == ev.id for i in items):
                items.append(EligibilityItem(certificate_type="project_completion", source_id=ev.id,
                                             label=sub.title, score=ev.overall_score))
        return items

    # ------------------------------------------------------------ issuing
    def issue(self, certificate_type: str, source_id: uuid.UUID, learner_name: str | None,
              learning: LearningService) -> CertificateOut:
        assert self._user is not None
        since = datetime.now(UTC) - timedelta(hours=24)
        if (self._db.scalar(select(func.count()).select_from(Certificate).where(
                Certificate.user_id == self._user.id, Certificate.issued_at >= since)) or 0) >= self._s.certificates_per_day:
            raise RateLimitExceededError("Daily certificate limit reached")
        name = clean_name(learner_name, self._user.display_name)
        fields: dict[str, object] = {}
        if certificate_type == "learning_completion":
            r, key = self._roadmap_evidence(source_id, learning)
            topic, score, fields = r.title, None, {"roadmap_id": r.id}
        elif certificate_type == "assessment":
            a, asm, key = self._attempt_evidence(source_id)
            topic, score, fields = asm.title, a.score, {"attempt_id": a.id}
        elif certificate_type == "project_completion":
            ev, sub, key = self._project_evidence(source_id)
            topic, score, fields = sub.title, ev.overall_score, {"evaluation_id": ev.id}
        else:
            raise InputValidationError("Unsupported certificate type")
        if self._db.scalar(select(Certificate.id).where(Certificate.user_id == self._user.id,
                                                        Certificate.source_key == key)):
            raise ConflictError("A certificate has already been issued for this achievement")
        cert = Certificate(
            certificate_code=new_code(), user_id=self._user.id, learner_name=name, source_key=key,
            certificate_type=certificate_type, title=TITLES[certificate_type], topic=topic, score=score,
            status="valid", issued_at=datetime.now(UTC), **fields)
        self._db.add(cert)
        self._db.add(AuditLog(actor_user_id=self._user.id, action="certificate.issued", entity_type="certificate",
                              entity_id=cert.certificate_code, details={"type": certificate_type}))
        try:
            self._db.commit()
        except IntegrityError as exc:  # concurrent duplicate request or code collision
            self._db.rollback()
            raise ConflictError("A certificate has already been issued for this achievement") from exc
        return certificate_out(cert, self._s.frontend_url)

    # ------------------------------------------------------------ owner views
    def list_mine(self) -> list[CertificateOut]:
        assert self._user is not None
        rows = self._db.scalars(select(Certificate).where(Certificate.user_id == self._user.id)
                                .order_by(Certificate.issued_at.desc())).all()
        return [certificate_out(c, self._s.frontend_url) for c in rows]

    def pdf(self, code: str) -> tuple[bytes, str]:
        assert self._user is not None
        c = self._db.scalar(select(Certificate).where(Certificate.certificate_code == code.upper(),
                                                      Certificate.user_id == self._user.id))
        if c is None:
            raise NotFoundError()
        if c.status == "revoked":
            raise ConflictError("This certificate has been revoked")
        out = certificate_out(c, self._s.frontend_url)
        data = render_certificate(CertificateData(
            code=c.certificate_code, certificate_type=c.certificate_type, title=c.title, topic=c.topic,
            learner_name=c.learner_name, issued_at=_aware(c.issued_at), score=c.score,
            verification_url=out.verification_url))
        return data, f"certificate-{c.certificate_code}.pdf"

    # ------------------------------------------------------------ public verification
    def verify(self, code: str) -> VerifyOut:
        code = (code or "").strip().upper()
        c = self._db.scalar(select(Certificate).where(Certificate.certificate_code == code)) if CODE_RE.match(code) else None
        if c is None:
            return VerifyOut(status="invalid", certificate=None, notice="No certificate with this ID was found.")
        pub = PublicCertificate(
            certificate_id=c.certificate_code, certificate_type=c.certificate_type, title=c.title,
            topic=c.topic, learner_name=c.learner_name, score=c.score, issued_at=_aware(c.issued_at),
            revoked_at=_aware(c.revoked_at) if c.revoked_at else None)
        return VerifyOut(status="revoked" if c.status == "revoked" else "valid", certificate=pub, notice=NOTICE)

    # ------------------------------------------------------------ admin
    def revoke(self, admin: User, code: str, reason: str) -> CertificateOut:
        c = self._db.scalar(select(Certificate).where(Certificate.certificate_code == code.strip().upper()))
        if c is None:
            raise NotFoundError()
        if c.status == "revoked":
            raise ConflictError("Certificate is already revoked")
        c.status, c.revoked_at, c.revoked_reason = "revoked", datetime.now(UTC), reason.strip()
        self._db.add(AuditLog(actor_user_id=admin.id, action="certificate.revoked", entity_type="certificate",
                              entity_id=c.certificate_code, details={"type": c.certificate_type}))
        self._db.commit()
        return certificate_out(c, self._s.frontend_url)

    def list_all(self, limit: int, offset: int) -> list[CertificateOut]:
        rows = self._db.scalars(select(Certificate).order_by(Certificate.issued_at.desc()).limit(limit).offset(offset)).all()
        return [certificate_out(c, self._s.frontend_url) for c in rows]
