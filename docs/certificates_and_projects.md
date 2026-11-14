# Practical Projects and Certificates (Phase 10)

Registered users only, except public certificate verification.

## Projects (`/api/v1/projects`)
| Endpoint | Purpose |
|---|---|
| `GET /catalog` | 7 authored project templates: description, requirements, expected outcomes, technology recommendations, milestones |
| `GET /recommendations` | Ranked by overlap with a roadmap's focus skills (`roadmap_id`) or with skill gaps from a resume + job description pair |
| `POST /submissions` | Submit a public GitHub repository URL (and/or pasted documentation, a documentation link, notes) |
| `POST /submissions/{id}/evaluate` | Evaluate the supplied evidence (max 3 per submission per day) |
| `GET/DELETE /submissions[/{id}]` | History |

**What the evaluation is - and is not.** It is a **static evidence review** of the repository file list, the README and any pasted documentation. The code is never cloned, run or tested, `code_executed` is always `false`, and every result says "the code was NOT executed and its tests were NOT run". Criteria (weights): requirement coverage 30%, architecture 15%, code quality 15%, documentation 15%, testing 15%, completeness 10% (testing, architecture and code quality are skipped for documentation-only projects). A project passes with an overall score >= 70 (configurable `PROJECT_PASS_SCORE`), requirement coverage >= 60%, a README or documentation, and (for code projects) at least 5 source files. A repo with no test files cannot score above 25 on testing, whatever the configuration or README claims. Feedback lists concrete improvements.
**Honest limits:** this can show a project is structured and documented, not that it works, and a determined person could fabricate the signals. Mitigations: a repository that already passed for another learner cannot be reused, evaluations are rate-limited, and the result is labelled as automated. Treat a Project Completion Certificate as evidence of a documented, structured submission, not a verified deliverable.
**GitHub access:** only `https://github.com/<owner>/<repo>` URLs are accepted; only `api.github.com` is called (file listing, README, repo metadata), with timeouts, size caps, no redirects. Documentation links are stored but never fetched (no SSRF). Optional `GITHUB_TOKEN` raises API rate limits. Live GitHub calls have not been exercised here (tests use a mocked transport).

## Certificates (`/api/v1/certificates`)
Three platform-issued types, each requiring evidence the **server verifies itself**:
- **Learning Completion**: the user's roadmap is completed and its criteria still hold (>= 80% of required activities and every assessment passed).
- **Assessment**: the user's own attempt passed that assessment's pass mark.
- **Project Completion**: the user's own project evaluation passed.
There is no way to issue from a client claim: unknown or foreign evidence returns 404, unmet evidence 422, a second certificate for the same achievement 409 (database unique constraint on user + source), plus a daily limit.

| Endpoint | Purpose |
|---|---|
| `GET /eligibility` | Evidence that can be certified now |
| `POST /` | Issue (`certificate_type`, `source_id`, optional `learner_name`, which is printed publicly; default = display name; control characters and `<>` removed) |
| `GET /`, `GET /{id}/download` | Own certificates; PDF download (revoked certificates are refused) |
| `GET /verify/{id}` | **Public**, rate limited: `valid` / `revoked` (200) or `invalid` (404, `status: invalid`) |
| `POST /api/v1/admin/certificates/{id}/revoke`, `GET /admin/certificates` | Admin only |

- **ID:** `ACC-XXXX-XXXX-XXXX` (Crockford base32 from a CSPRNG, 60 bits).
- **PDF:** A4 landscape with vector logo and platform name, learner name, title, topic, category, issue date, score (assessment/project), certificate ID, QR code (vector, encodes the verification URL `FRONTEND_URL/verify/<id>`) and the URL as text, plus the statement that it is platform-issued and **not an externally accredited qualification**. Rendered on demand (nothing stored on ephemeral disk).
- **Privacy:** verification returns the certificate facts and the chosen learner name only (no email or user id); the revocation reason is internal. Deleting an account deletes its certificates (their IDs then verify as invalid).
- **Revocation and audit:** admin revocation records who/when/why and writes audit-log entries for issuing and revoking (no personal data in details).

## Not done / limits
- Project evaluation is static; no sandboxed execution of submitted code.
- The frontend verification page (`/verify/<id>`) is built in the frontend phase; the QR already points to it.
- Migration `0006` verified on SQLite and rendered offline for PostgreSQL only.
