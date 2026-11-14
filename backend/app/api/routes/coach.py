"""AI Career Coach endpoints (registered users): conversations, messages, SSE streaming."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    SettingsDep,
    get_embeddings,
    get_llm,
    get_vector_store,
    state_singleton,
)
from app.rag.embeddings import Embeddings
from app.rag.vector_store import VectorStore
from app.schemas.coach import (
    ConversationCreateIn,
    ConversationOut,
    ExchangeOut,
    MessageIn,
    MessageOut,
)
from app.services.coach_service import CoachService
from app.services.llm import LLMClient
from app.utils.rate_limit import SlidingWindowLimiter

router = APIRouter(prefix="/coach", tags=["coach"])


def get_coach(
    request: Request, db: DbSession, settings: SettingsDep, user: CurrentUser,
    store: Annotated[VectorStore, Depends(get_vector_store)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
    llm: Annotated[LLMClient | None, Depends(get_llm)],
) -> CoachService:
    return CoachService(db, settings, store, embeddings, llm, user)


Coach = Annotated[CoachService, Depends(get_coach)]


def _limit_messages(request: Request, settings: SettingsDep, user: CurrentUser) -> None:
    """Per-user hourly cap on coach messages (each one can cost an LLM call)."""
    limiter: SlidingWindowLimiter = state_singleton(
        request, "coach_limiter", lambda: SlidingWindowLimiter(settings.coach_messages_per_hour, 3600))
    limiter.check(str(user.id))


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(body: ConversationCreateIn, coach: Coach) -> ConversationOut:
    return ConversationOut.model_validate(coach.create_conversation(body.title))


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(coach: Coach, limit: Annotated[int, Query(ge=1, le=50)] = 20,
                       offset: Annotated[int, Query(ge=0)] = 0) -> list[ConversationOut]:
    return [ConversationOut.model_validate(c) for c in coach.list_conversations(limit, offset)]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: uuid.UUID, coach: Coach,
                  limit: Annotated[int, Query(ge=1, le=200)] = 100,
                  offset: Annotated[int, Query(ge=0)] = 0) -> list[MessageOut]:
    return [MessageOut.model_validate(m) for m in coach.messages(conversation_id, limit, offset)]


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: uuid.UUID, coach: Coach) -> Response:
    coach.delete(conversation_id)
    return Response(status_code=204)


@router.post("/conversations/{conversation_id}/messages", response_model=ExchangeOut,
             dependencies=[Depends(_limit_messages)])
def send_message(conversation_id: uuid.UUID, body: MessageIn, coach: Coach) -> ExchangeOut:
    turn = coach.begin(conversation_id, body.content, body.document_ids)
    assistant = coach.send(turn)
    return ExchangeOut(user_message=MessageOut.model_validate(turn.user_message),
                       assistant_message=MessageOut.model_validate(assistant))


@router.post("/conversations/{conversation_id}/messages/stream",
             dependencies=[Depends(_limit_messages)])
def stream_message(conversation_id: uuid.UUID, body: MessageIn, coach: Coach) -> StreamingResponse:
    turn = coach.begin(conversation_id, body.content, body.document_ids)  # HTTP errors happen here
    return StreamingResponse(
        coach.stream(turn), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
