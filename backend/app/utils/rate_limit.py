"""In-process abuse controls: sliding-window rate limiter and a non-blocking concurrency gate.

Scope/limits: state is per process (fine for a single free-tier instance; use a shared store such
as Redis if the API is scaled horizontally). Keys are hashed-free identifiers like a client IP;
nothing here is persisted. ``ProcessingGate`` bounds concurrent heavy work (document ingestion)
and fails fast with a 503 instead of queueing, protecting small hosts.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from app.core.exceptions import RateLimitExceededError, ServiceBusyError


class SlidingWindowLimiter:
    def __init__(
        self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit, self._window, self._clock = limit, window_seconds, clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                raise RateLimitExceededError()
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory under abuse
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self._window]:
                    del self._hits[k]


class ProcessingGate:
    def __init__(self, max_concurrent: int) -> None:
        self._sem = threading.BoundedSemaphore(max_concurrent)

    @contextmanager
    def acquire(self) -> Iterator[None]:
        if not self._sem.acquire(blocking=False):
            raise ServiceBusyError()
        try:
            yield
        finally:
            self._sem.release()
