# Admin dashboard API (Phase 13)

Every route below requires a registered user with the `admin` role (401 without a user token, 403
for a normal user). No schema change, so no migration. Certificate management (Phase 10) and
testimonial moderation and feedback analytics (Phase 12) live under the same `/api/v1/admin` prefix.

| Route | Purpose |
|---|---|
| `GET /admin/overview` | Aggregate counts: users, guest sessions, documents by kind, reports, analyses, interview sessions, conversations, roadmaps by status and duration (7/15/60 only), assessment attempts and pass rate, certificates, projects, public portfolios, ratings, testimonials by status. |
| `GET /admin/users` | List with `search` (email or name, wildcards escaped), `role`, `active`, paging. Shows counts of roadmaps, certificates and attempts. Never returns hashes or content. |
| `PATCH /admin/users/{id}` | `is_active` and/or `role`, optional `reason`. |
| `GET /admin/audit-logs` | Filter by `action` prefix and `actor`; newest first. |
| `GET /admin/assessments` | Per-assessment questions, attempts, pass rate, average score. |
| `GET /admin/system` | Component status and production warnings. Names and booleans only: no keys, URLs or connection strings. |
| `POST /admin/maintenance/cleanup-guests` | Purge expired or deleted guest sessions (data, vectors, files) and audit-log the count. |

## Safeguards
* **Deactivation** ends access at once: `tokens_valid_after` is set (existing access tokens stop
  working) and refresh sessions are revoked. Reactivation restores login.
* **Role change** also invalidates existing tokens, so the new privilege level takes effect on the next sign-in.
* An admin cannot deactivate or demote **their own** account, and the last active administrator can
  never be removed. Both return 409.
* Every change writes an `admin.user_updated` audit entry with the changed fields and reason, never
  the email or any content. A request that changes nothing writes nothing.
* The overview contains counts only. Resume text, job descriptions, answers and chat content are
  not reachable through any admin route.

## Limits
* The last-admin guard cannot be triggered by one admin acting on another (the actor is always a
  second active admin); it protects against concurrent changes and is covered by the self-protection test only.
* `system` does not probe the LLM, Chroma or storage with live calls (that would cost quota or
  block); it reports configuration and checks the database with `SELECT 1`.
* Cleanup runs on demand or through `scripts/cleanup_guest_data.py`; there is no built-in scheduler.
* The dashboard UI belongs to the frontend phase.
