"""Start a throwaway backend for the end-to-end tests: fresh SQLite database, local hash embeddings,
no LLM key. Run from ``frontend/`` by Playwright; never used outside local testing.

Secrets come from the environment that Playwright sets for this run (random per run).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
WORK = Path(os.environ.get("E2E_WORKDIR", ROOT / "frontend" / "e2e" / ".run")).resolve()


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    env = {
        **os.environ,
        "APP_ENV": "development",
        "DATABASE_URL": f"sqlite:///{(WORK / 'e2e.db').as_posix()}",
        "EMBEDDING_PROVIDER": "hash",
        "CHROMA_PERSIST_PATH": str(WORK / "chroma"),
        "OBJECT_STORAGE_PATH": str(WORK / "storage"),
        "CORS_ORIGINS": "http://localhost:5173",
        "FRONTEND_URL": "http://localhost:5173",
        "LOG_FORMAT": "text",
        "GROQ_API_KEY": "",
        "CHROMA_API_KEY": "",
        "CHROMA_HOST": "",
    }
    for needed in ("JWT_SECRET_KEY", "E2E_ADMIN_EMAIL", "E2E_ADMIN_PASSWORD"):
        if not env.get(needed):
            print(f"{needed} must be set by the test runner", file=sys.stderr)
            return 2
    py = sys.executable
    subprocess.run([py, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)
    subprocess.run(
        [py, str(ROOT / "scripts" / "create_admin.py"), env["E2E_ADMIN_EMAIL"], "E2E Admin"],
        cwd=BACKEND, env={**env, "ADMIN_PASSWORD": env["E2E_ADMIN_PASSWORD"]}, check=True)
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    os.environ.update(env)
    import uvicorn

    uvicorn.run("app.main:app", host="localhost", port=8000, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
