"""Render a platform-issued certificate to PDF (A4 landscape) with logo, QR code and verification URL.

The logo is vector-drawn (no image files). The QR code encodes the public verification URL and is
drawn from the QR matrix as vector squares (``segno``), so no imaging libraries are needed.
Learner-provided text is HTML-escaped. The footer always states that the certificate is issued by
the platform and is not an externally accredited qualification.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

import pymupdf
import segno

from app.core.exceptions import ReportGenerationError

PLATFORM_NAME = "AI Career Coach"
CATEGORY_LABEL = {
    "learning_completion": "Learning Completion",
    "assessment": "Assessment",
    "project_completion": "Project Completion",
}
DISCLAIMER = ("This certificate is issued by the AI Career Coach platform to recognise completed learning activity. "
              "It is not an externally accredited qualification or a professional licence.")
_NAVY = (0.10, 0.16, 0.33)
_GOLD = (0.78, 0.60, 0.18)


@dataclass(frozen=True)
class CertificateData:
    code: str
    certificate_type: str
    title: str
    topic: str
    learner_name: str
    issued_at: datetime
    score: float | None
    verification_url: str


def qr_matrix(url: str) -> list[list[bool]]:
    qr = segno.make(url, error="m", micro=False)
    return [[bool(c) for c in row] for row in qr.matrix]


def _draw_logo(page: pymupdf.Page, cx: float, cy: float) -> None:
    shape = page.new_shape()
    shape.draw_circle((cx, cy), 22)
    shape.finish(fill=_NAVY, color=_GOLD, width=2)
    shape.draw_polyline([(cx - 11, cy + 8), (cx, cy - 12), (cx + 11, cy + 8)])  # stylised "A"
    shape.finish(color=(1, 1, 1), width=3, closePath=False)
    shape.draw_line((cx - 6, cy + 1), (cx + 6, cy + 1))
    shape.finish(color=(1, 1, 1), width=2)
    shape.commit()


def _draw_qr(page: pymupdf.Page, url: str, x: float, y: float, size: float) -> None:
    matrix = qr_matrix(url)
    quiet = 2
    n = len(matrix) + 2 * quiet
    cell = size / n
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(x, y, x + size, y + size))
    shape.finish(fill=(1, 1, 1), color=None)
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                rx, ry = x + (c + quiet) * cell, y + (r + quiet) * cell
                shape.draw_rect(pymupdf.Rect(rx, ry, rx + cell, ry + cell))
    shape.finish(fill=(0, 0, 0), color=None)
    shape.commit()


def render_certificate(d: CertificateData) -> bytes:
    try:
        doc = pymupdf.open()
        page = doc.new_page(width=842, height=595)
        outer = pymupdf.Rect(24, 24, 818, 571)
        border = page.new_shape()
        border.draw_rect(outer)
        border.finish(color=_NAVY, width=3)
        border.draw_rect(outer + (8, 8, -8, -8))
        border.finish(color=_GOLD, width=1)
        border.commit()
        _draw_logo(page, 421, 78)

        e = html.escape
        category = CATEGORY_LABEL.get(d.certificate_type, d.certificate_type)
        css = "* { font-family: sans-serif; text-align: center; } .c { color: #1a2954; }"
        blocks = [
            (pymupdf.Rect(60, 108, 782, 132), f'<p class="c" style="font-size:13pt;letter-spacing:3pt">{e(PLATFORM_NAME.upper())}</p>'),
            (pymupdf.Rect(60, 138, 782, 186), f'<p class="c" style="font-size:26pt"><b>Certificate of {e(category)}</b></p>'),
            (pymupdf.Rect(60, 196, 782, 214), '<p style="font-size:11pt">This is to certify that</p>'),
            (pymupdf.Rect(60, 218, 782, 268), f'<p class="c" style="font-size:28pt"><b>{e(d.learner_name)}</b></p>'),
            (pymupdf.Rect(60, 276, 782, 296), '<p style="font-size:11pt">has successfully completed</p>'),
            (pymupdf.Rect(80, 300, 762, 348), f'<p class="c" style="font-size:17pt"><b>{e(d.topic)}</b></p>'),
        ]
        meta = [f"Category: {category}", f"Issued: {d.issued_at.strftime('%d %B %Y')}"]
        if d.score is not None:
            meta.insert(1, f"Score: {d.score:g}%")
        blocks.append((pymupdf.Rect(60, 356, 782, 376), f'<p style="font-size:10.5pt">{e("   |   ".join(meta))}</p>'))
        blocks.append((pymupdf.Rect(60, 378, 782, 396), f'<p style="font-size:10pt"><b>Certificate ID: {e(d.code)}</b></p>'))
        blocks.append((pymupdf.Rect(60, 505, 560, 555), f'<p style="font-size:8pt;text-align:left">{e(DISCLAIMER)}</p>'))
        blocks.append((pymupdf.Rect(580, 505, 800, 555),
                       f'<p style="font-size:7.5pt;text-align:right">Verify: {e(d.verification_url)}</p>'))
        for rect, body in blocks:
            spare, _scale = page.insert_htmlbox(rect, body, css=css, scale_low=0.3)  # shrinks long text to fit
            if spare < 0:
                raise ReportGenerationError("Certificate text is too long to render")
        _draw_qr(page, d.verification_url, 372, 400, 100)
        data: bytes = doc.tobytes()
        doc.close()
        return data
    except (RuntimeError, ValueError) as exc:
        raise ReportGenerationError() from exc
