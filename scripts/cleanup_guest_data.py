"""Purge expired guest sessions (vectors, stored files, database rows).

Run on a schedule (e.g. a Render Cron Job every 15-60 minutes) from the ``backend`` directory:
    python ../scripts/cleanup_guest_data.py
Expired sessions are already rejected at access time; this removes their data. Exit code 1 if any
candidate session could not be purged (it will be retried on the next run).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_session_factory  # noqa: E402
from app.core.logging_config import configure_logging  # noqa: E402
from app.rag.embeddings import create_embeddings  # noqa: E402
from app.rag.vector_store import create_vector_store  # noqa: E402
from app.services.guest_service import cleanup_expired  # noqa: E402
from app.services.object_storage import create_object_storage  # noqa: E402

logger = logging.getLogger("cleanup_guest_data")


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    store = create_vector_store(settings, create_embeddings(settings))
    storage = create_object_storage(settings)
    with get_session_factory()() as db:
        purged = cleanup_expired(db, store, storage)
    print(f"purged {purged} guest session(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
