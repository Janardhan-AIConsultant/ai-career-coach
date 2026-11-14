# Authentication and Accounts (Phase 6)

## Endpoints (`/api/v1`)
| Endpoint | Purpose |
|---|---|
| `POST /auth/register` | Create account (role is always `user`; request cannot choose it). Returns access token + sets refresh cookie |
| `POST /auth/login` | Email + password. One generic failure message; rate limited per email and per IP |
| `POST /auth/refresh` | Rotates the refresh cookie, returns a new access token |
| `POST /auth/logout` | Revokes the refresh token, clears the cookie (idempotent) |
| `GET/PATCH /users/me`, `GET/PUT /users/me/profile` | Account and profile |
| `POST /users/me/password` | Change password; revokes all other sessions and older access tokens |
| `DELETE /users/me` | Delete account (password + `confirm: true`) |
| `POST /users/me/import-guest-session` | Move a guest session's data into the account (consent + guest token required) |

## Design
- **Passwords:** Argon2id; 10-128 chars with a letter and a digit. Unknown-email logins do a dummy hash check so timing doesn't reveal accounts.
- **Access token:** HS256 JWT, 30 min (`ACCESS_TOKEN_EXPIRE_MINUTES`), returned in the body for the SPA to hold in memory (not localStorage). The role is never read from the token; each request reloads the user.
- **Refresh token:** 256-bit random, HttpOnly cookie scoped to `/api/v1/auth`, stored only as a SHA-256 hash, rotated on every use. Reusing a rotated token revokes all of the user's sessions. In production the cookie is `Secure; SameSite=None` (Vercel and Render are different sites), so refresh/logout also verify the `Origin` header against `CORS_ORIGINS`.
- **Revocation:** `users.tokens_valid_after` rejects access tokens issued before a password change or reuse event (second-level granularity: a token minted in the same second as the change is not rejected).
- **Roles:** Guest, User, Admin. Admins can only be created with `scripts/create_admin.py`; `require_admin` checks the database role.
- **Validation errors** never echo submitted values.

## Guest import
Requires an authenticated user, the guest's secret token (ownership proof) and `consent: true`. Rows are re-owned in one transaction, vectors re-tagged before commit and restored if the commit fails; imported items lose their guest expiry; the guest token stops working afterwards.

## Account deletion
Deletes documents, resumes/JDs, analyses, reports (files), vectors, conversations, feedback, testimonials, profile and sessions. Certificates, project submissions/evaluations, roadmaps, assessment and interview data are deleted too (right to erasure), so a deleted learner's certificate IDs then verify as `invalid`. The user row is anonymised and the email becomes reusable.

## Known limitations
- Registering an existing email returns 409, which reveals that the address is registered (common MVP trade-off; mitigated by rate limiting). No email verification or password reset yet (needs an email provider, a cost/approval decision).
- Access tokens remain valid until expiry after a plain logout (30 min max); password change and reuse detection invalidate them.
- Rate limits are in-process (single instance).
- Postgres migrations 0001-0003 are verified on SQLite and rendered offline, not yet run on live PostgreSQL.
