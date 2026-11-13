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
