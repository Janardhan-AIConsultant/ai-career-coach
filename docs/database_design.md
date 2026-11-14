# Database Design (Phase 3)

PostgreSQL via SQLAlchemy 2.x; migrations in `backend/alembic` (`0001_initial_schema`). 27 tables, one per entity in the spec. JSON columns use JSONB on PostgreSQL and JSON elsewhere. No embeddings are stored in PostgreSQL (vectors live in ChromaDB).

| Module | Tables |
|---|---|
| `models/accounts.py` | users, user_profiles, user_sessions (refresh-token hash), guest_sessions (token hash) |
| `models/documents.py` | documents, resumes, job_descriptions, career_analyses, skill_gap_analyses |
| `models/learning.py` | conversations, messages, learning_roadmaps, learning_modules, learning_activities, assessments, assessment_questions, assessment_attempts |
| `models/achievements.py` | project_submissions, project_evaluations, certificates, portfolios, portfolio_achievements |
| `models/feedback.py` | feedback, testimonials, testimonial_share_events, moderation_logs, audit_logs |

## Integrity rules enforced in the database
- **Ownership:** documents, resumes, job_descriptions, career_analyses, skill_gap_analyses must belong to exactly one of a user or a guest session (CHECK).
- **Roadmap durations:** `duration_days IN (7, 15, 60)`.
- **Share platforms:** `platform IS NULL OR IN ('linkedin','whatsapp','facebook')`; event types `share_click | card_download | link_copy`. Share events store no user/IP data.
- **Certificates:** must reference evidence (roadmap, assessment attempt or project evaluation); type and status are closed sets; `certificate_code` is unique.
- **Ratings:** 1-5; testimonial status closed set; `is_publicly_visible` requires approved + consent + not withdrawn + not deleted.
- Unique email, unique token hashes, soft deletion (`deleted_at`) on user-facing content, FK indexes throughout.

Closed value sets live in `app/core/constants.py` and are used to build the CHECK constraints, so code and schema cannot drift.

## Verification status
- Constraints and the migration are tested on SQLite (upgrade and downgrade, tables match models).
- PostgreSQL DDL was rendered offline (`alembic upgrade head --sql`) and inspected; it was **not yet executed against a live PostgreSQL** because Docker Desktop did not start in this session. Run `alembic upgrade head` against Postgres (docker compose) to complete verification.
