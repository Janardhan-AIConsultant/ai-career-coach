"""Branded PNG share card for a testimonial (rendered locally with PyMuPDF, no external service).

The card carries only what the public view carries: the user's own words, their chosen display name
and optional rating. It makes no claim beyond that, and says so in the footer.
"""

from __future__ import annotations

import html
import math

import pymupdf

from app.services.brand import logo_png

WIDTH, HEIGHT = 1200, 630
NAVY, BLUE, GOLD, LIGHT = (0.07, 0.11, 0.24), (0.15, 0.39, 0.92), (0.98, 0.75, 0.14), (0.93, 0.95, 0.99)
MAX_CHARS = 320


def excerpt(text: str, limit: int = MAX_CHARS) -> str:
    """Whole-word excerpt with an ellipsis; never alters the wording otherwise."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.-")
    return cut + "..."


def _star(cx: float, cy: float, r: float) -> list[pymupdf.Point]:
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append(pymupdf.Point(cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def render_card(text: str, display_name: str, rating: int | None) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=WIDTH, height=HEIGHT)
    page.draw_rect(page.rect, color=None, fill=NAVY)
    page.draw_rect(pymupdf.Rect(0, 0, 18, HEIGHT), color=None, fill=BLUE)

    page.insert_image(pymupdf.Rect(70, 36, 118, 84), stream=logo_png(192))
    page.insert_htmlbox(
        pymupdf.Rect(132, 44, 800, 100),
        '<span style="color:#9db4ff;font-size:30px;font-weight:bold">AI Career Coach</span>')
    body = html.escape(excerpt(text))
    page.insert_htmlbox(
        pymupdf.Rect(70, 130, 1130, 470),
        f'<div style="color:#f3f6ff;font-size:38px;line-height:1.35">&ldquo;{body}&rdquo;</div>')

    shape = page.new_shape()
    if rating:
        for i in range(5):
            shape.draw_polyline(_star(90 + i * 48, 505, 20))
            shape.finish(color=None, fill=GOLD if i < rating else (0.3, 0.35, 0.5), closePath=True)
    shape.commit()

    name = html.escape(display_name or "Anonymous learner")
    page.insert_htmlbox(
        pymupdf.Rect(70, 535, 800, 585),
        f'<span style="color:#ffffff;font-size:30px;font-weight:bold">&mdash; {name}</span>')
    page.insert_htmlbox(
        pymupdf.Rect(700, 585, 1150, 620),
        '<span style="color:#7f8fb8;font-size:15px">Shared by the user in their own words</span>')
    png = page.get_pixmap(dpi=72).tobytes("png")
    doc.close()
    return bytes(png)
