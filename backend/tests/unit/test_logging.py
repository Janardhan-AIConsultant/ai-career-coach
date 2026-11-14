import json
import logging
from pathlib import Path

from app.core.logging_config import configure_logging, correlation_id


def test_json_log_has_required_fields(tmp_path: Path) -> None:
    configure_logging("INFO", "json", str(tmp_path))
    token = correlation_id.set("abc123")
    logging.getLogger("t").info("hello", extra={"op_ctx": "x"})
    correlation_id.reset(token)
    for handler in logging.getLogger().handlers:
        handler.flush()
    line = (tmp_path / "app.log").read_text().strip().splitlines()[-1]
    data = json.loads(line)
    assert data["correlation_id"] == "abc123"
    assert data["level"] == "INFO" and data["message"] == "hello" and data["op_ctx"] == "x"
    assert {"timestamp", "module", "operation"} <= data.keys()
    configure_logging("INFO", "text")  # release the file handle
