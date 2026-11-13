# Migration Plan

## Strategy
Strangler-style rewrite: the old Streamlit app is **not** extended. Reusable logic is ported into the new FastAPI backend layers; the Streamlit UI is replaced by React. The original ZIP stays untouched as a reference.

## Mapping old -> new

| Existing | New location | Action |
|---|---|---|
| `src/file_utils.py` | `backend/app/processors/` (`pdf.py`, `docx.py`, `text.py`) + `guardrails/file_validation.py` | Rewrite: PyMuPDF, python-docx, strict validation, no temp-file leaks |
| `rag_engine.split_documents` | `backend/app/rag/chunking.py` | Port; chunk size/overlap from settings, overlap < size validated |
| `rag_engine.get_embeddings` | `backend/app/rag/embeddings.py` | Port as provider adapter (`local-hf` default for dev; remote provider for cloud) |
| `rag_engine.build_vectorstore` | `backend/app/rag/vector_store.py` | Rewrite: abstraction, per-tenant metadata, no directory deletion |
| `rag_engine.retrieve_context` | `backend/app/rag/retrieval.py` | Port with enforced server-side filter |
| `rag_engine.run_career_coach` prompt | `backend/app/services/prompts/` | Port as versioned templates, injection-safe delimiters |
| `generate_complete_report` | `services/career_service` + `reports` | Replace LLM "ATS score" with deterministic scoring |
| `app.py` | `frontend/` React pages | Replace |
| `data/sample_*.txt` | `data/` | Copy unchanged |
| `career_coach_chroma_db/` | - | Not migrated (18 demo vectors, no tenant metadata); `scripts/migrate_chroma.py` only if the user wants it - it would re-embed with ownership metadata |
| `.env` | - | Dropped; `.env.example` placeholders only |
| `requirements.txt` | `backend/requirements.txt`, `pyproject.toml` | Re-pin after `pip check` |

## Data migration
- No application database exists, so there is no relational data to migrate.
- Chroma: collection `career_coach_rag` (384-d) -> new collection(s) whose metadata records `embedding_model` and `dimension`. Default local embedding stays MiniLM-384 so local data is compatible; switching provider requires a new collection + re-embedding (guarded by a startup dimension check).

## Secrets
No real key was found in the ZIP (`.env` holds an empty value). Any key ever used with the old project should be rotated if there is any chance it was shared.

## Phases (as in the master prompt) and exit criteria
Each phase ends with: summary, files changed, tests actually run with real output, outstanding issues, updated checklist.

1. Assessment (this phase) - docs only. **Exit:** three docs written.
2. Architecture/setup - repo skeleton, settings, logging, Docker Compose; `pytest` + `ruff` green.
3. Core infra - SQLAlchemy models, Alembic, exceptions, security, health.
4. Document processing + RAG - port of old pipeline with guardrails and isolation tests.
5-13. Features in the prompt's order (guest, auth, career intelligence, interview/coach, learning/assessments, certificates/projects, portfolio, testimonials + sharing, admin).
14. Hardening - full test suites, coverage report.
15. Deployment docs/config.

## Risks and decisions needing the user's input
1. **Scale:** the full prompt is a multi-week product. Plan is to deliver phase by phase with verified tests; a single run will not finish it.
2. **PyMuPDF licence** (AGPL) vs commercial SaaS intent - default to PyMuPDF as specified; revisit before monetising.
3. **Free-tier embeddings:** default dev = local MiniLM; cloud provider choice (e.g., a remote embeddings API) may carry limits/cost - will be confirmed before use.
4. **Object storage** free option for persistent files is unselected; MVP uses bounded temp processing + an abstraction.
5. **Local toolchain:** Python 3.11.9 present; Node/Docker availability to be verified at the start of Phase 2.
