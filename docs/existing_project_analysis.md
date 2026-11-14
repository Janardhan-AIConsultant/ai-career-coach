# Existing Project Analysis

Source: `Project-ai_career_coach_rag.zip` (extracted to an isolated directory and read in full; nothing was executed from it).
Analysis date: 2026-11-13.

## 1. Inventory

| Path | Size | Purpose |
|---|---|---|
| `app.py` | 5.8 KB | Streamlit UI: upload/paste resume + JD, build index, ask questions, generate report |
| `src/rag_engine.py` | 4.4 KB | LangChain RAG: documents, splitter, HF embeddings, Chroma, Groq chain |
| `src/file_utils.py` | 0.9 KB | Text extraction for TXT/PDF/DOCX from Streamlit uploads |
| `src/__init__.py` | 0 | Package marker |
| `requirements.txt` | 14 deps | Pinned LangChain 0.3.x stack, chromadb 0.5.23, streamlit 1.41.1 |
| `data/sample_resume.txt`, `data/sample_job_description.txt` | small | Sample inputs (reusable as-is) |
| `career_coach_chroma_db/` | ~570 KB | Persisted local Chroma DB (committed in ZIP) |
| `.env` | 14 B | Contains only `GROQ_API_KEY=` with an empty value (no secret found) |
| `README.md` | 1.8 KB | Teaching-oriented setup guide |

There are only 3 Python files, ~230 lines total. No tests, no logging, no config module, no auth, no database other than Chroma.

## 2. Streamlit application (`app.py`)
- Sidebar sliders for chunk size (300-1500) and overlap (0-400); no check that overlap < size.
- Flow: read resume/JD -> `create_documents` -> `split_documents` -> `build_vectorstore` -> store in `st.session_state` -> quick/custom question -> `run_career_coach` -> render answer + retrieved chunks. "Complete Career Report" button calls the same chain with a fixed question.
- Rendering uses `st.write` of LLM output (safe); static CSS uses `unsafe_allow_html` only on constant strings (safe).
- Everything is synchronous and runs in the UI process, so UI, business logic and AI logic are coupled.

## 3. LangChain RAG (`src/rag_engine.py`)
- Pipeline: `Document` -> `RecursiveCharacterTextSplitter` (separators `\n\n`, `\n`, `.`, ` `, `""`) -> `HuggingFaceEmbeddings(all-MiniLM-L6-v2)` -> `Chroma.from_documents` -> `as_retriever(k=6)` -> `ChatPromptTemplate | ChatGroq | StrOutputParser`.
- Model: `llama-3.1-8b-instant`, temperature 0.2, hard-coded.
- Prompt: "Use ONLY the given context... do not invent" - good intent, but no delimiting of untrusted text.
- `resume_text`/`jd_text` are passed into `run_career_coach` but unused (only retrieved chunks reach the prompt).

## 4. ChromaDB inspection (read-only SQLite query)
- One collection: `career_coach_rag`, **embedding dimension 384** (matches all-MiniLM-L6-v2).
- 18 embeddings. Metadata keys: only `source` and `doc_type` (+ `chroma:document`). No user/session/document ID, no timestamps, no embedding-model/version tag.
- Stored under a single shared directory; `build_vectorstore` **deletes the entire directory** on every build (`shutil.rmtree`), so concurrent users overwrite each other.
- Migration implication: the new vector store must keep dimension 384 *or* re-embed; collection metadata must record `embedding_model` + `dimension`. The existing 18 vectors are sample data from a demo and need not be preserved; sample inputs in `data/` are preserved.

## 5. PDF / DOCX / TXT processing (`file_utils.py`)
- PDF via `pypdf` (target stack requires PyMuPDF); DOCX via `docx2txt` (target requires python-docx); TXT via lenient UTF-8 decode.
- No OCR; scanned PDFs silently return empty text.

## 6. Reusable functionality
- Chunk/overlap parameters and `RecursiveCharacterTextSplitter` usage.
- Prompt intent ("use only context, don't invent") and section structure (match, strengths, gaps, improvements, projects, interview tips) - reuse as seeds for versioned prompt templates.
- Retrieval -> context -> prompt -> parser chain shape (LCEL).
- Embedding model choice (384-d MiniLM) as the *local-dev* embedding provider.
- Sample resume and JD files.

## 7. Bugs, security issues, architectural limits

| # | Severity | Finding | Fix in new design |
|---|---|---|---|
| 1 | High | **Temp-file leak:** `NamedTemporaryFile(delete=False)` is never removed -> uploaded resumes persist on disk (privacy) | Process from bytes/bounded temp dir with guaranteed cleanup |
| 2 | High | **No file validation:** only the extension is checked (by Streamlit); no size cap, MIME/signature check, zip-bomb protection for DOCX | `guardrails/file_validation` (ext + MIME + magic bytes + size + decompressed-size cap) |
| 3 | High | **Shared global vector store:** single directory/collection; every user's data wiped/mixed; no isolation | Per-session/user metadata filters enforced in backend |
| 4 | High | **Prompt injection:** resume/JD text goes straight into the prompt with no delimiting or detection | Delimited untrusted-data blocks, injection detector, output validation |
| 5 | Medium | `.env` shipped inside the ZIP (empty here, but the pattern risks leaking keys) | `.env` git-ignored; `.env.example` placeholders only. **If any real Groq key was ever placed in a copy of this project, rotate it.** |
| 6 | Medium | `get_llm` checks the key but doesn't pass it to `ChatGroq`; no timeout/retry/token limit | Settings-driven client with timeout, retry/backoff, `max_tokens` |
| 7 | Medium | Real bug: `read_uploaded_file` for `.txt` uses `errors="ignore"`, silently dropping bytes; PDF/DOCX failures raise raw exceptions to the UI | Typed exceptions, sanitized errors |
| 8 | Medium | `chunk_overlap` can exceed `chunk_size` via sliders -> splitter error | Validated settings |
| 9 | Medium | Embedding model loaded in-process (~90 MB + torch); unsuitable for a free-tier 512 MB backend | Configurable provider; remote/lightweight option in cloud |
| 10 | Low | Unused `resume_text`/`jd_text` params, unused `load_text_file`, unused `Optional` import | Removed in rewrite |
| 11 | Low | No logging, tests, type-checking, structured errors | Added in Phase 2+ |
| 12 | Low | "ATS-style score" is whatever the LLM says (non-deterministic, unexplained) | Transparent, configurable deterministic scoring, labelled as an estimate |

Architectural limits: monolithic Streamlit app, no API, no persistence/auth/users, only a single RAG Q&A feature, no isolation, no tests.

## 8. Dependency compatibility
- Existing pins are a coherent but dated set (LangChain 0.3.14, chromadb 0.5.23, streamlit 1.41.1). `pandas` is unpinned.
- `sentence-transformers` pulls PyTorch; heavy for Render Free.
- chromadb 0.5.x client vs Chroma Cloud: the new `CloudClient` requires a newer chromadb (1.x) - the plan is to re-pin to current compatible versions and verify with `pip check` in Phase 2 rather than assume. The vector store will sit behind an abstraction so a version bump is localised.
- Local environment observed: **Python 3.11.9** (within the required 3.11+). Dependency installs/resolution will be tested in Phase 2; no compatibility claim is made yet.
- `docx2txt` and `pypdf` will be replaced by `python-docx` and `PyMuPDF` per the target stack (PyMuPDF is AGPL/commercial-licensed - flagged for review before commercial SaaS use; `pypdf` is the permissive fallback).

## 9. Conclusion
The ZIP is a small teaching prototype. The RAG skeleton and prompts are worth carrying forward; the app shell, file handling, vector store lifecycle and security posture need replacement. See `migration_plan.md` and `architecture.md`.
