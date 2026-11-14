"""Brand mark used by server-rendered artefacts (certificates, share cards).

LOGO_SVG must stay identical to ``frontend/public/logo.svg`` (a test enforces it).
"""

from __future__ import annotations

import pymupdf

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="AI Career Coach logo">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4f46e5"/>
      <stop offset="0.6" stop-color="#2563eb"/>
      <stop offset="1" stop-color="#0ea5e9"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="16" fill="url(#bg)"/>
  <path d="M44 44A17 17 0 1 1 44 20" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round"/>
  <path d="M23 40L30 33L35 37L46 25" fill="none" stroke="#fbbf24" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M40 24.5H46.5V31" fill="none" stroke="#fbbf24" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="50" cy="14" r="2.2" fill="#fff" opacity="0.9"/>
</svg>
"""


def logo_png(size: int = 256) -> bytes:
    """Rasterise the logo to a square PNG using PyMuPDF (no extra imaging dependency)."""
    # MuPDF's SVG converter has no gradient support, so rasters use the solid brand blue instead.
    flat = LOGO_SVG.replace('fill="url(#bg)"', 'fill="#2563eb"')
    src = pymupdf.open(stream=flat.encode("utf-8"), filetype="svg")
    pdf = pymupdf.open("pdf", src.convert_to_pdf())
    page = pdf[0]
    zoom = size / page.rect.width
    png: bytes = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True).tobytes("png")
    pdf.close()
    src.close()
    return png
