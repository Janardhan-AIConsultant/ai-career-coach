"""Render a structured ``ReportDoc`` to PDF (PyMuPDF Story) or DOCX (python-docx).

All text is HTML-escaped before it reaches the PDF engine, so user-controlled text (resume lines,
skill names) cannot inject markup. Errors are wrapped in ``ReportGenerationError``.
"""

from __future__ import annotations

import html
import io
from dataclasses import dataclass, field

import pymupdf
from docx import Document

from app.core.exceptions import ReportGenerationError


@dataclass
class Section:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    table: list[list[str]] | None = None  # first row is the header


@dataclass
class ReportDoc:
    title: str
    disclaimer: str | None = None
    sections: list[Section] = field(default_factory=list)


_CSS = """
body { font-family: sans-serif; font-size: 10pt; }
h1 { font-size: 20pt; margin-bottom: 4pt; }
h2 { font-size: 13pt; margin-top: 14pt; margin-bottom: 4pt; }
p.note { color: #555555; font-size: 9pt; }
td, th { border: 1px solid #999999; padding: 3pt; font-size: 9pt; }
th { background-color: #eeeeee; }
li { margin-bottom: 2pt; }
"""


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _to_html(doc: ReportDoc) -> str:
    out = [f"<h1>{_e(doc.title)}</h1>"]
    if doc.disclaimer:
        out.append(f'<p class="note">{_e(doc.disclaimer)}</p>')
    for s in doc.sections:
        out.append(f"<h2>{_e(s.heading)}</h2>")
        out += [f"<p>{_e(p)}</p>" for p in s.paragraphs]
        if s.bullets:
            out.append("<ul>" + "".join(f"<li>{_e(b)}</li>" for b in s.bullets) + "</ul>")
        if s.table:
            head, *rows = s.table
            out.append("<table><tr>" + "".join(f"<th>{_e(c)}</th>" for c in head) + "</tr>")
            out += ["<tr>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>" for r in rows]
            out.append("</table>")
    return "<html><body>" + "".join(out) + "</body></html>"


def render_pdf(doc: ReportDoc) -> bytes:
    try:
        story = pymupdf.Story(html=_to_html(doc), user_css=_CSS)
        buf = io.BytesIO()
        writer = pymupdf.DocumentWriter(buf)
        page = pymupdf.paper_rect("a4")
        where = page + (48, 48, -48, -48)
        more, pages = 1, 0
        while more and pages < 60:
            dev = writer.begin_page(page)
            more, _ = story.place(where)
            story.draw(dev)
            writer.end_page()
            pages += 1
        writer.close()
        return buf.getvalue()
    except (RuntimeError, ValueError) as exc:
        raise ReportGenerationError() from exc


def render_docx(doc: ReportDoc) -> bytes:
    try:
        d = Document()
        d.add_heading(doc.title, level=0)
        if doc.disclaimer:
            d.add_paragraph().add_run(doc.disclaimer).italic = True
        for s in doc.sections:
            d.add_heading(s.heading, level=1)
            for p in s.paragraphs:
                d.add_paragraph(p)
            for b in s.bullets:
                d.add_paragraph(b, style="List Bullet")
            if s.table:
                head, *rows = s.table
                t = d.add_table(rows=1, cols=len(head))
                t.style = "Table Grid"
                for i, c in enumerate(head):
                    t.rows[0].cells[i].text = c
                for r in rows:
                    cells = t.add_row().cells
                    for i, c in enumerate(r):
                        cells[i].text = c
        buf = io.BytesIO()
        d.save(buf)
        return buf.getvalue()
    except (ValueError, KeyError, OSError) as exc:
        raise ReportGenerationError() from exc


def render(doc: ReportDoc, fmt: str) -> bytes:
    if fmt == "pdf":
        return render_pdf(doc)
    if fmt == "docx":
        return render_docx(doc)
    raise ReportGenerationError("Unsupported report format")
