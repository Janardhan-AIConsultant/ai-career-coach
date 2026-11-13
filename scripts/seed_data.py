"""Seed reference data (assessment bank). Idempotent: existing assessments (by slug) are kept.

Run from ``backend/``:  python ../scripts/seed_data.py
The API also seeds missing assessments lazily on first use, so running this is optional.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.database import get_session_factory  # noqa: E402
from app.services.assessment_service import seed_assessments  # noqa: E402


def main() -> int:
    with get_session_factory()() as db:
        created = seed_assessments(db)
    print(f"assessments created: {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
