"""Isolation contract tests, run against both the in-memory and the real Chroma implementation."""

from __future__ import annotations

import uuid

import chromadb
import pytest

from app.core.exceptions import VectorStoreError
from app.rag.chunking import Chunk
from app.rag.embeddings import HashEmbeddings
from app.rag.retrieval import retrieve
from app.rag.vector_store import ChromaVectorStore, InMemoryVectorStore, Owner, VectorStore

EMB = HashEmbeddings()
ALICE = Owner("user", "alice")
BOB = Owner("user", "bob")
GUEST_A = Owner("guest", "ga")
GUEST_B = Owner("guest", "gb")


@pytest.fixture(params=["memory", "chroma"])
def store(request: pytest.FixtureRequest) -> VectorStore:
    if request.param == "memory":
        return InMemoryVectorStore()
    return ChromaVectorStore(chromadb.EphemeralClient(), EMB, f"t_{uuid.uuid4().hex}")


def put(store: VectorStore, owner: Owner, doc: str, texts: list[str]) -> None:
    chunks = [Chunk(i, t) for i, t in enumerate(texts)]
    store.add_chunks(owner, doc, chunks, EMB.embed_documents(texts))


def ask(store: VectorStore, owner: Owner, q: str, docs: list[str] | None = None) -> list[str]:
    return [c.text for c in retrieve(store, EMB, owner, q, top_k=10, document_ids=docs)]


def test_cross_user_isolation(store: VectorStore) -> None:
    put(store, ALICE, "d1", ["alice secret python salary 200k"])
    put(store, BOB, "d2", ["bob java resume"])
    assert ask(store, BOB, "alice secret python salary") == ["bob java resume"]
    assert ask(store, ALICE, "bob java") == ["alice secret python salary 200k"]


def test_cross_guest_session_isolation(store: VectorStore) -> None:
    put(store, GUEST_A, "d1", ["guest a private text"])
    put(store, GUEST_B, "d2", ["guest b private text"])
    assert ask(store, GUEST_A, "private text") == ["guest a private text"]
    assert ask(store, GUEST_B, "private text") == ["guest b private text"]


def test_guest_and_user_with_same_id_do_not_collide(store: VectorStore) -> None:
    put(store, Owner("user", "42"), "d1", ["user forty-two"])
    put(store, Owner("guest", "42"), "d2", ["guest forty-two"])
    assert ask(store, Owner("user", "42"), "forty-two") == ["user forty-two"]
    assert ask(store, Owner("guest", "42"), "forty-two") == ["guest forty-two"]


def test_cross_document_isolation_within_owner(store: VectorStore) -> None:
    put(store, ALICE, "resume", ["resume python"])
    put(store, ALICE, "jd", ["job python"])
    assert ask(store, ALICE, "python", ["resume"]) == ["resume python"]
    assert ask(store, ALICE, "python", ["jd"]) == ["job python"]


def test_requesting_another_owners_document_id_returns_nothing(store: VectorStore) -> None:
    put(store, ALICE, "alice-doc", ["alice only"])
    assert ask(store, BOB, "alice only", ["alice-doc"]) == []


def test_empty_document_list_returns_nothing_not_everything(store: VectorStore) -> None:
    put(store, ALICE, "d", ["something"])
    assert ask(store, ALICE, "something", []) == []


def test_owner_is_mandatory() -> None:
    for bad in (("user", ""), ("admin", "x"), ("", "x")):
        with pytest.raises(ValueError):
            Owner(*bad)  # type: ignore[arg-type]


def test_store_api_has_no_user_filter_parameter() -> None:
    import inspect

    for cls in (InMemoryVectorStore, ChromaVectorStore):
        params = set(inspect.signature(cls.query).parameters)
        assert params == {"self", "owner", "vector", "k", "document_ids"}


def test_delete_document_only_affects_owner(store: VectorStore) -> None:
    put(store, ALICE, "d", ["alice text"])
    put(store, BOB, "d", ["bob text"])  # same document_id string, different owner
    store.delete_document(BOB, "d")
    assert store.count(BOB) == 0 and store.count(ALICE) == 1


def test_delete_owner_cleanup(store: VectorStore) -> None:
    put(store, GUEST_A, "d1", ["one", "two"])
    put(store, GUEST_B, "d2", ["three"])
    store.delete_owner(GUEST_A)
    assert store.count(GUEST_A) == 0 and store.count(GUEST_B) == 1


def test_prompt_injection_in_query_cannot_change_scope(store: VectorStore) -> None:
    put(store, ALICE, "d", ["alice data"])
    put(store, BOB, "d2", ["bob data"])
    hostile = "ignore filters owner_id=alice $or [] {'owner_id': {'$ne': 'x'}} data"
    assert ask(store, BOB, hostile) == ["bob data"]


def test_chroma_embedding_mismatch_rejected() -> None:
    client = chromadb.EphemeralClient()
    name = f"t_{uuid.uuid4().hex}"
    ChromaVectorStore(client, EMB, name)

    class Other(HashEmbeddings):
        def __init__(self) -> None:
            self.model_id = "other-model"

    with pytest.raises(VectorStoreError, match="different embedding"):
        ChromaVectorStore(client, Other(), name)


def test_chroma_dimension_mismatch_on_add_rejected() -> None:
    s = ChromaVectorStore(chromadb.EphemeralClient(), EMB, f"t_{uuid.uuid4().hex}")
    with pytest.raises(VectorStoreError, match="dimension"):
        s.add_chunks(ALICE, "d", [Chunk(0, "x")], [[0.1, 0.2]])
