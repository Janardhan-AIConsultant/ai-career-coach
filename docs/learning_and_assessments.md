# Learning Roadmaps and Assessments (Phase 9)

Registered users only. Everything is scoped to the owning user (foreign ids return 404).

## Roadmaps (`/api/v1/learning`)
The platform supports **three** roadmap lengths: **7, 15 and 60 days**. This is enforced three times: the request model accepts only those values (OpenAPI shows `enum: [7, 15, 60]`), `validate_duration` checks again in the service, and the database has a CHECK constraint. A test scans the OpenAPI document, README, docs and source for any other roadmap length.

| Endpoint | Purpose |
|---|---|
| `POST /learning/roadmaps` | Generate a roadmap: `duration_days`, `goal`, and optionally `focus_skills` or a resume + job description pair (skill gaps drive the plan) |
| `GET /learning/roadmaps`, `GET /learning/roadmaps/{id}`, `DELETE ...` | List / open / delete |
| `POST .../start` | Start the roadmap (idempotent) |
| `POST .../activities/{id}/complete`, `.../reopen` | Mark activities (not assessment activities) |
| `GET /learning/dashboard` | Roadmap progress, next activities, recent assessment attempts |
| `POST .../report` | PDF or DOCX of the plan |

**Focus selection:** explicit `focus_skills` > gaps from a resume/JD pair (most severe first) > skills mentioned in the goal. If none is found the request is rejected. Plans use at most 3 (7-day), 5 (15-day) or 10 (60-day) focus items.
**Structure:** one module per focus item; each day has learning and/or practice tasks; each module ends with an assessment (when an authored one exists) or a review; 15- and 60-day plans end with a capstone project (2 and 7 days). Every roadmap lists learning objectives, topics, daily tasks, practical exercises, generic resources (no invented URLs), assessment activities, estimated hours and completion criteria.
**Completion:** at least 80% of required activities AND every assessment in the plan passed. Assessment activities complete only when the user passes the assessment, so a roadmap cannot be finished by clicking. (Phase 10 certificates will additionally require server-verified evidence.)

## Assessments (`/api/v1/assessments`)
`GET /assessments`, `GET /assessments/{slug}` (questions only, **no answer key**), `POST /assessments/{slug}/attempts`, `GET /assessments/attempts[?slug=]`, `GET /assessments/attempts/{id}`.

- **Bank:** 6 authored assessments x 6 questions (Python, Kafka, PostgreSQL, RAG/GenAI, architecture, engineering leadership) covering multiple-choice, multiple-select, scenario and technical (free-text) questions, with difficulty, topic, explanations and a 70% pass mark. Seeded idempotently by slug (`scripts/seed_data.py` or lazily on first use).
- **Scoring is server-side only.** The client sends raw answers; any `score`/`passed` it adds is ignored. MCQ: exact; multi-select: correct minus wrong over total correct; scenario: author-assigned partial credit; technical/practical: keyword-rubric coverage with a minimum length. Malformed answers score 0 and never crash scoring.
- **After submission** the response reveals the correct answer and explanation per question. To limit memorising, attempts are capped at 5 per assessment per 24 hours.
- Passing marks matching activities complete in the user's in-progress roadmaps.

## Limitations
- Free-text scoring is a transparent keyword rubric, not human or LLM review (the feedback says so).
- "Practical" and "project-based" assessment: the engine supports rubric-scored practical questions, but real project evaluation (repository + documentation evidence) is built in Phase 10 with project submissions.
- No time limits per attempt; question and option order are fixed.
- Plans are generated deterministically from reusable content: topic outlines are generic per technology group, not course-specific. LangGraph is not used for roadmap generation (a deterministic planner is simpler and testable).
- Roadmap pacing is not enforced (a learner may finish early), but completion still requires passing the assessments.
