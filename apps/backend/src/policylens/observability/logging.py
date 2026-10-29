import json
import logging
import sys
from datetime import UTC, datetime
from typing import TextIO


class SafeJsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "service": self.service_name,
            "level": record.levelname,
            "event": str(getattr(record, "event", "service_log")),
        }
        for key in (
            "trace_id",
            "server_name",
            "server_version",
            "tool_name",
            "resource_name",
            "argument_hash",
            "status",
            "duration_ms",
            "error_code",
            "exception_type",
            "http_status",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = str(value)
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(
    service_name: str, level: str = "INFO", stream: TextIO | None = None
) -> logging.Logger:
    logger = logging.getLogger(service_name)
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(SafeJsonFormatter(service_name))
    logger.addHandler(handler)
    return logger
