"""Structured logging with correlation IDs.

Purpose: configure JSON/text logging (console always; RotatingFileHandler optionally).
Important: ``correlation_id`` ContextVar, ``JsonFormatter``, ``configure_logging``.
Privacy: callers must never pass resume text, passwords or keys; extra fields are
passed through as-is, so only non-sensitive context belongs there.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "operation": record.funcName,
            "correlation_id": getattr(record, "correlation_id", "-"),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and key != "correlation_id":
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


TEXT_FORMAT = "%(asctime)s %(levelname)s [%(correlation_id)s] %(module)s.%(funcName)s: %(message)s"


def configure_logging(
    level: str = "INFO", fmt: str = "json", log_dir: str | None = None
) -> None:
    """Idempotently configure the root logger. ``log_dir`` enables a rotating file."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    formatter: logging.Formatter = (
        JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT)
    )
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                Path(log_dir) / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
            )
        )
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(CorrelationFilter())
        root.addHandler(handler)
    root.setLevel(level.upper())
