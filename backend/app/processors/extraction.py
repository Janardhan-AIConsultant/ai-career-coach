"""Text extraction (PDF via PyMuPDF, DOCX via python-docx, TXT) and text cleaning.

Purpose: turn a ``ValidatedFile`` into clean plain text, in memory only (no temp files).
Errors: ``DocumentProcessingError`` for corrupt/encrypted/empty/oversized documents.
Limitations: scanned (image-only) PDFs are rejected with a clear message; OCR is not enabled.
Extracted text is untrusted data and is never interpreted as instructions.
"""

from __future__ import annotations

import io
import re
import unicodedata

import pymupdf  # PyMuPDF
from docx import Document as DocxDocument

from app.core.exceptions import DocumentProcessingError
from app.guardrails.file_validation import ValidatedFile

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """Normalise unicode/newlines, drop control chars, collapse whitespace."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = _CONTROL.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf(data: bytes, max_pages: int) -> str:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise DocumentProcessingError("The PDF is corrupted or unreadable") from exc
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise DocumentProcessingError("Password-protected PDFs are not supported")
        if doc.page_count > max_pages:
            raise DocumentProcessingError(f"PDF has more than {max_pages} pages")
        return "\n".join(str(doc.load_page(i).get_text()) for i in range(doc.page_count))
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise DocumentProcessingError("The PDF is corrupted or unreadable") from exc
    finally:
        doc.close()


def _extract_docx(data: bytes) -> str:
    try:
        document = DocxDocument(io.BytesIO(data))
    except Exception as exc:  # python-docx raises varied errors for malformed packages
        raise DocumentProcessingError("The DOCX file is corrupted or unreadable") from exc
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def extract_text(file: ValidatedFile, *, max_chars: int, max_pdf_pages: int = 50) -> str:
    if file.extension == "pdf":
        raw = _extract_pdf(file.data, max_pdf_pages)
    elif file.extension == "docx":
        raw = _extract_docx(file.data)
    else:
        raw = file.data.decode("utf-8-sig")
    return finalize_text(raw, max_chars=max_chars, scanned_hint=file.extension == "pdf")


def finalize_text(raw: str, *, max_chars: int, scanned_hint: bool = False) -> str:
    """Clean and bound text (also used for pasted manual text input)."""
    text = clean_text(raw)
    if not text:
        msg = (
            "No extractable text found. Scanned/image-only PDFs are not supported yet; "
            "please upload a text-based file or paste the text."
            if scanned_hint
            else "The document contains no text"
        )
        raise DocumentProcessingError(msg)
    if len(text) > max_chars:
        raise DocumentProcessingError("The document is too long to process")
    return text
