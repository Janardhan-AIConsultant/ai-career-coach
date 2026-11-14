# Guest Access (Phase 5)

Guests use the platform without login. Authentication is a **secret capability token**, not a session ID.

## Flow
1. `POST /api/v1/guest/sessions` -> `{session_id, token, expires_at, limits}`. The token (256-bit random) is shown once; only its SHA-256 is stored. Rate limited per client IP (`GUEST_SESSIONS_PER_IP_PER_HOUR`; `X-Forwarded-For` is deliberately not trusted).
2. Send the token in the `X-Guest-Token` header on every call (never in URLs; never logged).
3. `POST /api/v1/guest/documents` (multipart: `kind` = `resume|job_description`, plus exactly one of `file` or `text`) -> validated, extracted, indexed. Original file bytes are **not stored**; only extracted text and vectors.
4. `GET/DELETE /api/v1/guest/documents[/{id}]`, `GET /api/v1/guest/reports/{id}/download`, `DELETE /api/v1/guest/sessions/{session_id}`.

## Protections
Server-side expiry check on every request; per-session request quota (`MAX_REQUESTS_PER_SESSION`) and document quota (`GUEST_MAX_DOCUMENTS`); upload size cap; bounded concurrent ingestion (`MAX_CONCURRENT_INGESTIONS`, returns 503 when busy); other guests' ids return 404 (no enumeration); reports are ownership- and expiry-checked and served with `nosniff`, `no-store`, `attachment`.

## Expiry and cleanup
Expired sessions are unusable immediately. `scripts/cleanup_guest_data.py` physically removes vectors, report files and rows (run it from a scheduler, e.g. Render Cron). A failed purge leaves the session intact and is retried; it never half-deletes.

## Not yet done (later phases)
- (Done in Phase 7) The five analysis endpoints and report generation: see `career_intelligence.md`.
- Guest-to-account transfer needs registration (Phase 6).
- Local object storage is for development; production needs an S3-compatible backend (not implemented; `s3` fails fast).
- Rate limiting is in-process (single instance).
