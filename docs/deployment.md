# Deployment guide

Target topology: **Vercel** (React app) -> rewrite `/api/*` -> **Render** (FastAPI, Docker) -> **Neon**
(PostgreSQL) + **Chroma Cloud** (vectors) + **Groq** (LLM, optional) + an **S3-compatible bucket**
(generated files, recommended).

None of these steps has been executed from this repository: no cloud account was used, so the files below
are configuration prepared for you, not a verified deployment. Verify each step as you go.

## Decisions that need your approval (cost)
I have not signed up for or enabled any paid service. Please decide:

| Item | Why it matters | Options |
|---|---|---|
| **Embeddings** | Render's free web service has 512 MB RAM, too little for the local `sentence-transformers` model. `EMBEDDING_PROVIDER=hash` works but is lexical-only (retrieval quality is lower; the app warns about it in production). | (a) accept `hash` for a demo; (b) a larger Render instance and `local-hf` (paid); (c) a hosted embedding API (new adapter + a possibly paid account). Nothing is chosen for you. |
| **File storage** | Render's disk is ephemeral: generated reports/certificates vanish on restart with `OBJECT_STORAGE_BACKEND=local`. | An S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2, MinIO) with `OBJECT_STORAGE_BACKEND=s3`. Providers differ in free allowances and egress fees: check their current pricing. |
| **Render plan** | The free plan sleeps when idle (first request is slow) and has limited RAM/hours. | Stay free for a demo, or pick a paid plan for always-on. |
| **Chroma Cloud / Neon / Groq** | Each has a free or trial tier at the time of writing, with limits that change. | Check current limits before launch; the app degrades gracefully without a Groq key (deterministic answers). |

Do not exceed a free tier silently: set budget alerts on any account that accepts a card.

## 1. Neon (database)
1. Create a project and database; copy the connection string.
2. Convert it for SQLAlchemy/psycopg 3: `postgresql+psycopg://<USER>:<PASSWORD>@<HOST>/<DBNAME>?sslmode=require`.
3. Keep it secret. It goes only into Render's `DATABASE_URL`.
4. Migrations run automatically on every deploy (`alembic upgrade head` in the container start command).
   **Not yet verified against a live PostgreSQL**: run the first deploy against an empty Neon branch and
   check the logs. Alembic's offline SQL rendering for PostgreSQL was checked; a live run was not.

## 2. Chroma Cloud (vectors)
Create a database and API key; set `CHROMA_API_KEY`, `CHROMA_TENANT`, `CHROMA_DATABASE` on Render. With no
key the app falls back to a local persistent Chroma directory that is lost on restart.

## 3. Groq (LLM, optional)
Set `GROQ_API_KEY` (and optionally `LLM_MODEL`). Without it, scores, gaps and roadmaps still work (they are
deterministic); the narrative summary and coach answers use grounded fallbacks. The key is never sent to the
browser.

## 4. Storage bucket (recommended)
Create a private bucket and an access key limited to it. Set `OBJECT_STORAGE_BACKEND=s3`, `S3_BUCKET`,
`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, and for non-AWS providers `S3_ENDPOINT_URL` (and `S3_REGION`).
The code was tested against a fake client only, not a live bucket.

## 5. Render (API)
1. New > Blueprint, point at this repository: `render.yaml` defines the service (Docker, `/health` check,
   production mode, JSON logs).
2. Enter every `sync: false` value in the dashboard (table below). Nothing secret is in the repository.
3. Generate `JWT_SECRET_KEY` locally: `python -c "import secrets;print(secrets.token_urlsafe(48))"`.
4. Deploy, then open `https://<service>.onrender.com/health` and `/api/v1/health/database`.

| Variable | Value |
|---|---|
| `APP_ENV` | `production` (already set) |
| `DATABASE_URL` | Neon URL from step 1 |
| `JWT_SECRET_KEY` | random, at least 32 characters |
| `FRONTEND_URL`, `CORS_ORIGINS` | your exact Vercel origin, e.g. `https://my-app.vercel.app` (no trailing slash) |
| `GROQ_API_KEY`, `LLM_MODEL` | step 3 (optional) |
| `CHROMA_API_KEY`, `CHROMA_TENANT`, `CHROMA_DATABASE` | step 2 |
| `EMBEDDING_PROVIDER` | `hash` or `local-hf` (see decisions above) |
| `OBJECT_STORAGE_BACKEND`, `S3_*` | step 4 |
| `GITHUB_TOKEN` | optional, raises GitHub API rate limits for project review |

The admin console warns (Admin > System) when production runs with hash embeddings, local storage, SQLite or
a localhost `FRONTEND_URL`.

## 6. Vercel (frontend)
1. Import the repository, set the **Root Directory** to `frontend`.
2. Edit `frontend/vercel.json`: replace `YOUR-RENDER-SERVICE.onrender.com` with your Render host.
3. Set the environment variable `VITE_API_BASE_URL` to `/` (same-origin). The rewrite proxies `/api/*` to
   Render, so the refresh cookie is first-party (browsers increasingly block third-party cookies) and no
   cross-origin CORS is needed.
4. Deploy. `FRONTEND_URL` and `CORS_ORIGINS` on Render must equal the Vercel origin because the API checks the
   browser `Origin` header on cookie endpoints.

## 7. First administrator
There is no public way to become an admin. Run locally against production (the password is read from the
environment or prompted, never put on a command line):

```bash
cd backend
DATABASE_URL="<neon url>" ADMIN_PASSWORD="<strong password>" python ../scripts/create_admin.py you@example.com "Your Name"
```

## 8. Scheduled cleanup
Expired guest sessions are removed on demand (Admin > System, `POST /api/v1/admin/maintenance/cleanup-guests`)
or by `scripts/cleanup_guest_data.py`. Render's free plan has no cron; run it from your machine or a scheduler
you already have.

## Post-deploy checklist
- [ ] `/health`, `/api/v1/health/database`, `/api/v1/health/vector-store` return OK.
- [ ] A guest can run a match from the Vercel URL, and a refresh keeps a registered user signed in.
- [ ] `GET /api/v1/admin/system` (as admin) shows no unexpected warnings.
- [ ] A generated report downloads after a service restart (proves durable storage).
- [ ] Budget alerts are set on every account with a payment method.

## Local Docker Compose
`docker compose up --build` starts PostgreSQL, Chroma, the API (migrations run on start) and the Vite dev
server. The compose passwords are local-only values.
