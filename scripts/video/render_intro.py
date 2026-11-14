"""Render the 30 second AI Career Coach intro video (3840x2160, 30 fps) from vector drawing code.

Everything is drawn locally with PyMuPDF (no stock footage, no external images). The presenter is an
illustrated character whose mouth follows the narration loudness. Narration timing comes from
``narration.py`` (work directory ``timing.json`` and ``lineN.wav``).

Usage:
    python render_intro.py WORK_DIR --stills 1.0 6.0 12.0      # write PNG test frames only
    python render_intro.py WORK_DIR OUT_DIR                    # full render + encode (4K and 1080p)
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import wave
from multiprocessing import Pool
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import pymupdf

W, H, FPS, SCALE = 1920, 1080, 30, 2
LEAD, GAP, TOTAL = 0.25, 0.10, 30.0
NAVY = "#0b1437"
INDIGO = "#4f46e5"
SKY = "#0ea5e9"
AMBER = "#fbbf24"
GREEN = "#34d399"

_BG: bytes | None = None
_INFO: list[dict] = []
_STARTS: list[float] = []


def hexc(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def ease(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


def pop(x: float) -> float:
    """ease-out-back: overshoots slightly, then settles (0..1)."""
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def background() -> bytes:
    global _BG
    if _BG is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        t = (xx / W * 0.55 + yy / H * 0.45)
        c0, c1, c2 = np.array(hexc(NAVY)), np.array(hexc("#2a2a8f")), np.array(hexc("#0b6aa8"))
        img = np.where(t[..., None] < 0.55, c0 + (c1 - c0) * (t[..., None] / 0.55), c1 + (c2 - c1) * ((t[..., None] - 0.55) / 0.45))
        d2 = ((xx - W * 0.45) / (W * 0.75)) ** 2 + ((yy - H * 0.5) / (H * 0.8)) ** 2
        img *= (1 - 0.42 * np.clip(d2, 0, 1))[..., None]  # cinematic vignette
        img += (np.random.default_rng(1).random((H, W, 1), dtype=np.float32) - 0.5) / 120  # dither against banding
        arr = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        pix = pymupdf.Pixmap(pymupdf.csRGB, W, H, arr.tobytes(), False)
        _BG = pix.tobytes("png")
    return _BG



def catmull(pts, closed=True, n=8):
    """Dense points of a Catmull-Rom spline through ``pts`` (smooth organic outlines)."""
    P = list(pts)
    m = len(P)
    out = []
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        p0, p1, p2, p3 = (P[(i - 1) % m], P[i], P[(i + 1) % m], P[(i + 2) % m]) if closed else (
            P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, m - 1)])
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    if not closed:
        out.append(tuple(P[-1]))
    return out


class Canvas:
    """Thin drawing layer with a global alpha and offset (used for scene fades and slides)."""

    def __init__(self, page: pymupdf.Page):
        self.p, self.a, self.dx, self.dy = page, 1.0, 0.0, 0.0

    def _pt(self, x: float, y: float) -> pymupdf.Point:
        return pymupdf.Point(x + self.dx, y + self.dy)

    def poly(self, pts, fill=None, stroke=None, sw=1.0, op=1.0, closed=True, round_cap=True) -> None:
        if self.a * op <= 0.003:
            return
        sh = self.p.new_shape()
        sh.draw_polyline([self._pt(*q) for q in pts])
        sh.finish(fill=hexc(fill) if fill else None, color=hexc(stroke) if stroke else None, width=sw,
                  closePath=closed, lineCap=1 if round_cap else 0, lineJoin=1,
                  fill_opacity=op * self.a, stroke_opacity=op * self.a)
        sh.commit()

    def smooth(self, pts, fill=None, stroke=None, sw=1.0, op=1.0, closed=True) -> None:
        self.poly(catmull(pts, closed), fill, stroke, sw, op, closed=closed)

    def rrect(self, x, y, w, h, r=0, fill=None, stroke=None, sw=1.0, op=1.0) -> None:
        r = min(r, w / 2, h / 2)
        if r <= 0:
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        else:
            pts = []
            for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
                for k in range(9):
                    a = math.radians(a0 + 90 * k / 8)
                    pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.poly(pts, fill, stroke, sw, op)

    def ell(self, cx, cy, rx, ry, fill=None, stroke=None, sw=1.0, op=1.0) -> None:
        n = 48
        pts = [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self.poly(pts, fill, stroke, sw, op)

    def arc(self, cx, cy, r, a0, a1, stroke, sw, op=1.0) -> None:
        n = max(2, int(abs(a1 - a0) / 4))
        pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]
        self.poly(pts, None, stroke, sw, op, closed=False)

    def text(self, x, y, s, size, color="#ffffff", bold=False, align="l", op=1.0) -> None:
        if self.a * op <= 0.003:
            return
        font = "hebo" if bold else "helv"
        w = pymupdf.get_text_length(s, fontname=font, fontsize=size)
        x0 = x - (w / 2 if align == "c" else w if align == "r" else 0)
        self.p.insert_text(self._pt(x0, y), s, fontsize=size, fontname=font, color=hexc(color), fill_opacity=op * self.a)

    def check(self, cx, cy, s, color="#ffffff", sw=4.0, op=1.0) -> None:
        self.poly([(cx - s, cy), (cx - s * 0.3, cy + s * 0.7), (cx + s, cy - s * 0.7)], None, color, sw, op, closed=False)


def logo(c: Canvas, x: float, y: float, size: float, op: float = 1.0) -> None:
    """Brand mark drawn from the same geometry as frontend/public/logo.svg (64 unit box)."""
    k = size / 64

    def P(px, py):
        return (x + px * k, y + py * k)

    c.rrect(x, y, size, size, 16 * k, fill="#2563eb", op=op)
    arc = [P(32 + 17 * math.cos(math.radians(a)), 32 + 17 * math.sin(math.radians(a))) for a in np.linspace(45, 315, 60)]
    c.poly(arc, None, "#ffffff", 6 * k, op, closed=False)
    c.poly([P(23, 40), P(30, 33), P(35, 37), P(46, 25)], None, AMBER, 3.6 * k, op, closed=False)
    c.poly([P(40, 24.5), P(46.5, 24.5), P(46.5, 31)], None, AMBER, 3.6 * k, op, closed=False)
    c.ell(*P(50, 14), 2.2 * k, 2.2 * k, fill="#ffffff", op=op * 0.9)


# ------------------------------------------------------------------ presenter
SKIN, SKIN_D, SKIN_L = "#cf9670", "#a9704d", "#f0c4a0"
HAIR, HAIR_L = "#120a14", "#5a4a7a"
SUIT, SUIT_L, SUIT_D = "#2c3b6b", "#40508c", "#1b2650"
LIP = "#b8485c"


def presenter(c: Canvas, t: float, env: float) -> None:
    hx, hy = 1540, 488
    bob = math.sin(t * 1.3) * 3.5 + env * 2.5
    sway = math.sin(t * 0.7) * 3

    def R(*pts):
        return [(hx + x, hy + y) for x, y in pts]

    def mir(pts):
        return [(-x, y) for x, y in pts]

    # --- cinematic set: warm key glow, soft bokeh lights (out of focus), cool rim glow
    c.dy = 0
    c.ell(hx - 40, hy + 40, 330, 400, fill="#ffb86b", op=0.07)
    c.ell(hx, hy + 60, 250, 330, fill="#ffd9a8", op=0.06)
    for k, (bx, by, br, col, op) in enumerate(((1290, 250, 70, "#ffcf8a", 0.14), (1830, 210, 90, "#7cc4ff", 0.13), (1760, 760, 56, "#ffcf8a", 0.12),
                                               (1250, 620, 40, "#9fd3ff", 0.14), (1870, 520, 48, "#ffd9a8", 0.12), (1420, 110, 46, "#9fd3ff", 0.12))):
        c.ell(bx + math.sin(t * 0.5 + k) * 12, by + math.cos(t * 0.4 + k) * 9, br, br, fill=col, op=op)
    c.dy = bob
    c.dx = sway * 0.4

    # --- hair behind head/shoulders
    c.smooth(R((-135, -110), (-100, -162), (-40, -188), (30, -190), (100, -165), (140, -110), (152, -20), (160, 90), (170, 200),
               (150, 300), (70, 335), (-70, 335), (-150, 300), (-170, 200), (-160, 90), (-152, -20)), fill=HAIR)
    # --- neck
    c.poly(R((-40, 90), (40, 90), (46, 292), (-46, 292)), fill=SKIN)
    c.poly(R((8, 100), (40, 100), (46, 292), (14, 292)), fill=SKIN_D, op=0.35)          # shade side of neck
    c.ell(hx, hy + 150, 46, 30, fill=SKIN_D, op=0.55)                                    # shadow under chin
    # --- tailored suit jacket
    body = R((-310, 600), (-298, 430), (-262, 335), (-185, 296), (-62, 276), (62, 276), (185, 296), (262, 335), (298, 430), (310, 640))
    c.smooth(body, fill=SUIT)
    c.poly(R((-310, 600), (-298, 430), (-262, 335), (-200, 305), (-190, 600)), fill=SUIT_L, op=0.35)   # key light on the left shoulder
    c.poly(R((62, 276), (185, 296), (262, 335), (298, 430), (310, 600), (200, 600)), fill=SUIT_D, op=0.45)  # shadow side
    # white shirt + collar
    c.poly(R((-58, 272), (58, 272), (0, 392)), fill="#f6f4ef")
    c.poly(R((-8, 296), (58, 270), (92, 300), (40, 336)), fill="#ffffff")
    c.poly(R((8, 296), (-58, 270), (-92, 300), (-40, 336)), fill="#ffffff")
    c.poly(R((-58, 272), (-8, 296), (0, 392)), fill="#e2dfd6", op=0.6)
    # lapels with notch
    lap = [(-64, 268), (-106, 286), (-126, 350), (-100, 372), (-30, 470), (-2, 392)]
    c.poly(R(*lap), fill=SUIT_L)
    c.poly(R(*mir(lap)), fill=SUIT)
    c.poly(R((-2, 392), (2, 392), (3, 600), (-3, 600)), fill=SUIT_D, op=0.5)
    c.ell(hx - 2, hy + 500, 7, 7, fill="#10183a")                                         # button
    c.ell(hx - 96, hy + 378, 7, 7, fill="#e8b84a")                                        # lapel pin
    c.poly(R((-4, 296), (-1, 330), (-2, 392), (2, 392), (5, 330), (8, 296)), fill=SKIN, op=0)
    # delicate gold necklace and pendant
    c.smooth(R((-40, 292), (-26, 330), (0, 352), (26, 330), (40, 292)), stroke="#e8b84a", sw=2.4, closed=False)
    c.ell(hx, hy + 358, 6, 8, fill="#f2c85a")
    # --- hair locks falling over the shoulders (glossy)
    left = [(-112, 70), (-126, 140), (-140, 210), (-146, 270), (-122, 322), (-98, 306), (-94, 240), (-98, 160), (-96, 90)]
    right = [(112, 70), (122, 135), (132, 200), (136, 255), (118, 300), (94, 290), (92, 236), (94, 160), (96, 90)]
    c.smooth(R(*left), fill=HAIR)
    c.smooth(R(*right), fill=HAIR)
    c.smooth(R((-116, 100), (-128, 190), (-134, 250)), stroke=HAIR_L, sw=5, op=0.5, closed=False)
    c.smooth(R((112, 100), (122, 180), (126, 250)), stroke="#8fb8ff", sw=3, op=0.35, closed=False)   # cool rim light
    # --- face: slender oval with a defined jaw
    face = [(0, -150), (58, -134), (104, -88), (116, -22), (104, 46), (78, 100), (42, 134), (0, 146),
            (-42, 134), (-78, 100), (-104, 46), (-116, -22), (-104, -88), (-58, -134)]
    c.smooth(R(*face), fill=SKIN)
    c.smooth(R((58, -120), (106, -64), (114, -18), (102, 48), (76, 100), (44, 134), (52, 80), (78, 10), (84, -60)), fill=SKIN_D, op=0.22)  # contour
    c.ell(hx - 52, hy + 20, 34, 46, fill=SKIN_L, op=0.14)                                 # cheek highlight
    c.ell(hx - 6, hy - 92, 58, 26, fill=SKIN_L, op=0.14)                                  # forehead highlight
    c.ell(hx - 66, hy + 62, 30, 17, fill="#e0786c", op=0.26)                              # blush
    c.ell(hx + 66, hy + 62, 30, 17, fill="#e0786c", op=0.22)
    c.ell(hx, hy + 120, 20, 8, fill=SKIN_L, op=0.12)                                      # chin highlight
    # --- front hair: soft side parting sweeping across the forehead
    front = [(-110, 50), (-118, -60), (-100, -134), (-46, -172), (28, -178), (96, -152), (124, -90), (122, 50),
             (108, -22), (86, -84), (42, -120), (-10, -126), (-58, -102), (-92, -46), (-100, 14)]
    c.smooth(R(*front), fill=HAIR)
    c.smooth(R((-90, -130), (-40, -160), (30, -164), (88, -138)), stroke=HAIR_L, sw=6, op=0.45, closed=False)
    c.smooth(R((-60, -110), (-10, -138), (50, -126)), stroke=HAIR_L, sw=3, op=0.35, closed=False)
    # --- eyes: almond shape, iris, lashes, soft eyeshadow, blinking every ~3.4 s
    blink = 0.1 if (t % 3.4) < 0.13 else 1.0
    for sx in (-1, 1):
        ex, ey = hx + sx * 42, hy + 2
        c.ell(ex, ey - 16, 28, 11, fill="#b0705f", op=0.22)                                 # eyeshadow
        sclera = [(-24, 3), (-12, -8 * blink), (3, -11 * blink), (15, -7 * blink), (24, 2), (12, 9 * blink), (-4, 11 * blink), (-16, 7 * blink)]
        c.smooth([(ex + sx * x, ey + y) for x, y in sclera], fill="#fbf8f4")
        if blink > 0.4:
            c.ell(ex + sx * 1, ey + 0.5, 9.2, 9.2 * blink, fill="#4a2a1a")
            c.ell(ex + sx * 1, ey + 0.5, 5.2, 5.2 * blink, fill="#150a06")
            c.ell(ex + sx * 1 - 3, ey - 3.5, 2.6, 2.6, fill="#ffffff")
            c.ell(ex + sx * 1 + 3.5, ey + 3, 1.3, 1.3, fill="#ffffff", op=0.8)
        top = [(ex + sx * x, ey + y) for x, y in ((-25, 4), (-13, -9 * blink - 2), (3, -12 * blink - 2), (16, -9 * blink - 1), (27, -2))]
        c.smooth(top, stroke="#120a14", sw=3.6, closed=False)
        c.poly([(ex + sx * 26, ey - 3), (ex + sx * 35, ey - 9), (ex + sx * 29, ey + 1)], fill="#120a14")   # lash flick
        c.smooth([(ex + sx * x, ey + y) for x, y in ((-20, 8), (-4, 11 * blink), (14, 8))], stroke=SKIN_D, sw=1.6, op=0.6, closed=False)
        brow_top = [(-30, -26), (-10, -39), (16, -38), (32, -26)]
        brow_bot = [(32, -24), (16, -33), (-10, -33), (-30, -21)]
        c.poly([(ex + sx * x + sx * 2, ey - 4 + y) for x, y in brow_top + brow_bot], fill="#1a0f14", op=0.92)
    # nose
    c.smooth(R((6, -2), (12, 40), (22, 62)), stroke=SKIN_D, sw=3.2, op=0.45, closed=False)
    c.poly(R((-16, 62), (-7, 66), (-9, 60)), fill=SKIN_D, op=0.9)
    c.poly(R((16, 62), (7, 66), (9, 60)), fill=SKIN_D, op=0.9)
    c.ell(hx - 2, hy + 56, 6, 4, fill=SKIN_L, op=0.3)
    c.ell(hx, hy - 52, 4.6, 4.6, fill="#8d1d34")                                          # small bindi
    # --- lips follow the narration loudness
    o = clamp(env)
    my = hy + 96
    opn = o * 22
    inner = [(-24, 0), (-12, -2), (0, -2), (12, -2), (24, 0), (15, opn + 5), (0, opn + 7), (-15, opn + 5)]
    c.smooth([(hx + x, my + y) for x, y in inner], fill="#3a0a16")
    if o > 0.18:
        c.poly([(hx - 15, my - 1), (hx + 15, my - 1), (hx + 13, my + opn * 0.4 + 3), (hx - 13, my + opn * 0.4 + 3)], fill="#fbf7f2")
    upper = [(-28, 1), (-15, -8), (-5, -11), (0, -8), (5, -11), (15, -8), (28, 1), (15, -1), (0, -2), (-15, -1)]
    lower = [(-26, 1), (-14, opn + 3), (0, opn + 5), (14, opn + 3), (26, 1), (15, opn + 15), (0, opn + 20), (-15, opn + 15)]
    c.smooth([(hx + x, my + y) for x, y in lower], fill="#c4566a")
    c.smooth([(hx + x, my + y) for x, y in upper], fill=LIP)
    c.ell(hx - 4, my + opn + 11, 9, 2.6, fill="#ffd9e0", op=0.5)                         # gloss
    # rim light along the right shoulder, jaw and hair
    c.smooth(R((185, 296), (262, 335), (298, 430)), stroke="#8fb8ff", sw=4, op=0.45, closed=False)
    c.smooth(R((104, 46), (80, 98), (44, 133)), stroke="#ffe2c8", sw=2.4, op=0.35, closed=False)
    c.dy = 0
    c.dx = 0
    c.rrect(1355, 1000, 370, 56, 28, fill=NAVY, op=0.85)
    c.text(hx, 1036, "Your AI Career Coach guide", 27, "#ffffff", True, "c")


# ------------------------------------------------------------------ scenes
def title(c: Canvas, s: str, sub: str | None = None) -> None:
    c.text(110, 190, s, 58, "#ffffff", True)
    if sub:
        c.text(112, 232, sub, 24, "#bcd0ff")


def scene_intro(c: Canvas, lt: float, d: float) -> None:
    p = pop(lt / 0.7)
    c.dy = (1 - ease(lt / 0.7)) * 40
    logo(c, 110, 300, 230 * p)
    c.text(400, 420, "AI Career", 112, "#ffffff", True)
    c.text(400, 535, "Coach", 112, "#ffffff", True)
    c.text(404, 610, "PLAN  ·  LEARN  ·  CERTIFY", 36, "#9fe0ff", True, op=ease((lt - 0.8) / 0.6))
    for k, (x, y, r) in enumerate(((880, 280, 7), (1010, 360, 5), (920, 700, 6), (1100, 520, 4))):
        c.ell(x, y + math.sin(lt * 2 + k) * 8, r, r, fill=AMBER, op=0.7)
    c.dy = 0


def doc(c: Canvas, x: float, y: float, w: float, h: float, label: str, color: str, op: float) -> None:
    c.rrect(x, y, w, h, 20, fill="#ffffff", op=0.97 * op)
    c.rrect(x, y, w, 56, 20, fill=color, op=op)
    c.rrect(x, y + 30, w, 26, 0, fill=color, op=op)
    c.text(x + 24, y + 38, label, 22, "#ffffff", True, op=op)
    for k, ln in enumerate((0.85, 0.7, 0.9, 0.6, 0.8, 0.5, 0.75)):
        c.rrect(x + 24, y + 90 + k * 38, (w - 48) * ln, 12, 6, fill="#cbd5e1", op=op)


def scene_match(c: Canvas, lt: float, d: float) -> None:
    title(c, "Match score and skill gaps", "Example result, for illustration only")
    for x, label, col, t0 in ((110, "RESUME", INDIGO, 0.2), (440, "JOB DESCRIPTION", "#0e7490", 0.5)):
        p = pop((lt - t0) / 0.5)
        c.dy = (1 - ease((lt - t0) / 0.5)) * 50
        doc(c, x, 270, 300, 340, label, col, ease((lt - t0) / 0.4))
        c.dy = 0
    for k in range(3):
        c.poly([(780 + k * 26, 420), (796 + k * 26, 440), (780 + k * 26, 460)], None, "#ffffff", 6, op=ease((lt - 1.0 - k * 0.12) / 0.3) * 0.8, closed=False)
    cx, cy, r = 1010, 440, 115
    ro = ease((lt - 1.0) / 0.4)
    c.ell(cx, cy, r + 28, r + 28, fill="#ffffff", op=0.96 * ro)
    c.arc(cx, cy, r, 0, 359, "#e2e8f0", 26, ro)
    prog = ease((lt - 1.3) / 1.4)
    if prog > 0.01:
        c.arc(cx, cy, r, -90, -90 + 360 * 0.86 * prog, GREEN, 26)
    c.text(cx, cy + 22, f"{round(86 * prog)}%", 72, "#0f172a", True, "c", op=ro)
    c.text(cx, cy + 62, "MATCH", 20, "#64748b", True, "c", op=ro)
    chips = [("Python", True), ("SQL", True), ("Docker", False), ("Cloud", False)]
    for k, (name, ok) in enumerate(chips):
        t0 = 2.7 + k * 0.45
        p = pop((lt - t0) / 0.4)
        if p <= 0:
            continue
        x = 110 + k * 262
        c.dy = (1 - ease((lt - t0) / 0.4)) * 30
        c.rrect(x, 690, 240, 84, 42, fill="#ffffff", op=0.96 * ease((lt - t0) / 0.3))
        c.ell(x + 44, 732, 22, 22, fill=GREEN if ok else AMBER, op=ease((lt - t0) / 0.3))
        if ok:
            c.check(x + 44, 732, 9, "#ffffff", 4.5, ease((lt - t0) / 0.3))
        else:
            c.rrect(x + 41, 718, 6, 17, 3, fill="#ffffff", op=ease((lt - t0) / 0.3))
            c.ell(x + 44, 745, 3.4, 3.4, fill="#ffffff", op=ease((lt - t0) / 0.3))
        c.text(x + 80, 726, name, 28, "#0f172a", True, op=ease((lt - t0) / 0.3))
        c.text(x + 80, 757, "matched" if ok else "gap to close", 19, "#16a34a" if ok else "#b45309", op=ease((lt - t0) / 0.3))
        c.dy = 0


def scene_roadmap(c: Canvas, lt: float, d: float) -> None:
    title(c, "A roadmap made for you", "Choose 7, 15 or 60 days")
    active = min(2, int(lt / (d / 3)))
    for k, (num, x) in enumerate((("7", 110), ("15", 410), ("60", 710))):
        t0 = 0.15 + k * 0.18
        c.dy = (1 - ease((lt - t0) / 0.5)) * 40
        on = k == active
        c.rrect(x, 260, 270, 150, 28, fill="#ffffff" if on else "#ffffff", op=(0.97 if on else 0.14) * ease((lt - t0) / 0.4))
        c.text(x + 135, 350, num, 80, NAVY if on else "#ffffff", True, "c", op=ease((lt - t0) / 0.4))
        c.text(x + 135, 392, "days", 26, "#475569" if on else "#cfe0ff", False, "c", op=ease((lt - t0) / 0.4))
        c.dy = 0
    y0, labels = 640, ("Learn", "Practise", "Quiz", "Project", "Certificate")
    c.poly([(150, y0), (1030, y0)], None, "#ffffff", 8, 0.25, closed=False)
    prog = ease((lt - 0.8) / (d - 1.2))
    c.poly([(150, y0), (150 + 880 * prog, y0)], None, GREEN, 8, closed=False)
    for k, lab in enumerate(labels):
        x = 150 + k * 220
        done = prog >= k / 4 - 0.001
        c.ell(x, y0, 30, 30, fill="#ffffff" if done else NAVY, stroke=GREEN if done else "#ffffff", sw=5, op=0.97)
        if done and k < 4:
            c.check(x, y0, 11, GREEN, 5)
        if k == 4:
            c.ell(x, y0, 30, 30, fill=AMBER if done else NAVY, stroke="#ffffff", sw=4)
        c.text(x, y0 + 76, lab, 25, "#ffffff", True, "c", op=0.92)


def bubble(c, x, y, w, h, lines, fill, color, op, right=False) -> None:
    c.rrect(x, y, w, h, 30, fill=fill, op=op)
    for i, ln in enumerate(lines):
        c.text(x + 30, y + 52 + i * 40, ln, 30, color, False, op=op)


def scene_coach(c: Canvas, lt: float, d: float) -> None:
    title(c, "Interview practice and coach", "Answers grounded in your own documents")
    c.rrect(110, 250, 960, 600, 36, fill="#ffffff", op=0.97)
    c.rrect(110, 250, 960, 84, 36, fill="#eef2ff")
    c.rrect(110, 300, 960, 34, 0, fill="#eef2ff")
    logo(c, 138, 266, 52)
    c.text(206, 306, "AI Career Coach", 30, "#1e1b4b", True)
    c.ell(1010, 292, 9, 9, fill=GREEN)
    t0 = 0.4
    if lt > t0:
        o = ease((lt - t0) / 0.3)
        c.dy = (1 - o) * 20
        bubble(c, 330, 370, 700, 76, ["How do I close my skill gaps?"], INDIGO, "#ffffff", o)
        c.dy = 0
    if 1.0 < lt < 1.6:  # typing dots
        for k in range(3):
            c.ell(160 + k * 34, 500 + math.sin(lt * 9 + k) * 6, 8, 8, fill="#94a3b8")
    if lt > 1.6:
        o = ease((lt - 1.6) / 0.3)
        c.dy = (1 - o) * 20
        bubble(c, 140, 470, 760, 120, ["From your resume: start with", "Docker and SQL basics."], "#e8edf7", "#0f172a", o)
        c.dy = 0
    if lt > 2.9:
        o = ease((lt - 2.9) / 0.3)
        c.dy = (1 - o) * 20
        bubble(c, 140, 625, 700, 76, ["Ready for a mock interview?"], "#e8edf7", "#0f172a", o)
        c.rrect(140, 725, 300, 64, 32, fill=GREEN, op=o)
        c.text(290, 766, "Start practising", 26, "#052e16", True, "c", op=o)
        c.dy = 0


def scene_cert(c: Canvas, lt: float, d: float) -> None:
    title(c, "Certificates you can verify", "Sample shown, not a real certificate")
    o = ease(lt / 0.5)
    c.dy = (1 - o) * 50
    x, y, w, h = 150, 250, 880, 560
    c.rrect(x, y, w, h, 18, fill="#ffffff", op=0.98 * o)
    c.rrect(x + 16, y + 16, w - 32, h - 32, 10, stroke="#c99a2e", sw=3, op=o)
    logo(c, x + w / 2 - 34, y + 40, 68, o)
    c.text(x + w / 2, y + 160, "CERTIFICATE OF LEARNING COMPLETION", 28, "#1a2954", True, "c", op=o)
    c.text(x + w / 2, y + 245, "Sample Learner", 62, "#1a2954", True, "c", op=o)
    c.text(x + w / 2, y + 300, "has successfully completed the roadmap", 24, "#475569", False, "c", op=o)
    rng = np.random.default_rng(7)
    for r_ in range(9):
        for k in range(9):
            if rng.random() > 0.5 or (r_ < 3 and k < 3):
                c.rrect(x + 70 + k * 14, y + 380 + r_ * 14, 12, 12, 1, fill="#0f172a", op=o)
    c.text(x + w / 2, y + 450, "Certificate ID printed here", 22, "#475569", False, "c", op=o)
    c.text(x + w / 2, y + 486, "SAMPLE", 30, "#b91c1c", True, "c", op=o * 0.8)
    c.dy = 0
    v = pop((lt - 1.9) / 0.5)
    if v > 0:
        cx, cy = 930, 740
        c.ell(cx, cy, 70 * v, 70 * v, fill=GREEN, stroke="#ffffff", sw=8)
        c.check(cx, cy, 28 * v, "#ffffff", 11)
        c.rrect(cx - 120, cy + 90, 240, 56, 28, fill="#ffffff", op=0.97 * ease((lt - 2.2) / 0.3))
        c.text(cx, cy + 128, "Verified online", 26, "#0f172a", True, "c", op=ease((lt - 2.2) / 0.3))


def scene_cta(c: Canvas, lt: float, d: float) -> None:
    p = pop(lt / 0.6)
    logo(c, 110, 140, 130 * p)
    c.text(110, 400, "Your next job", 104, "#ffffff", True, op=ease(lt / 0.5))
    c.text(110, 510, "begins here", 104, AMBER, True, op=ease((lt - 0.25) / 0.5))
    pulse = 1 + 0.03 * math.sin(lt * 6)
    bw, bh = 360 * pulse, 110 * pulse
    c.rrect(110, 620 - (bh - 110) / 2, bw, bh, bh / 2, fill=AMBER, op=ease((lt - 0.7) / 0.4))
    c.text(110 + bw / 2, 691, "Start free", 50, NAVY, True, "c", op=ease((lt - 0.7) / 0.4))
    c.text(112, 790, "No account needed to try the analysis.", 32, "#d8e4ff", op=ease((lt - 1.2) / 0.5))


SCENES = (scene_intro, scene_match, scene_roadmap, scene_coach, scene_cert, scene_cta)


def timeline(info: list[dict]) -> list[float]:
    starts, t = [], LEAD
    for item in info:
        starts.append(t)
        t += item["duration"] + GAP
    return starts


def wrap(text: str, size: float, width: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if pymupdf.get_text_length(trial, fontname="helv", fontsize=size) > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


def envelope(t: float) -> float:
    for i, item in enumerate(_INFO):
        lt = t - _STARTS[i]
        if 0 <= lt < item["duration"]:
            env = item["env"]
            j = min(len(env) - 1, int(lt * 60))
            return float(np.mean(env[max(0, j - 2):j + 1]))
    return 0.0


def render_frame(t: float) -> bytes:
    doc_ = pymupdf.open()
    page = doc_.new_page(width=W, height=H)
    page.insert_image(pymupdf.Rect(0, 0, W, H), stream=background())
    c = Canvas(page)
    for k, (x, y, r, sp) in enumerate(((300, 200, 420, 0.3), (1100, 900, 520, 0.2), (1700, 100, 300, 0.4))):
        c.ell(x + math.sin(t * sp + k) * 40, y + math.cos(t * sp) * 30, r, r, fill="#ffffff", op=0.035)
    # active scene
    idx = max(i for i, s in enumerate(_STARTS) if t >= s - 0.2) if t >= _STARTS[0] - 0.2 else 0
    for i in {idx, idx - 1}:
        if i < 0:
            continue
        start = _STARTS[i]
        end = start + _INFO[i]["duration"] + GAP
        a_in = ease((t - (start - 0.2)) / 0.35)
        a_out = 1.0 if i == len(SCENES) - 1 else 1 - ease((t - end + 0.05) / 0.3)
        a = a_in * a_out
        if a <= 0.003:
            continue
        c.a, c.dy, c.dx = a, 0, (1 - a) * 30 if t < end else -(1 - a) * 30
        if i not in (0, len(SCENES) - 1):
            logo(c, 110, 52, 44)
            c.text(166, 86, "AI Career Coach", 28, "#dbe6ff", True)
        SCENES[i](c, max(0.0, t - start), _INFO[i]["duration"])
    c.a, c.dx, c.dy = 1.0, 0, 0
    presenter(c, t, envelope(t))
    # caption for the current line
    for i, item in enumerate(_INFO):
        lt = t - _STARTS[i]
        if -0.05 <= lt < item["duration"] + GAP:
            lines = wrap(item["text"], 36, 1075)
            bh = 30 + 48 * len(lines)
            c.a = ease((lt + 0.05) / 0.2)
            c.rrect(90, 1000 - bh + 40, 1120, bh, 24, fill="#050a1f", op=0.72)
            for j, ln in enumerate(lines):
                c.text(125, 1000 - bh + 40 + 56 + j * 48 - 8, ln, 36, "#ffffff")
            c.a = 1.0
    c.rrect(0, H - 8, W * clamp(t / TOTAL), 8, 0, fill=AMBER, op=0.9)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(SCALE, SCALE), alpha=False)
    out = pix.samples
    doc_.close()
    return out


def init(work: str) -> None:
    global _INFO, _STARTS
    _INFO = json.loads((Path(work) / "timing.json").read_text(encoding="utf-8"))
    _STARTS = timeline(_INFO)


def mix_audio(work: Path, out: Path) -> None:
    sr = 44100
    buf = np.zeros(int(TOTAL * sr) + sr, dtype=np.float32)
    for i, start in enumerate(_STARTS):
        with wave.open(str(work / f"line{i}.wav")) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        s = int(start * sr)
        buf[s:s + len(pcm)] += pcm
    buf = buf[: int(TOTAL * sr)] * 0.95
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(buf, -1, 1) * 32767).astype(np.int16).tobytes())


def vtt(out: Path) -> None:
    def fmt(s: float) -> str:
        return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"

    rows = ["WEBVTT", ""]
    for i, item in enumerate(_INFO):
        rows += [str(i + 1), f"{fmt(_STARTS[i])} --> {fmt(_STARTS[i] + item['duration'])}", item["text"], ""]
    out.write_text("\n".join(rows), encoding="utf-8")


def main(argv: list[str]) -> int:
    work = Path(argv[0])
    init(str(work))
    if len(argv) > 1 and argv[1] == "--stills":
        for s in argv[2:]:
            png = Path(work) / f"still_{float(s):05.2f}.png"
            pix = pymupdf.Pixmap(pymupdf.csRGB, W * SCALE, H * SCALE, render_frame(float(s)), False)
            pix.save(str(png))
            print("wrote", png)
        return 0
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    mix_audio(work, work / "narration.wav")
    vtt(out / "ai-career-coach-intro.vtt")
    frames = int(TOTAL * FPS)
    cmd4k = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W * SCALE}x{H * SCALE}", "-r", str(FPS),
             "-i", "-", "-i", str(work / "narration.wav"), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(TOTAL), str(out / "ai-career-coach-intro-4k.mp4")]
    proc = subprocess.Popen(cmd4k, stdin=subprocess.PIPE)
    with Pool(max(1, (__import__("os").cpu_count() or 2) - 1), initializer=init, initargs=(str(work),)) as pool:
        for n, raw in enumerate(pool.imap(render_frame, [k / FPS for k in range(frames)], chunksize=2)):
            assert proc.stdin is not None
            proc.stdin.write(raw)
            if n % 60 == 0:
                print(f"frame {n}/{frames}", flush=True)
            if n == int(5 * FPS):  # poster frame
                pymupdf.Pixmap(pymupdf.csRGB, W * SCALE, H * SCALE, raw, False).save(str(out / "ai-career-coach-intro-poster.png"))
    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait()
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(out / "ai-career-coach-intro-4k.mp4"), "-vf", "scale=1920:1080:flags=lanczos",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", str(out / "ai-career-coach-intro-1080p.mp4")], check=True)
    print("done", out)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
