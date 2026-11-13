"""Registered-user account endpoints. Every route acts only on the authenticated user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import (
    CurrentGuest,
    CurrentUser,
    DbSession,
    get_object_storage,
    get_vector_store,
)
from app.core.exceptions import InputValidationError
from app.rag.vector_store import VectorStore
from app.schemas.auth import (
    AccountDeleteIn,
    GuestImportIn,
    GuestImportOut,
    PasswordChangeIn,
    ProfileIO,
    UserOut,
    UserUpdateIn,
)
from app.services import account_service
from app.services.object_storage import ObjectStorage

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(body: UserUpdateIn, user: CurrentUser, db: DbSession) -> UserOut:
    user.display_name = body.display_name
    db.commit()
    return UserOut.model_validate(user)


@router.get("/me/profile", response_model=ProfileIO)
def get_profile(user: CurrentUser, db: DbSession) -> ProfileIO:
    profile = account_service.get_profile(db, user)
    return ProfileIO.model_validate(profile) if profile else ProfileIO()


@router.put("/me/profile", response_model=ProfileIO)
def put_profile(body: ProfileIO, user: CurrentUser, db: DbSession) -> ProfileIO:
    profile = account_service.upsert_profile(db, user, body.model_dump())
    return ProfileIO.model_validate(profile)


@router.post("/me/password", status_code=204)
def change_password(body: PasswordChangeIn, user: CurrentUser, db: DbSession) -> Response:
    account_service.change_password(db, user, body.current_password, body.new_password)
    return Response(status_code=204)


@router.delete("/me", status_code=204)
def delete_me(
    body: AccountDeleteIn,
    user: CurrentUser,
    db: DbSession,
    store: Annotated[VectorStore, Depends(get_vector_store)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    if not body.confirm:
        raise InputValidationError("Deletion must be confirmed")
    account_service.delete_account(db, store, storage, user, body.password)
    return Response(status_code=204)


@router.post("/me/import-guest-session", response_model=GuestImportOut)
def import_guest_session(
    body: GuestImportIn,
    user: CurrentUser,
    guest: CurrentGuest,  # proves ownership: requires the guest's secret X-Guest-Token
    db: DbSession,
    store: Annotated[VectorStore, Depends(get_vector_store)],
) -> GuestImportOut:
    documents, reports = account_service.import_guest_session(db, store, user, guest, body.consent)
    return GuestImportOut(documents=documents, reports=reports)
