import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Self, TextIO

from scitracker.observability.context import request_id_var
from scitracker.observability.redact import redact_text, redact_value

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
FORMATS = ("json", "text")
# Attributes every LogRecord has: everything else came from `extra=` and is logged as a field.
_STANDARD = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "request_id"}


def _current_request_id(record: logging.LogRecord) -> str | None:
    explicit: str | None = getattr(record, "request_id", None)
    return explicit or request_id_var.get()


class JsonFormatter(logging.Formatter):
    """One JSON object per line: easy for machines (and for `docker logs | jq`)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        request_id = _current_request_id(record)
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key in _STANDARD or key.startswith("_") or value is None:
                continue
            payload[key] = redact_value(key, value)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable variant for local development."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        line = redact_text(super().format(record))
        request_id = _current_request_id(record)
        return f"[{request_id}] {line}" if request_id else line


class ManagedHandler(logging.StreamHandler[TextIO]):
    """Marks the handler installed by `configure_logging`, so a repeated call replaces it."""


@dataclass(frozen=True, slots=True)
class LogSettings:
    level: str = "INFO"
    format: str = "json"

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        level = env.get("LOG_LEVEL", "").strip().upper() or "INFO"
        fmt = env.get("LOG_FORMAT", "").strip().lower() or "json"
        if level not in LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {', '.join(LEVELS)}, got {level!r}")
        if fmt not in FORMATS:
            raise ValueError(f"LOG_FORMAT must be one of {', '.join(FORMATS)}, got {fmt!r}")
        return cls(level, fmt)


def configure_logging(level: str = "INFO", fmt: str = "json", stream: TextIO | None = None) -> None:
    """Send all logs to one handler (stderr by default). Safe to call more than once."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, ManagedHandler):
            root.removeHandler(handler)
    managed = ManagedHandler(stream or sys.stderr)
    managed.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    root.addHandler(managed)
    root.setLevel(level)
    # uvicorn installs its own handlers: route its errors through ours, and silence its
    # access log, because RequestContextMiddleware writes a structured one.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    # httpx logs full URLs at INFO, including the Crossref `mailto` parameter.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
