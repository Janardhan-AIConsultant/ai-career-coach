"""Principal: who owns data (a guest session or a registered user). Built server-side only."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from app.models.documents import Document, JobDescription, Report, Resume
from app.rag.vector_store import Owner


@dataclass(frozen=True)
class Principal:
    kind: Literal["guest", "user"]
    id: uuid.UUID

    @property
    def vector_owner(self) -> Owner:
        return Owner(self.kind, str(self.id))

    @property
    def owner_columns(self) -> dict[str, uuid.UUID | None]:
        if self.kind == "guest":
            return {"owner_user_id": None, "guest_session_id": self.id}
        return {"owner_user_id": self.id, "guest_session_id": None}

    def owns(self, model: type[Document | Resume | JobDescription | Report]) -> Any:
        """SQL predicate restricting a query to this principal's rows."""
        column = model.guest_session_id if self.kind == "guest" else model.owner_user_id
        return column == self.id
