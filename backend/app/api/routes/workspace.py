"""Document, career-intelligence and report endpoints shared by guests and registered users.

One router factory is mounted twice: under ``/guest`` (authenticated by the secret guest token)
and at the root (authenticated by a user bearer token). Handlers only ever see a ``Ctx`` whose
principal was built server-side, so every query is automatically scoped to its owner.
"""


import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy import delete, select

from app.api.dependencies import (
    CurrentGuest,
    CurrentUser,
    DbSession,
    SettingsDep,
    get_llm,
    get_object_storage,
    get_processing_gate,
    get_rag_service,
    get_vector_store,
)
from app.core.config import Settings
from app.core.exceptions import InputValidationError, NotFoundError
from app.models import Document, JobDescription, Report, Resume
from app.rag.vector_store import VectorStore
from app.schemas.career_api import (
    JobDescriptionAnalyzeIn,
    JobDescriptionAnalyzeOut,
    MatchIn,
    MatchOut,
    OptimizeIn,
    OptimizeOut,
    ReportOut,
    ResumeAnalyzeIn,
    ResumeAnalyzeOut,
    SkillGapIn,
    SkillGapOut,
)
from app.schemas.guest import DocumentOut
from app.services import report_service
from app.services.career_service import CareerService
from app.services.document_intake import UploadedFile, add_document
from app.services.llm import LLMClient
from app.services.object_storage import ObjectStorage
from app.services.principal import Principal
from app.services.rag_service import RagService
from app.utils.rate_limit import ProcessingGate

# NOTE: no `from __future__ import annotations` here: FastAPI must resolve the locally defined
# Annotated dependency aliases at definition time.
__all__ = ["Ctx", "build_workspace_router", "guest_ctx", "user_ctx"]


@dataclass(frozen=True)
class Ctx:
    principal: Principal
    expires_at: datetime | None
    max_documents: int


def guest_ctx(guest: CurrentGuest, settings: SettingsDep) -> Ctx:
    return Ctx(Principal("guest", guest.id), guest.expires_at, settings.guest_max_documents)


def user_ctx(user: CurrentUser, settings: SettingsDep) -> Ctx:
    return Ctx(Principal("user", user.id), None, settings.user_max_documents)


def build_workspace_router(ctx_dep: Callable[..., Ctx]) -> APIRouter:
    router = APIRouter()
    CtxDep = Annotated[Ctx, Depends(ctx_dep)]
    Storage = Annotated[ObjectStorage, Depends(get_object_storage)]
    Llm = Annotated[LLMClient | None, Depends(get_llm)]

    def service(db: DbSession, ctx: Ctx, storage: ObjectStorage, settings: Settings,
                llm: LLMClient | None) -> CareerService:
        return CareerService(db, storage, settings, ctx.principal, ctx.expires_at, llm)

    # ------------------------------------------------------------ documents
    @router.post("/documents", response_model=DocumentOut, status_code=201, tags=["documents"])
    def upload_document(
        db: DbSession, ctx: CtxDep, settings: SettingsDep,
        rag: Annotated[RagService, Depends(get_rag_service)],
        store: Annotated[VectorStore, Depends(get_vector_store)],
        gate: Annotated[ProcessingGate, Depends(get_processing_gate)],
        kind: Annotated[str, Form()],
        file: Annotated[UploadFile | None, File()] = None,
        text: Annotated[str | None, Form(max_length=200_000)] = None,
    ) -> DocumentOut:
        if file is not None and text is not None:
            raise InputValidationError("Provide exactly one of a file or pasted text")
        uploaded = None
        if file is not None:
            data = file.file.read(settings.max_upload_bytes + 1)  # bounded read
            uploaded = UploadedFile(data, file.filename or "", file.content_type)
        if uploaded is None and text is None:
            raise InputValidationError("Provide a file or pasted text")
        with gate.acquire():
            result = add_document(
                db, rag, store, ctx.principal, kind, file=uploaded,
                text=text if uploaded is None else None,
                max_documents=ctx.max_documents, expires_at=ctx.expires_at,
            )
        return DocumentOut(document_id=result.document_id, kind=result.kind,
                           chunk_count=result.chunk_count, injection_flagged=result.injection_flagged)

    @router.get("/documents", response_model=list[DocumentOut], tags=["documents"])
    def list_documents(db: DbSession, ctx: CtxDep) -> list[DocumentOut]:
        docs = db.scalars(
            select(Document).where(ctx.principal.owns(Document), Document.deleted_at.is_(None))
            .order_by(Document.created_at)).all()
        return [DocumentOut(document_id=d.id, kind=d.kind, filename=d.filename,
                            created_at=d.created_at) for d in docs]

    @router.delete("/documents/{document_id}", status_code=204, tags=["documents"])
    def delete_document(
        document_id: uuid.UUID, db: DbSession, ctx: CtxDep,
        store: Annotated[VectorStore, Depends(get_vector_store)],
    ) -> Response:
        doc = db.scalar(select(Document).where(Document.id == document_id,
                                               ctx.principal.owns(Document)))
        if doc is None:
            raise NotFoundError()
        store.delete_document(ctx.principal.vector_owner, str(doc.id))
        db.execute(delete(Resume).where(Resume.document_id == doc.id))
        db.execute(delete(JobDescription).where(JobDescription.document_id == doc.id))
        db.delete(doc)
        db.commit()
        return Response(status_code=204)

    # ------------------------------------------------------------ career services
    @router.post("/resume/analyze", response_model=ResumeAnalyzeOut, tags=["resume"])
    def resume_analyze(body: ResumeAnalyzeIn, db: DbSession, ctx: CtxDep, settings: SettingsDep,
                       storage: Storage, llm: Llm) -> ResumeAnalyzeOut:
        return service(db, ctx, storage, settings, llm).analyze_resume(
            body.document_id, body.report_format)

    @router.post("/job-description/analyze", response_model=JobDescriptionAnalyzeOut,
                 tags=["job-description"])
    def jd_analyze(body: JobDescriptionAnalyzeIn, db: DbSession, ctx: CtxDep, settings: SettingsDep,
                   storage: Storage, llm: Llm) -> JobDescriptionAnalyzeOut:
        return service(db, ctx, storage, settings, llm).analyze_jd(
            body.document_id, body.report_format)

    @router.post("/career/match", response_model=MatchOut, tags=["career"])
    def career_match(body: MatchIn, db: DbSession, ctx: CtxDep, settings: SettingsDep,
                     storage: Storage, llm: Llm) -> MatchOut:
        return service(db, ctx, storage, settings, llm).match(
            body.resume_document_id, body.job_description_document_id, body.report_format,
            body.include_narrative)

    @router.post("/career/skill-gap", response_model=SkillGapOut, tags=["career"])
    def career_skill_gap(body: SkillGapIn, db: DbSession, ctx: CtxDep, settings: SettingsDep,
                         storage: Storage, llm: Llm) -> SkillGapOut:
        return service(db, ctx, storage, settings, llm).skill_gap(
            body.resume_document_id, body.job_description_document_id,
            body.declared_absent_skills, body.report_format)

    @router.post("/resume/optimize", response_model=OptimizeOut, tags=["resume"])
    def resume_optimize(body: OptimizeIn, db: DbSession, ctx: CtxDep, settings: SettingsDep,
                        storage: Storage, llm: Llm) -> OptimizeOut:
        return service(db, ctx, storage, settings, llm).optimize(
            body.resume_document_id, body.job_description_document_id,
            confirmed=body.confirmed_skills, approved=set(body.approved_change_ids),
            declined=set(body.declined_change_ids), fmt=body.report_format)

    # ------------------------------------------------------------ reports
    @router.get("/reports", response_model=list[ReportOut], tags=["reports"])
    def list_reports(db: DbSession, ctx: CtxDep) -> list[ReportOut]:
        rows = db.scalars(
            select(Report).where(ctx.principal.owns(Report), Report.deleted_at.is_(None))
            .order_by(Report.created_at.desc()).limit(100)).all()
        return [ReportOut(report_id=r.id, report_type=r.report_type, file_format=r.file_format,
                          filename=r.filename, created_at=r.created_at.isoformat()) for r in rows]

    @router.get("/reports/{report_id}/download", tags=["reports"])
    def download_report(report_id: uuid.UUID, db: DbSession, ctx: CtxDep,
                        storage: Storage) -> Response:
        report, data = report_service.get_report_bytes(db, storage, ctx.principal, report_id)
        return Response(
            content=data, media_type=report.content_type,
            headers={"Content-Disposition": f'attachment; filename="{report.filename}"'},
        )

    return router
