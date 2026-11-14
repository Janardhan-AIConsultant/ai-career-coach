# Delivery report

Repository: `Janardhan-AIConsultant/ai-career-coach` (branch `master`). Every statement below says whether
it was **run** or only **written**. Nothing is claimed that was not executed.

## 1. Verification actually performed
| Check | Result |
|---|---|
| Backend tests (`python -m pytest --cov=app`) | **584 passed**, 97% coverage of about 6,200 statements (about 3 minutes) |
| `ruff check app tests` | clean |
| `mypy app` (strict) | no issues in 106 source files |
| Frontend unit tests (Vitest) | **24 passed** (run after the react-router 7 upgrade) |
| Frontend `npm run build` (tsc + Vite) | succeeds |
| End to end (Playwright, installed Edge, real backend, SQLite) | **6 passed** (run after the react-router 7 upgrade) |
| `npm audit --omit=dev` | 0 vulnerabilities |
| Alembic migrations 0001-0007 | upgrade verified on SQLite; PostgreSQL DDL rendered offline only |

**Not verified (no access or no account):** a live PostgreSQL/Neon run, live Groq calls, live GitHub API
calls, Chroma Cloud, a real S3-compatible bucket, and any Vercel/Render deployment. The Docker daemon was
unavailable here, so `docker compose` and the Dockerfile were **not built or run**. `pip-audit` is not
installed, so Python dependencies were not audited.

## 2. Phases
| # | Delivered |
|---|---|
| 1-2 | Analysis of the Streamlit prototype, migration plan, architecture, scaffold, configuration, logging |
| 3 | Guest sessions (capability token), file validation, extraction, quotas, cleanup |
| 4 | RAG: chunking, embeddings adapters, Chroma and in-memory stores, owner-scoped retrieval, prompt-injection guardrails |
| 5 | Authentication: Argon2id, JWT access tokens, rotating HttpOnly refresh cookie, account deletion, guest import |
| 6 | Career intelligence: resume/JD analysis, transparent match, skill gaps, resume optimisation, reports (PDF/DOCX) |
| 7 | Interview preparation and mock interviews; AI Career Coach with streaming endpoint |
| 8 | Learning roadmaps (7/15/60 days) and assessment engine |
| 9-10 | GitHub project review (static), certificates with QR and public verification, admin revocation |
| 11 | Career achievement portfolio (consent-gated, evidence levels, LinkedIn text, resume section) |
| 12 | Ratings, testimonials, moderation, LinkedIn/WhatsApp/Facebook share links, PNG cards, consent withdrawal, aggregate analytics |
| 13 | Admin dashboard API |
| 14 | Cross-cutting security tests, React frontend, Vitest, Playwright E2E |
| 15 | Render/Vercel/Docker configuration, S3-compatible storage backend, react-router 7, deployment guide, README, this report |

## 3. Requirement compliance (hard rules)
| Rule | Status |
|---|---|
| Roadmaps only 7, 15, 60 days | DB CHECK, API validation, UI offers exactly three; repo scan test fails on other lengths |
| Sharing only LinkedIn, WhatsApp, Facebook | DB CHECK, API, UI; repo scan test; E2E asserts exactly three links |
| No testimonial published without consent | consent defaults to false, moderation required, withdrawal immediate (tests + E2E) |
| Never claim a post was published | share links open each platform's dialog only; UI states the platform never posts |
| No fabricated experience/skills/testimonials | optimiser never adds unstated skills; portfolio derived from verified records; no endpoint to add items |
| No secrets committed | `.env.example` placeholders only; repo scan test; Render values are `sync: false` |
| Uploaded content is untrusted; nothing sensitive logged | injection flags, delimited context, log-hygiene test |
| No paid service introduced silently | none enabled; costs listed in `docs/deployment.md` for your decision |

## 4. Directory tree (tracked files)
```text
AIPoweredCareerCoach/
├── backend/
│   ├── alembic/
│   │   ├── versions/  (7 files)
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── admin.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── certificates.py
│   │   │   │   ├── coach.py
│   │   │   │   ├── feedback.py
│   │   │   │   ├── guest.py
│   │   │   │   ├── health.py
│   │   │   │   ├── interview.py
│   │   │   │   ├── learning.py
│   │   │   │   ├── portfolio.py
│   │   │   │   ├── projects.py
│   │   │   │   ├── users.py
│   │   │   │   └── workspace.py
│   │   │   ├── __init__.py
│   │   │   └── dependencies.py
│   │   ├── assessments/
│   │   │   ├── __init__.py
│   │   │   ├── bank.py
│   │   │   └── scoring.py
│   │   ├── career/
│   │   │   ├── __init__.py
│   │   │   ├── jd_analysis.py
│   │   │   ├── matching.py
│   │   │   ├── optimization.py
│   │   │   ├── resume_analysis.py
│   │   │   ├── skill_gap.py
│   │   │   ├── taxonomy.py
│   │   │   └── text_utils.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── constants.py
│   │   │   ├── database.py
│   │   │   ├── exceptions.py
│   │   │   ├── logging_config.py
│   │   │   └── security.py
│   │   ├── guardrails/
│   │   │   ├── __init__.py
│   │   │   ├── file_validation.py
│   │   │   └── prompt_safety.py
│   │   ├── interview/
│   │   │   ├── __init__.py
│   │   │   ├── bank.py
│   │   │   ├── evaluation.py
│   │   │   └── selection.py
│   │   ├── learning/
│   │   │   ├── __init__.py
│   │   │   └── curriculum.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── accounts.py
│   │   │   ├── achievements.py
│   │   │   ├── base.py
│   │   │   ├── documents.py
│   │   │   ├── feedback.py
│   │   │   ├── interview.py
│   │   │   └── learning.py
│   │   ├── processors/
│   │   │   ├── __init__.py
│   │   │   └── extraction.py
│   │   ├── projects/
│   │   │   ├── __init__.py
│   │   │   ├── catalog.py
│   │   │   ├── evaluation.py
│   │   │   └── github.py
│   │   ├── rag/
│   │   │   ├── __init__.py
│   │   │   ├── chunking.py
│   │   │   ├── embeddings.py
│   │   │   ├── retrieval.py
│   │   │   └── vector_store.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── admin.py
│   │   │   ├── auth.py
│   │   │   ├── career.py
│   │   │   ├── career_api.py
│   │   │   ├── certificates.py
│   │   │   ├── coach.py
│   │   │   ├── feedback.py
│   │   │   ├── guest.py
│   │   │   ├── interview.py
│   │   │   ├── learning.py
│   │   │   ├── portfolio.py
│   │   │   └── projects.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── account_service.py
│   │   │   ├── admin_service.py
│   │   │   ├── assessment_service.py
│   │   │   ├── auth_service.py
│   │   │   ├── career_service.py
│   │   │   ├── certificate_pdf.py
│   │   │   ├── certificate_service.py
│   │   │   ├── coach_service.py
│   │   │   ├── document_intake.py
│   │   │   ├── feedback_service.py
│   │   │   ├── guest_service.py
│   │   │   ├── interview_service.py
│   │   │   ├── learning_service.py
│   │   │   ├── llm.py
│   │   │   ├── object_storage.py
│   │   │   ├── portfolio_service.py
│   │   │   ├── principal.py
│   │   │   ├── project_service.py
│   │   │   ├── rag_service.py
│   │   │   ├── report_builders.py
│   │   │   ├── report_render.py
│   │   │   ├── report_service.py
│   │   │   └── testimonial_card.py
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── rate_limit.py
│   │   │   └── retry.py
│   │   ├── workflows/
│   │   │   ├── __init__.py
│   │   │   └── career_graph.py
│   │   ├── __init__.py
│   │   └── main.py
│   ├── tests/  (42 files)
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── requirements-dev.txt
│   ├── requirements-local-embeddings.txt
│   └── requirements.txt
├── data/
│   ├── sample_job_description.txt
│   └── sample_resume.txt
├── docs/
│   ├── admin_dashboard.md
│   ├── architecture.md
│   ├── authentication.md
│   ├── career_intelligence.md
│   ├── certificates_and_projects.md
│   ├── database_design.md
│   ├── deployment.md
│   ├── existing_project_analysis.md
│   ├── feedback_and_testimonials.md
│   ├── guest_access.md
│   ├── interview_and_coach.md
│   ├── learning_and_assessments.md
│   ├── migration_plan.md
│   ├── portfolio.md
│   ├── rag_pipeline.md
│   └── testing.md
├── frontend/
│   ├── e2e/  (2 files)
│   ├── src/  (25 files)
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── playwright.config.ts
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── vercel.json
│   └── vite.config.ts
├── scripts/
│   ├── cleanup_guest_data.py
│   ├── create_admin.py
│   └── seed_data.py
├── .env.example
├── .gitignore
├── README.md
├── docker-compose.yml
├── render.yaml
└── tree.txt
```

## 5. Known limitations and open items
1. **No live end-to-end on the target stack.** Neon/PostgreSQL, Groq, GitHub, Chroma Cloud and S3 paths are
   covered by unit tests with fakes or by offline checks only. Run the first deploy carefully and read logs.
2. **Embeddings in production need a decision.** Render Free cannot host the local model; `hash` is
   lexical-only. See `docs/deployment.md`.
3. **Object storage:** the S3-compatible backend exists and is unit-tested with a fake client; it has not
   touched a real bucket. Local storage loses files on Render restarts.
4. **Docker artefacts untested here** (no Docker daemon). The Dockerfile runs migrations on start, which is
   safe for one instance only.
5. **Heuristic features:** interview answer feedback and project review are heuristic/static (code is never
   executed); there is no OCR for scanned PDFs; match scores are estimates, not hiring decisions.
6. **Frontend coverage:** all main flows have screens, but only six browser journeys are automated.
   Assessments, certificate issuing, the coach, roadmap activity completion and the portfolio screens have no
   browser test. The coach UI uses the non-streaming endpoint. No accessibility audit, visual regression or
   load test was done.
7. **Rate limiting is in-process**, so it protects a single instance; behind multiple instances use a shared
   store (e.g. Redis).
8. **Guest-session cleanup** needs an external scheduler (none on Render Free).
9. **Certificates** are platform-issued and not externally accredited; the UI and PDFs say so.
10. **Rotate any credential that was ever pasted into a chat or file** before going live.

## 6. Cost summary (nothing enabled by me)
Vercel, Render, Neon, Chroma Cloud and Groq each offer a free or trial tier today, with limits that change and
that I could not verify from here. An S3-compatible bucket and a larger Render instance (for local
embeddings) are the likely paid items. Decide before enabling, and set budget alerts.
