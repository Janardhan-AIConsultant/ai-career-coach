# Target Architecture

## Overview
Two independent applications:

```
React + TS (Vite) --REST /api/v1, SSE--> FastAPI --> PostgreSQL (app data)
                                              |--> ChromaDB (vectors, via VectorStore abstraction)
                                              |--> Groq (LLM)
                                              |--> Embedding provider (configurable)
                                              |--> Object storage (abstraction)
```

React never talks to PostgreSQL, ChromaDB, or Groq; all logic, security and AI processing live in the backend.

## Backend layering (`backend/app/`)
- `api/routes/*` - thin HTTP layer, Pydantic request/response models, dependency-injected services.
- `services/` - business logic (career analysis, scoring, learning, certificates, portfolio, testimonials).
- `repositories/` - SQLAlchemy 2.x data access; every query is ownership-scoped.
- `rag/` - chunking, embeddings adapter, `VectorStore` interface (Chroma local/cloud), retrieval with **server-built filters only**.
- `processors/` - PDF (PyMuPDF), DOCX (python-docx), TXT extraction.
- `guardrails/` - file validation, prompt-injection detection, output validation.
- `workflows/` - LangGraph graphs only for career analysis, resume optimisation, interview prep, roadmap generation, project evaluation; simple chains elsewhere.
- `core/` - settings (`lru_cache`d `get_settings`), logging (JSON, correlation IDs), exceptions, security, DB session.

## Key decisions
1. **Deterministic scoring:** match/overall scores computed in code from LLM-extracted, evidence-grounded facts (continuing the principle that scores are not trusted from the model). Labelled as an estimate, not an ATS score.
2. **Isolation:** every vector record carries `owner_type`, `owner_id`, `document_id`; the retrieval layer builds the filter from the authenticated principal. Client-supplied filters are never accepted. Security tests cover cross-user, cross-session, cross-document.
3. **Guest access:** `POST /guest/sessions` issues a signed, expiring capability token (random 256-bit ID + HMAC/JWT); sent in a header, never in URLs or logs. Quotas, rate limits, and a cleanup job remove expired files/vectors.
4. **Persistence on free tier:** nothing durable on Render's ephemeral disk - PostgreSQL (Neon), Chroma Cloud, object storage abstraction.
5. **Constrained enumerations:** roadmap durations `{7, 15, 60}` and share platforms `{linkedin, whatsapp, facebook}` enforced by Pydantic enums *and* DB CHECK constraints; no other values appear in code, docs, or UI.
6. **Embeddings:** provider adapter; collection metadata stores model + dimension and startup verifies a match.
7. **Errors/logging:** custom exception hierarchy mapped to sanitised JSON errors; no resume text, passwords or keys in logs; retries with backoff only for transient failures.

## Frontend (`frontend/src/`)
React 18 + TypeScript + Vite + Tailwind + shadcn/ui; React Router (public guest routes, protected user/admin routes), TanStack Query for server state, Zustand for UI/auth state, React Hook Form + Zod for forms. Only `VITE_API_BASE_URL` is exposed.

## Local and deployment
- Docker Compose: frontend, backend, PostgreSQL, Chroma (named volumes).
- Prod: Vercel (frontend), Render Free (backend, sleeps when idle), Neon (Postgres), Chroma Cloud (subject to allowance), Groq. Free allowances are provider-controlled and will be documented with the date checked; no zero-cost guarantee is promised.

## Planned repository layout
Follows section 31 of the master prompt; files are created only when they contain real implementation.
