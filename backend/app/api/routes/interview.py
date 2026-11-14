"""Interview preparation and mock-interview endpoints (registered users)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CurrentUser, DbSession, SettingsDep, get_object_storage
from app.interview.bank import INTERVIEW_KINDS, TOPICS
from app.schemas.interview import (
    AnswerIn,
    AnswerOut,
    MockSessionOut,
    MockStartIn,
    MockSummary,
    PrepareIn,
    PrepareOut,
    TopicsOut,
)
from app.services.interview_service import InterviewService
from app.services.object_storage import ObjectStorage

router = APIRouter(prefix="/interview", tags=["interview"])
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]


def _svc(db: DbSession, storage: ObjectStorage, settings: SettingsDep, user: CurrentUser) -> InterviewService:
    return InterviewService(db, storage, settings, user)


@router.get("/topics", response_model=TopicsOut)
def topics(user: CurrentUser) -> TopicsOut:
    return TopicsOut(kinds=list(INTERVIEW_KINDS), topics=TOPICS)


@router.post("/prepare", response_model=PrepareOut)
def prepare(body: PrepareIn, db: DbSession, storage: Storage, settings: SettingsDep,
            user: CurrentUser) -> PrepareOut:
    return _svc(db, storage, settings, user).prepare(body)


@router.post("/mock", response_model=MockSessionOut, status_code=201)
def start_mock(body: MockStartIn, db: DbSession, storage: Storage, settings: SettingsDep,
               user: CurrentUser) -> MockSessionOut:
    return _svc(db, storage, settings, user).start_mock(body)


@router.get("/mock", response_model=list[MockSessionOut])
def list_mocks(db: DbSession, storage: Storage, settings: SettingsDep, user: CurrentUser,
               limit: Annotated[int, Query(ge=1, le=50)] = 20,
               offset: Annotated[int, Query(ge=0)] = 0) -> list[MockSessionOut]:
    return _svc(db, storage, settings, user).list_mocks(limit, offset)


@router.get("/mock/{session_id}", response_model=MockSessionOut)
def get_mock(session_id: uuid.UUID, db: DbSession, storage: Storage, settings: SettingsDep,
             user: CurrentUser) -> MockSessionOut:
    return _svc(db, storage, settings, user).get_mock(session_id)


@router.post("/mock/{session_id}/answers", response_model=AnswerOut)
def answer(session_id: uuid.UUID, body: AnswerIn, db: DbSession, storage: Storage,
           settings: SettingsDep, user: CurrentUser) -> AnswerOut:
    return _svc(db, storage, settings, user).answer(session_id, body.question_id, body.answer)


@router.post("/mock/{session_id}/complete", response_model=MockSummary)
def complete(session_id: uuid.UUID, db: DbSession, storage: Storage, settings: SettingsDep,
             user: CurrentUser) -> MockSummary:
    return _svc(db, storage, settings, user).complete(session_id)
