"""Object storage abstraction for generated files (reports, certificates).

``LocalObjectStorage`` writes under a fixed root and rejects any key that would escape it
(path traversal). It is for local development; on Render Free the disk is ephemeral, so files
vanish on restart - production needs an S3-compatible backend (not implemented yet; selecting
``OBJECT_STORAGE_BACKEND=s3`` fails fast with ``ConfigurationError`` instead of silently using disk).
Uploaded source documents are NOT stored: only extracted text and vectors are kept.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, NotFoundError

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,300}$")


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _KEY.match(key) or ".." in key.split("/"):
            raise ValueError("Invalid storage key")
        path = (self._root / key).resolve()
        if self._root not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise NotFoundError() from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as exc:
            raise NotFoundError() from exc

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def create_object_storage(settings: Settings) -> ObjectStorage:
    if settings.object_storage_backend == "local":
        return LocalObjectStorage(settings.object_storage_path)
    raise ConfigurationError("The configured object storage backend is not implemented")
