"""Vector store abstraction with strict tenant isolation.

Isolation model: every stored chunk carries ``owner_type`` ("guest" | "user"), ``owner_id`` and
``document_id``. Every read/delete requires an ``Owner`` built server-side from the authenticated
principal, and the metadata filter is constructed *here*; callers cannot pass raw filters, so a
user-supplied filter can never widen a query. Document-scoped queries are AND-ed with the owner.

Implementations: ``ChromaVectorStore`` (persistent / HTTP / Chroma Cloud) and
``InMemoryVectorStore`` (tests, contract-identical). Errors: ``VectorStoreError``.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import chromadb

from app.core.config import Settings
from app.core.exceptions import VectorStoreError
from app.rag.chunking import Chunk
from app.rag.embeddings import Embeddings

logger = logging.getLogger(__name__)

OwnerType = Literal["guest", "user"]
COLLECTION_NAME = "career_documents"


@dataclass(frozen=True)
class Owner:
    owner_type: OwnerType
    owner_id: str

    def __post_init__(self) -> None:
        if self.owner_type not in ("guest", "user") or not self.owner_id:
            raise ValueError("A valid owner is required for every vector operation")


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    score: float


class VectorStore(Protocol):
    def add_chunks(
        self, owner: Owner, document_id: str, chunks: Sequence[Chunk], vectors: list[list[float]]
    ) -> int: ...

    def query(
        self,
        owner: Owner,
        vector: list[float],
        k: int,
        document_ids: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]: ...

    def delete_document(self, owner: Owner, document_id: str) -> None: ...

    def delete_owner(self, owner: Owner) -> None: ...

    def reassign_owner(self, source: Owner, target: Owner) -> int: ...

    def count(self, owner: Owner) -> int: ...

    def healthcheck(self) -> bool: ...


# ---------------------------------------------------------------- in-memory (tests)


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def add_chunks(
        self, owner: Owner, document_id: str, chunks: Sequence[Chunk], vectors: list[list[float]]
    ) -> int:
        if len(chunks) != len(vectors):
            raise VectorStoreError("Chunk/vector count mismatch")
        for c, v in zip(chunks, vectors, strict=True):
            self._rows.append(
                {"owner": owner, "doc": document_id, "idx": c.index, "text": c.text, "vec": v}
            )
        return len(chunks)

    def query(
        self,
        owner: Owner,
        vector: list[float],
        k: int,
        document_ids: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        rows = [r for r in self._rows if r["owner"] == owner]
        if document_ids is not None:
            rows = [r for r in rows if r["doc"] in set(document_ids)]
        scored = sorted(rows, key=lambda r: _cosine(vector, r["vec"]), reverse=True)[:k]
        return [
            RetrievedChunk(f"{r['doc']}:{r['idx']}", r["doc"], r["idx"], r["text"],
                           _cosine(vector, r["vec"]))
            for r in scored
        ]

    def delete_document(self, owner: Owner, document_id: str) -> None:
        self._rows = [r for r in self._rows if not (r["owner"] == owner and r["doc"] == document_id)]

    def delete_owner(self, owner: Owner) -> None:
        self._rows = [r for r in self._rows if r["owner"] != owner]

    def reassign_owner(self, source: Owner, target: Owner) -> int:
        moved = 0
        for r in self._rows:
            if r["owner"] == source:
                r["owner"] = target
                moved += 1
        return moved

    def count(self, owner: Owner) -> int:
        return sum(1 for r in self._rows if r["owner"] == owner)

    def healthcheck(self) -> bool:
        return True


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# ---------------------------------------------------------------- Chroma


@contextmanager
def _wrap_chroma(operation: str) -> Iterator[None]:
    try:
        yield
    except VectorStoreError:
        raise
    except Exception as exc:  # chromadb raises many unrelated exception types
        logger.error("vector store operation failed", extra={"operation": operation})
        raise VectorStoreError() from exc


def _owner_where(owner: Owner, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    clauses: list[dict[str, Any]] = [
        {"owner_type": {"$eq": owner.owner_type}},
        {"owner_id": {"$eq": owner.owner_id}},
    ]
    if extra:
        clauses.append(extra)
    return {"$and": clauses}


class ChromaVectorStore:
    def __init__(
        self, client: Any, embeddings: Embeddings, collection_name: str = COLLECTION_NAME
    ) -> None:
        self._embeddings = embeddings
        with _wrap_chroma("init"):
            self._client = client
            existing = {c.name for c in client.list_collections()}
            if collection_name in existing:
                meta = client.get_collection(collection_name).metadata or {}
                if (
                    meta.get("embedding_model") != embeddings.model_id
                    or meta.get("dimension") != embeddings.dimension
                ):
                    raise VectorStoreError(
                        "Existing collection was built with a different embedding model/"
                        "dimension; re-embed into a new collection"
                    )
            self._col = client.get_or_create_collection(
                collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": embeddings.model_id,
                    "dimension": embeddings.dimension,
                },
            )

    def add_chunks(
        self, owner: Owner, document_id: str, chunks: Sequence[Chunk], vectors: list[list[float]]
    ) -> int:
        if len(chunks) != len(vectors):
            raise VectorStoreError("Chunk/vector count mismatch")
        if not chunks:
            return 0
        if any(len(v) != self._embeddings.dimension for v in vectors):
            raise VectorStoreError("Embedding dimension mismatch")
        with _wrap_chroma("add"):
            self._col.add(
                ids=[f"{owner.owner_type}:{owner.owner_id}:{document_id}:{c.index}" for c in chunks],
                embeddings=vectors,
                documents=[c.text for c in chunks],
                metadatas=[
                    {
                        "owner_type": owner.owner_type,
                        "owner_id": owner.owner_id,
                        "document_id": document_id,
                        "chunk_index": c.index,
                        "embedding_model": self._embeddings.model_id,
                    }
                    for c in chunks
                ],
            )
        return len(chunks)

    def query(
        self,
        owner: Owner,
        vector: list[float],
        k: int,
        document_ids: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        extra = None
        if document_ids is not None:
            if not document_ids:
                return []
            extra = {"document_id": {"$in": list(document_ids)}}
        with _wrap_chroma("query"):
            res = self._col.query(
                query_embeddings=[vector], n_results=k, where=_owner_where(owner, extra),
                include=["documents", "metadatas", "distances"],
            )
        out: list[RetrievedChunk] = []
        for cid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0],
            strict=True,
        ):
            out.append(RetrievedChunk(cid, str(meta["document_id"]), int(meta["chunk_index"]),
                                      doc, 1.0 - float(dist)))
        return out

    def delete_document(self, owner: Owner, document_id: str) -> None:
        with _wrap_chroma("delete_document"):
            self._col.delete(where=_owner_where(owner, {"document_id": {"$eq": document_id}}))

    def delete_owner(self, owner: Owner) -> None:
        with _wrap_chroma("delete_owner"):
            self._col.delete(where=_owner_where(owner))

    def reassign_owner(self, source: Owner, target: Owner) -> int:
        """Re-tag every chunk of ``source`` as owned by ``target`` (guest -> account import)."""
        with _wrap_chroma("reassign_owner"):
            found = self._col.get(where=_owner_where(source), include=["metadatas"])
            ids = found["ids"]
            if not ids:
                return 0
            metas = [
                {**m, "owner_type": target.owner_type, "owner_id": target.owner_id}
                for m in found["metadatas"]
            ]
            self._col.update(ids=ids, metadatas=metas)
            return len(ids)

    def count(self, owner: Owner) -> int:
        with _wrap_chroma("count"):
            return len(self._col.get(where=_owner_where(owner), include=[])["ids"])

    def healthcheck(self) -> bool:
        try:
            self._client.heartbeat()
        except Exception:
            logger.exception("vector store heartbeat failed")
            return False
        return True


def create_vector_store(settings: Settings, embeddings: Embeddings) -> VectorStore:
    """Choose Chroma Cloud, a Chroma server, or local persistence from configuration."""
    with _wrap_chroma("connect"):
        if settings.chroma_api_key.get_secret_value():
            client = chromadb.CloudClient(
                tenant=settings.chroma_tenant or None,
                database=settings.chroma_database or None,
                api_key=settings.chroma_api_key.get_secret_value(),
            )
        elif settings.chroma_host:
            client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        else:
            client = chromadb.PersistentClient(path=settings.chroma_persist_path)
    return ChromaVectorStore(client, embeddings)
