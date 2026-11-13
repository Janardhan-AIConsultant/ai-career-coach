import pytest

from app.core.exceptions import FileValidationError
from app.guardrails.file_validation import sanitize_filename, validate_upload
from tests.helpers import make_docx, make_pdf, make_zip

MB = 1024 * 1024
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_valid_pdf_docx_txt() -> None:
    assert validate_upload(make_pdf("hello"), "cv.pdf", PDF, MB).extension == "pdf"
    assert validate_upload(make_docx(["hello"]), "cv.DOCX", DOCX, MB).extension == "docx"
    assert validate_upload(b"hello", "cv.txt", "text/plain", MB).extension == "txt"


def test_octet_stream_allowed_if_signature_valid() -> None:
    assert validate_upload(make_pdf("x"), "cv.pdf", "application/octet-stream", MB)


@pytest.mark.parametrize("name", ["cv.exe", "cv", "cv.pdf.exe", "cv.html", "cv.zip", ".pdf.sh"])
def test_extension_allowlist(name: str) -> None:
    with pytest.raises(FileValidationError):
        validate_upload(b"%PDF-1.4", name, PDF, MB)


def test_size_limits() -> None:
    with pytest.raises(FileValidationError, match="empty"):
        validate_upload(b"", "a.txt", "text/plain", MB)
    with pytest.raises(FileValidationError, match="limit"):
        validate_upload(b"a" * (MB + 1), "a.txt", "text/plain", MB)


def test_mime_extension_mismatch() -> None:
    with pytest.raises(FileValidationError, match="does not match"):
        validate_upload(make_pdf("x"), "cv.pdf", "text/html", MB)


def test_signature_spoofing_rejected() -> None:
    # an executable renamed to .pdf / .docx
    with pytest.raises(FileValidationError):
        validate_upload(b"MZ\x90\x00 malicious", "cv.pdf", PDF, MB)
    with pytest.raises(FileValidationError):
        validate_upload(b"MZ\x90\x00 malicious", "cv.docx", DOCX, MB)
    with pytest.raises(FileValidationError):
        validate_upload(make_pdf("x"), "cv.docx", DOCX, MB)


def test_text_binary_and_encoding_rejected() -> None:
    with pytest.raises(FileValidationError):
        validate_upload(b"abc\x00def", "a.txt", "text/plain", MB)
    with pytest.raises(FileValidationError, match="UTF-8"):
        validate_upload("é".encode("latin-1"), "a.txt", "text/plain", MB)


def test_corrupt_and_non_word_zip_rejected() -> None:
    with pytest.raises(FileValidationError, match="corrupted"):
        validate_upload(b"PK\x03\x04garbage", "a.docx", DOCX, MB)
    with pytest.raises(FileValidationError, match="not a valid DOCX"):
        validate_upload(make_zip({"readme.txt": b"hi"}), "a.docx", DOCX, MB)


def test_zip_bomb_rejected() -> None:
    bomb = make_zip({"word/document.xml": b"0" * (30 * MB)})
    assert len(bomb) < MB  # tiny on the wire, huge when expanded
    with pytest.raises(FileValidationError, match="expands"):
        validate_upload(bomb, "a.docx", DOCX, 5 * MB)


def test_zip_slip_paths_rejected() -> None:
    evil = make_zip({"word/document.xml": b"<x/>", "../../evil.sh": b"x"})
    with pytest.raises(FileValidationError, match="unsafe paths"):
        validate_upload(evil, "a.docx", DOCX, MB)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\cmd.exe", "cmd.exe"),
        ("/abs/path/cv.pdf", "cv.pdf"),
        ("cv\x00.pdf", "cv.pdf"),
        ("a<b>:c|d?.txt", "abcd.txt"),
    ],
)
def test_filename_sanitised(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw", ["", "...", "/", "   "])
def test_filename_required(raw: str) -> None:
    with pytest.raises(FileValidationError):
        sanitize_filename(raw)
