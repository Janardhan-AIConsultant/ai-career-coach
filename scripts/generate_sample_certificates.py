"""Render three SAMPLE certificate images for the public Verify page.

They use the real certificate renderer so they look like the genuine PDF, but every one carries a large
"SAMPLE" watermark, a placeholder learner name and a certificate ID that is not in the valid ID format
(so it can never verify). They are illustrations, not issued certificates.

Usage (from ``backend/``): python ../scripts/generate_sample_certificates.py
Output: frontend/public/samples/certificate-*.png
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import pymupdf  # noqa: E402

from app.services.certificate_pdf import CertificateData, render_certificate  # noqa: E402

OUT = ROOT / "frontend" / "public" / "samples"
ISSUED = datetime(2026, 1, 15)
SAMPLES = [
    ("certificate-learning.png", "learning_completion", "Backend Engineering Roadmap (15 days)", 100.0),
    ("certificate-assessment.png", "assessment", "Python Essentials Assessment", 86.0),
    ("certificate-project.png", "project_completion", "REST API Capstone Project", 82.0),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (name, kind, topic, score) in enumerate(SAMPLES, 1):
        pdf = render_certificate(CertificateData(
            code=f"SAMPLE-NOT-VALID-{i}", certificate_type=kind, title=topic, topic=topic,
            learner_name="Sample Learner", issued_at=ISSUED, score=score if kind != "learning_completion" else None,
            verification_url="https://example.invalid/sample-certificate"))
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        page = doc[0]
        centre = pymupdf.Point(421, 300)
        page.insert_text(pymupdf.Point(150, 340), "SAMPLE", fontsize=150, fontname="helv", color=(0.55, 0.1, 0.1),
                         fill_opacity=0.16, morph=(centre, pymupdf.Matrix(-25)))
        page.insert_textbox(pymupdf.Rect(60, 538, 782, 558), "SAMPLE ONLY - not a real certificate and cannot be verified",
                            fontsize=11, fontname="helv", color=(0.55, 0.1, 0.1), align=1)
        page.get_pixmap(dpi=110).save(OUT / name)
        doc.close()
        print("wrote", OUT / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
