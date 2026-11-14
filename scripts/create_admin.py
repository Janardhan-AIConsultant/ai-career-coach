"""Create (or promote) an administrator account. There is no public way to obtain admin rights.

Usage (from ``backend/``): ``ADMIN_PASSWORD=... python ../scripts/create_admin.py admin@example.com "Admin"``
If ADMIN_PASSWORD is unset the password is prompted for (never passed on the command line).
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.database import get_session_factory  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import User  # noqa: E402
from app.schemas.auth import validate_password_strength  # noqa: E402
from app.services.auth_service import normalize_email  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: create_admin.py EMAIL [DISPLAY_NAME]")
        return 2
    email = normalize_email(argv[1])
    name = argv[2] if len(argv) > 2 else "Administrator"
    with get_session_factory()() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
            validate_password_strength(password)
            user = User(email=email, password_hash=hash_password(password), display_name=name,
                        role="admin")
            db.add(user)
        else:
            user.role = "admin"
        db.commit()
    print(f"admin ready: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
