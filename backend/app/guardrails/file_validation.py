"""Upload validation: extension, declared MIME, magic bytes, size, ZIP-bomb limits.

Purpose: reject unsafe/corrupt uploads *before* any parser touches them. Nothing is executed
and nothing is written to disk. The client filename is only ever sanitised for display; storage
keys are generated server-side, so path traversal via filenames is impossible.
Inputs: raw bytes + client filename + declared content type. Output: ``ValidatedFile``.
Errors: ``FileValidationError`` (client-safe messages, not retryable).
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass

from app.core.exceptions import FileValidationError

ALLOWED_TYPES: dict[str, set[str]] = {
    "pdf": {"application/pdf"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "txt": {"text/plain"},
}

MAX_ZIP_ENTRIES = 1000
MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ZIP_RATIO = 100

_UNSAFE = re.compile(r"[\x00-\x1f\x7f<>:\"|?*]")


@dataclass(frozen=True)
class ValidatedFile:
    safe_name: str
    extension: str
    content_type: str
    data: bytes
    size: int


def sanitize_filename(name: str) -> str:
    """Return a display-safe base name (no directories, control chars or traversal)."""
    name = unicodedata.normalize("NFKC", name or "")
    name = name.replace("\\", "/").split("/")[-1]
    name = _UNSAFE.sub("", name).strip(" .")
    name = name[:120]
    if not name:
        raise FileValidationError("A valid file name is required")
    return name


def _check_docx_zip(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise FileValidationError("DOCX file has too many entries")
            total = sum(i.file_size for i in infos)
            if total > MAX_ZIP_UNCOMPRESSED_BYTES or (
                len(data) and total / len(data) > MAX_ZIP_RATIO
            ):
                raise FileValidationError("DOCX file expands too much and was rejected")
            names = {i.filename for i in infos}
            if any(n.startswith("/") or ".." in n.split("/") for n in names):
                raise FileValidationError("DOCX file contains unsafe paths")
            if "word/document.xml" not in names:
                raise FileValidationError("File is not a valid DOCX document")
    except zipfile.BadZipFile as exc:
        raise FileValidationError("File is corrupted or not a valid DOCX") from exc


def validate_upload(
    data: bytes, filename: str, content_type: str | None, max_bytes: int
) -> ValidatedFile:
    safe_name = sanitize_filename(filename)
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext not in ALLOWED_TYPES:
        raise FileValidationError("Unsupported file type. Allowed: PDF, DOCX, TXT")
    if not data:
        raise FileValidationError("The file is empty")
    if len(data) > max_bytes:
        raise FileValidationError(f"File exceeds the {max_bytes // (1024 * 1024)} MB limit")

    declared = (content_type or "").split(";")[0].strip().lower()
    # Browsers often send octet-stream; the signature check below is the authority.
    if declared and declared != "application/octet-stream" and declared not in ALLOWED_TYPES[ext]:
        raise FileValidationError("File content type does not match its extension")

    if ext == "pdf":
        if not data.startswith(b"%PDF-"):
            raise FileValidationError("File content is not a valid PDF")
    elif ext == "docx":
        if not data.startswith(b"PK\x03\x04"):
            raise FileValidationError("File content is not a valid DOCX")
        _check_docx_zip(data)
    else:
        if b"\x00" in data:
            raise FileValidationError("Text file contains binary data")
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FileValidationError("Text file must be UTF-8 encoded") from exc

    return ValidatedFile(safe_name, ext, next(iter(ALLOWED_TYPES[ext])), data, len(data))
