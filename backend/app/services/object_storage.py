"""Object storage abstraction for generated files (reports, certificates).

``LocalObjectStorage`` writes under a fixed root and rejects any key that would escape it
(path traversal). It is for local development; on Render Free the disk is ephemeral, so files
vanish on restart. ``S3ObjectStorage`` stores files in any S3-compatible bucket (AWS S3, Cloudflare R2,
Backblaze B2, MinIO) and is the production choice; an incomplete S3 configuration fails fast with
``ConfigurationError`` instead of silently using disk.
Uploaded source documents are NOT stored: only extracted text and vectors are kept.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

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


class S3ObjectStorage:
    """S3-compatible storage. Keys are validated exactly like the local backend (no traversal)."""

    def __init__(self, bucket: str, client: Any, prefix: str = "") -> None:
        self._bucket, self._client, self._prefix = bucket, client, prefix

    def _key(self, key: str) -> str:
        if not _KEY.match(key) or ".." in key.split("/"):
            raise ValueError("Invalid storage key")
        return f"{self._prefix}{key}"

    @staticmethod
    def _missing(exc: Exception) -> bool:
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
        return code in {"NoSuchKey", "404", "NotFound"}

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=self._key(key), Body=data)

    def get(self, key: str) -> bytes:
        try:
            return bytes(self._client.get_object(Bucket=self._bucket, Key=self._key(key))["Body"].read())
        except Exception as exc:
            if self._missing(exc):
                raise NotFoundError() from exc
            raise

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._key(key))  # S3 delete is idempotent


def create_object_storage(settings: Settings) -> ObjectStorage:
    if settings.object_storage_backend == "local":
        return LocalObjectStorage(settings.object_storage_path)
    if settings.object_storage_backend == "s3":
        key, secret = settings.s3_access_key_id.get_secret_value(), settings.s3_secret_access_key.get_secret_value()
        if not (settings.s3_bucket and key and secret):
            raise ConfigurationError("S3 storage needs S3_BUCKET, S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY")
        import boto3  # imported lazily so local development does not need it

        client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint_url or None, region_name=settings.s3_region or None,
            aws_access_key_id=key, aws_secret_access_key=secret)
        return S3ObjectStorage(settings.s3_bucket, client)
    raise ConfigurationError("The configured object storage backend is not supported")
