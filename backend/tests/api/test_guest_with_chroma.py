"""End-to-end guest flow against a real (ephemeral) Chroma store instead of the in-memory fake."""

import uuid

import chromadb

from app.api.dependencies import get_rag_service, get_vector_store
from app.rag.embeddings import HashEmbeddings
from app.rag.vector_store import ChromaVectorStore, Owner
from app.services.rag_service import RagService
from tests.guest_fixtures import JD, RESUME, build_env


def test_upload_isolation_and_purge_on_real_chroma() -> None:
    env = next(build_env())
    emb = HashEmbeddings()
    chroma = ChromaVectorStore(chromadb.EphemeralClient(), emb, f"t_{uuid.uuid4().hex}")
    rag = RagService(env.settings, emb, chroma, None)
    env.client.app.dependency_overrides[get_vector_store] = lambda: chroma  # type: ignore[attr-defined]
    env.client.app.dependency_overrides[get_rag_service] = lambda: rag  # type: ignore[attr-defined]

    a, a_body = env.new_guest()
    b, b_body = env.new_guest()
    env.upload_text(a, "resume", RESUME)
    env.upload_text(b, "job_description", JD)
    oa, ob = Owner("guest", a_body["session_id"]), Owner("guest", b_body["session_id"])
    assert chroma.count(oa) >= 1 and chroma.count(ob) >= 1
    hits = chroma.query(oa, emb.embed_query("python fastapi"), 10)
    assert hits and all(JD[:20] not in h.text for h in hits)

    assert env.client.delete(f"/api/v1/guest/sessions/{a_body['session_id']}", headers=a).status_code == 204
    assert chroma.count(oa) == 0 and chroma.count(ob) >= 1
