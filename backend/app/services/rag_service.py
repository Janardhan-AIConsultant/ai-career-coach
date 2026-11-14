"""RAG orchestration: ingestion (validate -> extract -> clean -> chunk -> embed -> store) and
grounded answering (retrieve -> context -> prompt -> LLM -> validate -> sources).

Dependencies are injected (settings, embeddings, vector store, LLM) so it is fully testable.
Privacy: document text and questions are never logged; only counts/ids/flags are.
Errors: propagates the typed ``AppError`` subclasses from each stage.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.core.config import Settings
from app.core.exceptions import (
    EmbeddingGenerationError,
    InputValidationError,
    LLMServiceError,
)
from app.guardrails.file_validation import validate_upload
from app.guardrails.prompt_safety import (
    SYSTEM_PROMPT,
    build_context,
    scan_for_injection,
    validate_output,
)
from app.processors.extraction import extract_text, finalize_text
from app.rag.chunking import chunk_text
from app.rag.embeddings import Embeddings
from app.rag.retrieval import retrieve
from app.rag.vector_store import Owner, VectorStore
from app.services.llm import LLMClient
from app.utils.retry import retry_call

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 2000
NO_EVIDENCE = "I could not find relevant information in your documents to answer that."


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    chunk_count: int
    text: str
    injection_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    document_id: str
    chunk_index: int
    excerpt: str


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    sources: list[SourceRef] = field(default_factory=list)


class RagService:
    def __init__(
        self, settings: Settings, embeddings: Embeddings, store: VectorStore, llm: LLMClient | None
    ) -> None:
        self._s = settings
        self._emb = embeddings
        self._store = store
        self._llm = llm

    # ---- ingestion
    def ingest_file(
        self, owner: Owner, document_id: str, data: bytes, filename: str, content_type: str | None
    ) -> IngestResult:
        file = validate_upload(data, filename, content_type, self._s.max_upload_bytes)
        text = extract_text(
            file, max_chars=self._s.max_document_chars, max_pdf_pages=self._s.max_pdf_pages
        )
        return self._index(owner, document_id, text)

    def ingest_text(self, owner: Owner, document_id: str, raw_text: str) -> IngestResult:
        if not raw_text or not raw_text.strip():
            raise InputValidationError("Text input is empty")
        return self._index(owner, document_id, finalize_text(raw_text, max_chars=self._s.max_document_chars))

    def _index(self, owner: Owner, document_id: str, text: str) -> IngestResult:
        scan = scan_for_injection(text)
        if scan.flagged:
            logger.warning("instruction-like content in document",
                           extra={"document_id": document_id, "patterns": list(scan.patterns)})
        chunks = chunk_text(text, self._s.chunk_size, self._s.chunk_overlap)
        vectors = retry_call(
            lambda: self._emb.embed_documents([c.text for c in chunks]),
            retries=self._s.llm_max_retries,
        )
        if len(vectors) != len(chunks):
            raise EmbeddingGenerationError("Embedding count mismatch")
        stored = retry_call(
            lambda: self._store.add_chunks(owner, document_id, chunks, vectors),
            retries=self._s.llm_max_retries,
        )
        logger.info("document indexed", extra={"document_id": document_id, "chunks": stored})
        return IngestResult(document_id, stored, text, scan.patterns)

    # ---- answering
    def answer(
        self, owner: Owner, question: str, document_ids: Sequence[str] | None = None
    ) -> AnswerResult:
        question = (question or "").strip()
        if not question or len(question) > MAX_QUESTION_CHARS:
            raise InputValidationError(f"Question must be 1-{MAX_QUESTION_CHARS} characters")
        chunks = retrieve(
            self._store, self._emb, owner, question,
            top_k=self._s.retrieval_top_k, document_ids=document_ids,
        )
        context = build_context(chunks, self._s.max_context_chars)
        if not context.source_ids:
            return AnswerResult(NO_EVIDENCE, [])
        if self._llm is None:

            raise LLMServiceError("The AI service is not configured")
        user_prompt = f"EXCERPTS:\n{context.text}\n\nQUESTION:\n{question}"
        raw = self._llm.invoke(SYSTEM_PROMPT, user_prompt)
        answer = validate_output(raw, set(context.source_ids))
        refs = [
            SourceRef(sid, c.document_id, c.chunk_index, c.text[:300])
            for sid, c in context.source_ids.items()
        ]
        return AnswerResult(answer, refs)
