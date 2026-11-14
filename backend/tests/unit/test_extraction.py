import pytest

from app.core.exceptions import DocumentProcessingError
from app.guardrails.file_validation import validate_upload
from app.processors.extraction import clean_text, extract_text, finalize_text
from tests.helpers import make_docx, make_pdf

MB = 1024 * 1024


def _extract(data: bytes, name: str, **kw: int) -> str:
    return extract_text(validate_upload(data, name, None, 5 * MB), max_chars=kw.get("max", 10000),
                        max_pdf_pages=kw.get("pages", 50))


def test_pdf_extraction() -> None:
    text = _extract(make_pdf("Senior Python developer\nSkills: FastAPI, Docker"), "cv.pdf")
    assert "Senior Python developer" in text and "FastAPI" in text


def test_docx_extraction_paragraphs_and_tables() -> None:
    data = make_docx(["Jane Doe", "Engineer"], table=[["Skill", "Level"], ["Python", "Expert"]])
    text = _extract(data, "cv.docx")
    assert "Jane Doe" in text and "Python | Expert" in text


def test_txt_extraction_with_bom() -> None:
    assert _extract(b"\xef\xbb\xbfhello  world", "cv.txt") == "hello world"


def test_scanned_pdf_gives_clear_error() -> None:
    with pytest.raises(DocumentProcessingError, match="Scanned"):
        _extract(make_pdf(""), "scan.pdf")


def test_corrupt_pdf_rejected() -> None:
    with pytest.raises(DocumentProcessingError):
        _extract(b"%PDF-1.7\n garbage that is not a pdf", "bad.pdf")


def test_pdf_page_limit() -> None:
    with pytest.raises(DocumentProcessingError, match="pages"):
        _extract(make_pdf("page text", pages=3), "long.pdf", pages=2)


def test_length_limit() -> None:
    with pytest.raises(DocumentProcessingError, match="too long"):
        finalize_text("word " * 100, max_chars=50)


def test_clean_text_normalises() -> None:
    raw = "a\x00b\r\n\r\n\r\n\r\nc \t  d e   \n  f"
    assert clean_text(raw) == "ab\n\nc d e\nf"


def test_manual_text_empty_rejected() -> None:
    with pytest.raises(DocumentProcessingError):
        finalize_text("  \n\x00 ", max_chars=100)
