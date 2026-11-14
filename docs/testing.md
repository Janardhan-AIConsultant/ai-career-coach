# Testing and hardening (Phase 14)

## What exists and how to run it
| Layer | Command (from) | Scope |
|---|---|---|
| Backend unit + API | `python -m pytest` (`backend/`, venv active) | 581 tests: services, routes, security, privacy, migrations on SQLite |
| Static checks | `python -m ruff check app tests`, `python -m mypy app` (`backend/`) | lint, `mypy --strict` |
| Frontend unit | `npm test` (`frontend/`) | 19 Vitest tests: HTTP client, guards, forms, consent, sharing, 7/15/60 |
| Frontend types and build | `npm run build` (`frontend/`) | `tsc --noEmit` then Vite build |
| End to end | `npm run e2e` (`frontend/`) | 6 Playwright journeys against a real backend and a real browser |

## Cross-cutting backend checks (`backend/tests/test_hardening.py`)
* **Authentication sweep.** The test reads the OpenAPI schema, calls every documented operation
  without credentials and fails if any route outside a small allow-list answers with anything other
  than 401/403. The allow-list itself is checked, so it cannot silently go stale. Every `/admin` route
  is called as an ordinary user (must be 403) and user routes are called with a guest token.
* **Error envelope.** Unknown routes and wrong methods now use the same `{"error": {...}}` envelope as
  every other error (found by this suite: they previously returned FastAPI's `{"detail": ...}`).
  Validation errors do not echo submitted values; no stack traces or file names leak.
* **Headers, CORS, cookies.** Security headers on success, 404 and auth failures; only the configured
  origin is allowed; the refresh cookie is HttpOnly with SameSite.
* **Log hygiene.** Resume text, passwords, guest tokens and the JWT secret never appear in log records.
* **Repository policy** (over `git ls-files`): no X/Twitter/Telegram, no roadmap length other than
  7/15/60, no real-looking keys or credential-bearing URLs, no tracked `.env`, placeholder-only
  `.env.example`.

## End-to-end journeys (`frontend/e2e/journeys.spec.ts`)
1. A guest runs a match with no account. 2. Anonymous visitors are redirected from account and
admin pages. 3. An unknown certificate ID is "not found". 4. A user registers, creates a 15-day
roadmap and stays signed in after a reload (refresh cookie). 5. Testimonial lifecycle: consent
unticked by default, hidden until moderated, approved by an admin, public with only the chosen
display name, exactly three share links, consent withdrawal unpublishes it. 6. An ordinary user
cannot open the admin console.

The runner starts a throwaway backend (fresh SQLite database, hash embeddings, no LLM key) and the
Vite dev server. The admin password and JWT secret are random per run; nothing is stored. It drives
the Microsoft Edge that is already installed (`channel: "msedge"`), so no browser is downloaded;
set `E2E_BROWSER_CHANNEL=chrome` to use Chrome instead.

## Defects the new tests found (all fixed)
* Unknown routes and wrong methods returned a different error shape (backend).
* The access-token refresh helper could hand back a finished attempt to a later caller (frontend).
* Two uploads in one guest run each created a new guest session, so the second document was
  invisible to the first (frontend; found only by the browser test).

## What is not covered
* **No live PostgreSQL run.** Migrations are verified on SQLite and rendered offline for Postgres.
  E2E also uses SQLite.
* **No live Groq, GitHub or Chroma Cloud calls.** LLM and GitHub behaviour is tested with fakes;
  the E2E backend runs without an LLM key (deterministic paths only).
* The E2E suite covers six journeys, not every screen. Roadmap activity completion, assessments,
  certificate issuing, the coach and the portfolio page have unit tests (backend and, in part,
  frontend) but no browser journey.
* No accessibility audit beyond semantic roles, labels and keyboard-reachable controls; no visual
  regression or load testing.
* In-process rate limiting is per server instance.
* `npm audit --omit=dev` reports two moderate advisories in `react-router` 6.x (an open redirect via
  a backslash in `<Link>`/`useNavigate`, and an SSR-hydration issue). The fix is react-router 7, a
  breaking upgrade that has not been made. Exposure here: the app is client-rendered only, and the
  one redirect target (`state.from` after sign-in) is set internally from the current path, never
  from a URL parameter. Upgrading is listed as an open item for Phase 15.
* `npm audit` also lists advisories in development tooling. `pip-audit` is not installed here, so the
  Python dependencies have not been audited.
