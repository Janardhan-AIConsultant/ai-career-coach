"""Render brand PNGs (app icons, README logo) from the single source ``frontend/public/logo.svg``.

Usage (from ``backend/``): python ../scripts/generate_brand_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.brand import LOGO_SVG, logo_png  # noqa: E402

PUBLIC = ROOT / "frontend" / "public"
TARGETS = [(PUBLIC / "apple-touch-icon.png", 180), (PUBLIC / "logo-512.png", 512),
           (ROOT / "docs" / "images" / "logo.png", 512)]


def main() -> int:
    source = (PUBLIC / "logo.svg").read_text(encoding="utf-8")
    if source.strip() != LOGO_SVG.strip():
        print("warning: backend/app/services/brand.py LOGO_SVG differs from frontend/public/logo.svg", file=sys.stderr)
        return 1
    for path, size in TARGETS:
        path.write_bytes(logo_png(size))
        print("wrote", path)
    (ROOT / "docs" / "images" / "logo.svg").write_text(source, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
