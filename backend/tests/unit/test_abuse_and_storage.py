import threading
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.exceptions import (
    ConfigurationError,
    NotFoundError,
    RateLimitExceededError,
    ServiceBusyError,
)
from app.services.object_storage import LocalObjectStorage, create_object_storage
from app.utils.rate_limit import ProcessingGate, SlidingWindowLimiter


def test_sliding_window_limits_and_recovers() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(2, 10, clock=lambda: now[0])
    limiter.check("a")
    limiter.check("a")
    with pytest.raises(RateLimitExceededError):
        limiter.check("a")
    limiter.check("b")  # separate key
    now[0] = 10.5
    limiter.check("a")  # window slid


def test_processing_gate_bounds_concurrency_and_releases() -> None:
    gate = ProcessingGate(2)
    with gate.acquire(), gate.acquire(), pytest.raises(ServiceBusyError), gate.acquire():
        pass
    with gate.acquire():
        pass


def test_gate_releases_on_error() -> None:
    gate = ProcessingGate(1)
    with pytest.raises(ValueError), gate.acquire():
        raise ValueError
    with gate.acquire():
        pass


def test_gate_is_thread_safe() -> None:
    gate, results = ProcessingGate(1), []
    started, release = threading.Event(), threading.Event()

    def hold() -> None:
        with gate.acquire():
            started.set()
            release.wait(2)

    t = threading.Thread(target=hold)
    t.start()
    started.wait(2)
    try:
        with gate.acquire():
            results.append("entered")
    except ServiceBusyError:
        results.append("busy")
    release.set()
    t.join()
    assert results == ["busy"]


def test_local_storage_roundtrip_and_delete(tmp_path: Path) -> None:
    s = LocalObjectStorage(tmp_path)
    s.put("guest/abc/r1.pdf", b"data")
    assert s.get("guest/abc/r1.pdf") == b"data"
    s.delete("guest/abc/r1.pdf")
    s.delete("guest/abc/r1.pdf")  # idempotent
    with pytest.raises(NotFoundError):
        s.get("guest/abc/r1.pdf")


@pytest.mark.parametrize(
    "key", ["../evil", "a/../../evil", "/etc/passwd", "..\\evil", "a/b/../../../x", "", "a\x00b"]
)
def test_local_storage_rejects_traversal(tmp_path: Path, key: str) -> None:
    s = LocalObjectStorage(tmp_path / "root")
    with pytest.raises(ValueError):
        s.put(key, b"x")
    assert not (tmp_path / "evil").exists()


def test_s3_backend_fails_fast_instead_of_using_disk() -> None:
    s = Settings(_env_file=None, object_storage_backend="s3")  # type: ignore[call-arg]
    with pytest.raises(ConfigurationError):
        create_object_storage(s)


class _FakeS3:
    """Just enough of the boto3 S3 client; raises a botocore-shaped error for missing keys."""

    class ClientError(Exception):
        def __init__(self, code: str) -> None:
            self.response = {"Error": {"Code": code}}

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket: str, Key: str) -> dict:  # type: ignore[type-arg]
        import io
        if (Bucket, Key) not in self.objects:
            raise self.ClientError("NoSuchKey")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)


def test_s3_storage_round_trip_prefix_and_missing_key() -> None:
    from app.services.object_storage import S3ObjectStorage
    fake = _FakeS3()
    s = S3ObjectStorage("bkt", fake, prefix="reports/")
    s.put("a/b.pdf", b"data")
    assert fake.objects == {("bkt", "reports/a/b.pdf"): b"data"}
    assert s.get("a/b.pdf") == b"data"
    s.delete("a/b.pdf")
    s.delete("a/b.pdf")  # idempotent
    with pytest.raises(NotFoundError):
        s.get("a/b.pdf")


def test_s3_storage_rejects_unsafe_keys_and_propagates_other_errors() -> None:
    from app.services.object_storage import S3ObjectStorage
    s = S3ObjectStorage("bkt", _FakeS3())
    for bad in ("../x", "a/../b", "/abs", "", "a b"):
        with pytest.raises(ValueError):
            s.put(bad, b"x")

    class Broken(_FakeS3):
        def get_object(self, Bucket: str, Key: str) -> dict:  # type: ignore[type-arg]
            raise self.ClientError("AccessDenied")

    with pytest.raises(Exception) as exc:
        S3ObjectStorage("bkt", Broken()).get("k")
    assert not isinstance(exc.value, NotFoundError)


def test_s3_factory_needs_complete_configuration_and_builds_a_client() -> None:
    from app.services.object_storage import S3ObjectStorage
    base = {"_env_file": None, "object_storage_backend": "s3"}
    for partial in ({}, {"s3_bucket": "b"}, {"s3_bucket": "b", "s3_access_key_id": "k"}):
        with pytest.raises(ConfigurationError):
            create_object_storage(Settings(**base, **partial))  # type: ignore[arg-type]
    full = Settings(**base, s3_bucket="b", s3_access_key_id="k", s3_secret_access_key="s",  # type: ignore[arg-type]
                    s3_endpoint_url="https://example.invalid", s3_region="auto")
    assert isinstance(create_object_storage(full), S3ObjectStorage)
