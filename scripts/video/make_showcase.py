"""Render a 4K (3840x2160) project showcase image: a portfolio "cover" explaining what AI Career Coach does.

Uses the same vector drawing layer and brand mark as the intro video. Numbers shown are real measured results
(see docs/testing.md); on-screen result values (match %, skills) are illustrative and labelled as such.

Usage (with the video requirements installed): python make_showcase.py OUT_DIR
Writes ai-career-coach-showcase-4k.png and a 1920x1080 .jpg for sites with upload limits.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_intro as R  # noqa: E402

W, H = R.W, R.H


def tile(c, x, y, w, h, fill="#ffffff", op=0.96, r=22):
    c.rrect(x, y, w, h, r, fill=fill, op=op)


def window(c, x, y, w, h):
    tile(c, x, y, w, h, "#f8fafc", 0.99, 22)
    c.rrect(x, y, w, 44, 22, fill="#e2e8f0")
    c.rrect(x, y + 22, w, 22, 0, fill="#e2e8f0")
    for k, col in enumerate(("#f87171", "#fbbf24", "#34d399")):
        c.ell(x + 28 + k * 24, y + 22, 7, 7, fill=col)
    c.rrect(x + 130, y + 9, 320, 26, 13, fill="#ffffff")
    c.text(x + 148, y + 28, "/analyze", 15, "#64748b")


def doc_card(c, x, y, w, h, label, col):
    c.rrect(x, y, w, h, 14, fill="#ffffff", stroke="#e2e8f0", sw=1.5)
    c.rrect(x, y, w, 38, 14, fill=col)
    c.rrect(x, y + 20, w, 18, 0, fill=col)
    c.text(x + 16, y + 26, label, 15, "#ffffff", True)
    for k, ln in enumerate((0.9, 0.75, 0.95, 0.6, 0.85)):
        c.rrect(x + 16, y + 56 + k * 24, (w - 32) * ln, 9, 4.5, fill="#cbd5e1")


def icon(c, kind, cx, cy, s, col="#ffffff"):
    """Tiny pictograms drawn from shapes (no font glyphs needed)."""
    if kind == "doc":
        c.rrect(cx - s * 0.6, cy - s * 0.8, s * 1.2, s * 1.6, 3, stroke=col, sw=2.2)
        for k in range(3):
            c.poly([(cx - s * 0.3, cy - s * 0.35 + k * s * 0.4), (cx + s * 0.3, cy - s * 0.35 + k * s * 0.4)], None, col, 2, closed=False)
    elif kind == "target":
        for rr in (0.85, 0.5, 0.15):
            c.ell(cx, cy, s * rr, s * rr, stroke=col, sw=2.2) if rr > 0.2 else c.ell(cx, cy, s * rr, s * rr, fill=col)
    elif kind == "compass":
        c.ell(cx, cy, s * 0.85, s * 0.85, stroke=col, sw=2.2)
        c.poly([(cx, cy - s * 0.55), (cx + s * 0.22, cy + s * 0.1), (cx, cy + s * 0.55), (cx - s * 0.22, cy + s * 0.1)], col, op=0.9)
    elif kind == "pen":
        c.poly([(cx - s * 0.7, cy + s * 0.7), (cx - s * 0.5, cy + s * 0.2), (cx + s * 0.5, cy - s * 0.7), (cx + s * 0.7, cy - s * 0.5), (cx - s * 0.2, cy + s * 0.5)], None, col, 2.2)
    elif kind == "mic":
        c.rrect(cx - s * 0.28, cy - s * 0.8, s * 0.56, s * 1.0, s * 0.28, stroke=col, sw=2.2)
        c.arc(cx, cy - s * 0.1, s * 0.6, 20, 160, col, 2.2)
        c.poly([(cx, cy + s * 0.5), (cx, cy + s * 0.8)], None, col, 2.2, closed=False)
    elif kind == "check":
        c.ell(cx, cy, s * 0.85, s * 0.85, stroke=col, sw=2.2)
        c.check(cx, cy, s * 0.4, col, 2.6)
    elif kind == "folder":
        c.poly([(cx - s * 0.8, cy - s * 0.5), (cx - s * 0.2, cy - s * 0.5), (cx, cy - s * 0.3), (cx + s * 0.8, cy - s * 0.3), (cx + s * 0.8, cy + s * 0.6), (cx - s * 0.8, cy + s * 0.6)], None, col, 2.2)
    elif kind == "chat":
        c.rrect(cx - s * 0.8, cy - s * 0.6, s * 1.6, s * 1.0, 6, stroke=col, sw=2.2)
        c.poly([(cx - s * 0.3, cy + s * 0.4), (cx - s * 0.5, cy + s * 0.8), (cx, cy + s * 0.4)], None, col, 2.2, closed=False)
    elif kind == "shield":
        c.poly([(cx, cy - s * 0.85), (cx + s * 0.7, cy - s * 0.5), (cx + s * 0.6, cy + s * 0.3), (cx, cy + s * 0.85), (cx - s * 0.6, cy + s * 0.3), (cx - s * 0.7, cy - s * 0.5)], None, col, 2.2)
        c.check(cx, cy, s * 0.3, col, 2.4)
    elif kind == "star":
        pts = [(cx + (s * 0.85 if i % 2 == 0 else s * 0.38) * math.cos(-math.pi / 2 + i * math.pi / 5),
                cy + (s * 0.85 if i % 2 == 0 else s * 0.38) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
        c.poly(pts, col, op=0.95)


def render() -> bytes:
    R._INFO, R._STARTS = [], []
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    page.insert_image(pymupdf.Rect(0, 0, W, H), stream=R.background())
    c = R.Canvas(page)
    for x, y, r, col, op in ((260, 180, 420, "#ffffff", 0.035), (1500, 900, 520, "#ffffff", 0.03), (1800, 120, 300, "#7cc4ff", 0.06), (700, 1000, 260, "#ffcf8a", 0.04)):
        c.ell(x, y, r, r, fill=col, op=op)

    # ---- header
    R.logo(c, 80, 40, 76)
    c.text(176, 86, "AI Career Coach", 50, "#ffffff", True)
    c.text(178, 120, "PLAN  ·  LEARN  ·  CERTIFY", 21, "#9fe0ff", True)
    c.rrect(1500, 56, 340, 50, 25, fill="#ffffff", op=0.12)
    c.text(1670, 89, "Full-stack AI web application", 21, "#ffffff", True, "c")

    # ---- headline
    c.text(80, 218, "From resume to career-ready:", 58, "#ffffff", True)
    c.text(80, 286, "match, learn, practise, certify.", 58, R.AMBER, True)
    sub = ("Upload a resume and a job description for an explainable match score and skill gaps, then follow a personal "
           "7, 15 or 60 day roadmap with assessments and verifiable certificates.")
    for i, ln in enumerate(R.wrap(sub, 25, 1060)):
        c.text(82, 336 + i * 34, ln, 25, "#cfe0ff")

    # ---- real, measured numbers
    stats = [("15", "build phases delivered"), ("588", "backend tests passing"), ("97%", "backend code coverage"), ("6", "browser journeys (Playwright)")]
    for k, (num, lab) in enumerate(stats):
        x, y = 1230 + (k % 2) * 310, 150 + (k // 2) * 118
        tile(c, x, y, 292, 100, "#ffffff", 0.12, 18)
        c.text(x + 22, y + 56, num, 46, R.AMBER, True)
        c.text(x + 22, y + 84, lab, 17, "#e1ebff")

    # ---- main app mock-up
    wx, wy, ww, wh = 80, 408, 1010, 470
    window(c, wx, wy, ww, wh)
    doc_card(c, wx + 28, wy + 62, 456, 170, "RESUME", R.INDIGO)
    doc_card(c, wx + 526, wy + 62, 456, 170, "JOB DESCRIPTION", "#0e7490")
    c.rrect(wx + ww / 2 - 190, wy + 250, 380, 50, 25, fill=R.INDIGO)
    c.text(wx + ww / 2, wy + 283, "Analyse and match", 21, "#ffffff", True, "c")
    ry = wy + 372
    c.ell(wx + 100, ry, 62, 62, fill="#ffffff", stroke="#e2e8f0", sw=2)
    c.arc(wx + 100, ry, 50, 0, 359, "#e2e8f0", 14)
    c.arc(wx + 100, ry, 50, -90, -90 + 360 * 0.86, R.GREEN, 14)
    c.text(wx + 100, ry + 10, "86%", 30, "#0f172a", True, "c")
    for k, (lab, v) in enumerate((("Skills", 0.9), ("Experience", 0.8), ("Keywords", 0.78))):
        by = ry - 38 + k * 38
        c.text(wx + 190, by + 12, lab, 17, "#334155", True)
        c.rrect(wx + 300, by, 260, 14, 7, fill="#e2e8f0")
        c.rrect(wx + 300, by, 260 * v, 14, 7, fill=R.GREEN if v > 0.79 else R.AMBER)
    for k, (name, ok) in enumerate((("Python", True), ("SQL", True), ("Docker", False), ("Cloud", False))):
        cx0, cy0 = wx + 610 + (k % 2) * 190, ry - 40 + (k // 2) * 56
        c.rrect(cx0, cy0, 176, 44, 22, fill="#ffffff", stroke="#e2e8f0", sw=1.5)
        c.ell(cx0 + 24, cy0 + 22, 12, 12, fill=R.GREEN if ok else R.AMBER)
        c.text(cx0 + 46, cy0 + 29, name, 19, "#0f172a", True)
    c.text(wx + ww - 18, wy + wh - 14, "Illustrative data", 14, "#94a3b8", False, "r")

    # ---- right-hand feature cards
    cx0, cw = 1130, 710
    # roadmap
    y0 = 408
    tile(c, cx0, y0, cw, 148)
    c.text(cx0 + 24, y0 + 40, "Personal learning roadmaps", 24, "#0f172a", True)
    for k, (n, on) in enumerate((("7", False), ("15", True), ("60", False))):
        c.rrect(cx0 + 24 + k * 92, y0 + 58, 80, 40, 12, fill=R.INDIGO if on else "#e2e8f0")
        c.text(cx0 + 64 + k * 92, y0 + 86, f"{n} d", 21, "#ffffff" if on else "#475569", True, "c")
    for k in range(6):
        px = cx0 + 330 + k * 60
        if k:
            c.poly([(px - 48, y0 + 100), (px - 12, y0 + 100)], None, R.GREEN if k < 4 else "#cbd5e1", 4, closed=False)
        c.ell(px, y0 + 100, 13, 13, fill=R.GREEN if k < 4 else "#e2e8f0")
        if k < 4:
            c.check(px, y0 + 100, 5, "#ffffff", 2.6)
    c.text(cx0 + 24, y0 + 130, "Skill-gap driven steps, quizzes and projects", 17, "#475569")
    # coach
    y1 = 574
    tile(c, cx0, y1, cw, 148)
    c.text(cx0 + 24, y1 + 40, "AI career coach and mock interviews", 24, "#0f172a", True)
    c.rrect(cx0 + 24, y1 + 56, 330, 32, 16, fill="#e8edf7")
    c.text(cx0 + 40, y1 + 78, "How do I close my Docker gap?", 16, "#0f172a")
    c.rrect(cx0 + 300, y1 + 96, 386, 40, 20, fill=R.INDIGO)
    c.text(cx0 + 318, y1 + 122, "From your resume: start with containers.", 16, "#ffffff")
    # certificates
    y2 = 740
    tile(c, cx0, y2, cw, 148)
    c.text(cx0 + 24, y2 + 40, "Assessments and verifiable certificates", 24, "#0f172a", True)
    c.rrect(cx0 + 24, y2 + 58, 190, 76, 10, fill="#f8fafc", stroke="#c99a2e", sw=2)
    R.logo(c, cx0 + 34, y2 + 64, 24)
    c.text(cx0 + 70, y2 + 84, "Certificate", 14, "#1a2954", True)
    c.text(cx0 + 119, y2 + 108, "Sample Learner", 13, "#475569", False, "c")
    c.text(cx0 + 119, y2 + 126, "SAMPLE", 12, "#b91c1c", True, "c")
    c.ell(cx0 + 270, y2 + 96, 24, 24, fill=R.GREEN)
    c.check(cx0 + 270, y2 + 96, 9, "#ffffff", 4)
    c.text(cx0 + 306, y2 + 90, "Public verification page", 19, "#0f172a", True)
    c.text(cx0 + 306, y2 + 114, "Platform-issued, never accredited", 16, "#475569")

    # ---- feature chips
    feats = [("doc", "Resume analysis"), ("doc", "Job analysis"), ("target", "Match score"), ("compass", "Skill gaps"), ("pen", "Optimiser"),
             ("mic", "Mock interviews"), ("check", "Assessments"), ("folder", "Portfolio"), ("chat", "Testimonials"), ("shield", "Admin audit")]
    widths = [pymupdf.get_text_length(lab, fontname="hebo", fontsize=16) + 62 for _, lab in feats]
    gap = (1760 - sum(widths)) / (len(feats) - 1)
    x = 80.0
    for (kind, lab), cwid in zip(feats, widths):
        c.rrect(x, 902, cwid, 48, 24, fill="#ffffff", op=0.13, stroke="#ffffff", sw=1)
        icon(c, kind, x + 26, 926, 10)
        c.text(x + 46, 932, lab, 16, "#ffffff", True)
        x += cwid + gap

    # ---- tech and security strip
    c.text(80, 1002, "BUILT WITH", 16, "#9fe0ff", True)
    x = 190
    for tech in ("React", "TypeScript", "Tailwind", "FastAPI", "SQLAlchemy", "PostgreSQL", "LangChain", "LangGraph", "ChromaDB", "Groq", "Docker"):
        w = pymupdf.get_text_length(tech, fontname="hebo", fontsize=17) + 28
        c.rrect(x, 980, w, 34, 17, fill="#ffffff", op=0.16)
        c.text(x + w / 2, 1003, tech, 17, "#ffffff", True, "c")
        x += w + 10
    c.text(80, 1050, "Argon2id passwords  ·  short-lived JWT + HttpOnly refresh  ·  consent-gated testimonials  ·  uploads treated as untrusted  ·  no fabricated results",
           17, "#bcd0ff")

    pix = page.get_pixmap(matrix=pymupdf.Matrix(R.SCALE, R.SCALE), alpha=False)
    png = pix.tobytes("png")
    doc.close()
    return png


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    png = render()
    (out / "ai-career-coach-showcase-4k.png").write_bytes(png)
    pix = pymupdf.Pixmap(png)
    pix.shrink(1)
    (out / "ai-career-coach-showcase-1080p.jpg").write_bytes(pix.tobytes("jpg", jpg_quality=92))
    print("wrote", out / "ai-career-coach-showcase-4k.png", f"{len(png) / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
