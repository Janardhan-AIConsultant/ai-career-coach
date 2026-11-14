"""Retrieval: embeds the query and queries the store with a server-built owner filter."""

from __future__ import annotations

from collections.abc import Sequence

from app.rag.embeddings import Embeddings
from app.rag.vector_store import Owner, RetrievedChunk, VectorStore


def retrieve(
    store: VectorStore,
    embeddings: Embeddings,
    owner: Owner,
    question: str,
    *,
    top_k: int,
    document_ids: Sequence[str] | None = None,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """``owner`` must come from the authenticated principal, never from request data."""
    chunks = store.query(owner, embeddings.embed_query(question), top_k, document_ids)
    return [c for c in chunks if c.score >= min_score]
