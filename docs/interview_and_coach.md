# Interview Preparation and AI Career Coach (Phase 8)

Both are for **registered users** (bearer token); guests are limited to the five career services.

## Interview preparation (`/api/v1/interview`)
| Endpoint | Purpose |
|---|---|
| `GET /topics` | Supported interview kinds and technical topics |
| `POST /prepare` | Personalised question set (kinds, optional resume/JD ids, topics, count, `report_format`) with model answers, key points, practical examples, follow-ups, evaluation criteria and a reason for each question |
| `POST /mock` | Start a mock interview (questions only; model answers stay hidden) |
| `POST /mock/{id}/answers` | Submit one answer, receive per-dimension feedback and the model answer |
| `POST /mock/{id}/complete` | Overall score, dimension averages, weakest areas, recommendations |
| `GET /mock`, `GET /mock/{id}` | History / session state |

- **Kinds:** technical, engineering_leadership, engineering_management, architecture, system_design, behavioural, scenario, hr.
- **Question bank** (`app/interview/bank.py`, 56 authored questions): Java 17/21, Spring Boot, React, TypeScript, Python, FastAPI, AWS, Kafka, PostgreSQL, microservices, distributed systems, generative AI, RAG, LangChain, LangGraph, ChromaDB, prompt engineering, system design, solution architecture, engineering management/leadership, plus behavioural (STAR), scenario and HR questions. A test checks that every reference answer satisfies its own key points, which guards the keyword lists.
- **Personalisation** (deterministic): required job skills missing from the resume come first ("practise this"), then required-and-evidenced ("expect depth questions"), then preferred and resume skills; leadership questions rise when the JD expects leadership.
- **Feedback dimensions:** technical accuracy (key-point coverage; STAR coverage for behavioural), communication, clarity, problem solving, structured thinking, and leadership/ownership (only for leadership, management, behavioural and scenario questions). All are transparent heuristics over the text and are labelled as such: they are **not** an LLM or human assessment. Very short answers are capped; keyword dumps score poorly on structure and clarity.

## AI Career Coach (`/api/v1/coach`)
| Endpoint | Purpose |
|---|---|
| `POST/GET /conversations`, `DELETE /conversations/{id}` | Persisted conversations (per user) |
| `GET /conversations/{id}/messages` | History (paginated) |
| `POST /conversations/{id}/messages` | One-shot reply |
| `POST /conversations/{id}/messages/stream` | Server-Sent Events: `meta`, `token`*, then `done` (final content + sources) or `error` |

- **Needs `GROQ_API_KEY`.** Without it the coach returns 503 `not_configured` and stores nothing; it never fakes answers.
- **Grounding:** retrieval only from the user's own vectors (server-built owner filter; optional `document_ids` are intersected with the user's own documents). Excerpts are delimited untrusted data; `[S#]` citations must refer to supplied excerpts; the sources of cited excerpts are saved with the message. With no relevant excerpts the coach says its advice is general.
- **Honesty:** the system prompt forbids claiming external actions; if an answer still claims to have sent/applied/submitted/saved something, a correction note is appended.
- **History:** last `COACH_HISTORY_MESSAGES` messages within `COACH_HISTORY_CHARS`.
- **Limits:** message length, messages per conversation, conversations per user, and `COACH_MESSAGES_PER_HOUR` per user (invalid requests count too). A failed or abandoned turn deletes its user message so retries do not duplicate.
- **Frontend note:** the stream endpoint is `POST`, so the browser must read it with `fetch` + a stream reader, not `EventSource`.

## Limitations
- Streaming sends tokens before final validation. If validation then fails the client gets an `error` event and the answer is not saved, but part of it may already have been displayed. The system-prompt canary is checked on every chunk to cut leaks short.
- Groq calls (invoke and stream) are tested with the network call replaced; no live Groq request has been made.
- Mock-interview feedback is heuristic. LLM-judged feedback and LangGraph-based interview generation were deliberately not added (a deterministic bank is cheaper, testable and cannot hallucinate); they are possible future improvements.
- The bank has 56 questions; coverage of each topic is two questions. Extend `bank.py` to add more (the integrity tests validate new entries).
- Coach/interview data (conversations, answers) is deleted with the account.
