"""Exponential backoff retry for *transient* failures only.

Only ``AppError`` subclasses with ``retryable = True`` are retried; validation, authentication
and other permanent errors propagate immediately. ``sleep`` is injectable for fast tests.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)
T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    retries: int,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    attempt = 0
    while True:
        try:
            return fn()
        except AppError as exc:
            if not exc.retryable or attempt >= retries:
                raise
            delay = min(max_delay, base_delay * (2**attempt)) * (0.5 + random.random() / 2)
            attempt += 1
            logger.warning("retrying after transient failure",
                           extra={"attempt": attempt, "code": exc.code, "delay_s": round(delay, 2)})
            sleep(delay)
