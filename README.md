# AI Career Coach

Status: **Phase 2 scaffold** (see `docs/`). Career features are implemented in later phases; this README lists only what exists now.

## Layout
- `backend/` FastAPI app (`app/core/config.py`, `logging_config.py`, `main.py`, `/health`, `/api/v1/health`)
- `frontend/` React 18 + TypeScript + Vite + Tailwind (placeholder page showing API status)
- `data/` sample resume and job description
- `docs/` existing-project analysis, migration plan, architecture

## Backend
```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # Windows (use bin/activate on macOS/Linux)
pip install -r requirements-dev.txt
cp ../.env.example .env                           # fill in values locally; never commit .env
uvicorn app.main:app --reload
pytest --cov=app && ruff check . && mypy app
```

## Frontend
```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 ; set VITE_API_BASE_URL if the API is elsewhere
npm test && npm run build
```

## Docker Compose (local)
Create `backend/.env` first (copy `.env.example`), then `docker compose up --build`. Starts PostgreSQL, Chroma, backend and frontend with named volumes. Database and Chroma are not yet used by the backend (Phase 3/4).

## Secrets
`.env` is git-ignored; `.env.example` has placeholders only. Only `VITE_API_BASE_URL` is exposed to the browser.
