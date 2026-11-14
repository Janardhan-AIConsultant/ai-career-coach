# RAG Pipeline (Phase 4)

`services/rag_service.py` orchestrates the stages; all dependencies are injected.

## Ingestion
1. **Validate** (`guardrails/file_validation.py`): extension allowlist (pdf/docx/txt), declared MIME vs extension, magic bytes, size cap, UTF-8/NUL check for text, DOCX ZIP checks (entry count, expansion ratio and size, zip-slip paths, required `word/document.xml`). Filenames are sanitised for display only; storage keys are server-generated.
2. **Extract** (`processors/extraction.py`): PDF via PyMuPDF (page cap, encrypted rejected), DOCX via python-docx (paragraphs + tables), TXT. In memory only, no temp files.
3. **Clean**: NFC normalisation, control-char removal, whitespace collapse, length cap.
4. **Scan**: instruction-like content is flagged and logged (`prompt_safety.scan_for_injection`); text is still stored as data.
5. **Chunk** (`rag/chunking.py`): `RecursiveCharacterTextSplitter`, `CHUNK_SIZE` / `CHUNK_OVERLAP`.
6. **Embed** (`rag/embeddings.py`): provider adapter (see below), retried on transient failure.
7. **Store** (`rag/vector_store.py`): Chroma (cloud / HTTP server / local persistent) behind a `VectorStore` protocol.

## Answering
Retrieve (server-built owner filter) -> `build_context` (delimited `<document_excerpt id="S1">` blocks, forgery neutralised, character budget) -> system prompt (excerpts are untrusted data) -> LLM (Groq: timeout, bounded `max_tokens`, backoff retry) -> `validate_output` (non-empty, no system-prompt canary, citations must reference supplied sources) -> sources returned with document id, chunk index and excerpt. If nothing relevant is retrieved the LLM is not called.

## Isolation
Every chunk has `owner_type` (`guest`|`user`), `owner_id`, `document_id`. `Owner` is built from the authenticated principal; the store builds the filter itself and exposes no filter parameter. Document-scoped queries are AND-ed with the owner; an empty document list returns nothing. Tested against both the in-memory and real Chroma implementations.

## Embeddings
| Provider | Notes |
|---|---|
| `local-hf` (default) | MiniLM 384-d via `langchain-huggingface`. Optional heavy install: `pip install -r requirements-local-embeddings.txt` (PyTorch). Not intended for 512 MB free hosts. **Not exercised in this environment's tests.** |
| `hash` | Deterministic lexical 384-d feature hashing. Dev/test only, not semantic. |
A remote embedding provider for the free tier is still to be chosen (any paid/limited service needs your approval first). Chroma collections record `embedding_model` and `dimension`; opening a collection with a different model/dimension raises `VectorStoreError`.

## Known limitations
- No OCR: scanned PDFs are rejected with a clear message.
- Injection detection is heuristic; the delimiting, system prompt and output validation are the real defences, and none is a guarantee.
- Hybrid retrieval/reranking is not implemented (optional in the spec).
- Chroma Cloud and HTTP-server paths are written but untested here (no credentials/Docker); local Chroma (ephemeral and persistent) is tested.
- Groq calls are tested with the network call replaced; no live Groq request was made.
