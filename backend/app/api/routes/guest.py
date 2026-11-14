"""Guest (no-login) endpoints: session lifecycle plus the shared workspace routes.

Authentication is the secret ``X-Guest-Token`` header (see ``get_guest_session``). The session
routes live here; documents, the five career services and report download come from the shared
workspace router mounted with a guest context, so every query is scoped to the guest's session
and foreign ids return 404.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import (
    CurrentGuest,
    DbSession,
    SettingsDep,
    get_object_storage,
    get_vector_store,
    limit_guest_session_creation,
)
from app.api.routes.workspace import build_workspace_router, guest_ctx
from app.core.exceptions import NotFoundError
from app.rag.vector_store import VectorStore
from app.schemas.guest import GuestSessionOut
from app.services import guest_service
from app.services.object_storage import ObjectStorage

router = APIRouter(prefix="/guest", tags=["guest"])


@router.post("/sessions", response_model=GuestSessionOut, status_code=201,
             dependencies=[Depends(limit_guest_session_creation)])
def create_session(db: DbSession, settings: SettingsDep) -> GuestSessionOut:
    created = guest_service.create_guest_session(db, settings.guest_session_expire_minutes)
    return GuestSessionOut(
        session_id=created.session.id, token=created.token, expires_at=created.session.expires_at,
        max_requests=settings.max_requests_per_session, max_documents=settings.guest_max_documents,
        max_upload_mb=settings.max_upload_size_mb,
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: uuid.UUID,
    db: DbSession,
    guest: CurrentGuest,
    store: Annotated[VectorStore, Depends(get_vector_store)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    if session_id != guest.id:
        raise NotFoundError()  # never reveal whether another session exists
    guest_service.purge_guest_session(db, store, storage, guest.id)
    return Response(status_code=204)


router.include_router(build_workspace_router(guest_ctx))
