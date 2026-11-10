import io
import json
import logging
import sys
from collections.abc import Iterator

import pytest

from scitracker.observability.context import bind_request_id, new_run_id, request_id_var
from scitracker.observability.logs import (
    JsonFormatter,
    LogSettings,
    ManagedHandler,
    TextFormatter,
    configure_logging,
)


def make_record(message: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("scitracker.test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_line_has_the_standard_fields() -> None:
    data = json.loads(
        JsonFormatter().format(
            make_record(
                "saved %d",
            )
        )
    )
    assert data["level"] == "INFO"
    assert data["logger"] == "scitracker.test"
    assert data["message"] == "saved %d"
    assert data["timestamp"].endswith("+00:00")
    assert "request_id" not in data


def test_extra_fields_are_included_and_nulls_dropped() -> None:
    data = json.loads(JsonFormatter().format(make_record(status=404, route=None, path="/x")))
    assert (data["status"], data["path"]) == (404, "/x")
    assert "route" not in data


def test_request_id_comes_from_the_context_and_an_explicit_value_wins() -> None:
    with bind_request_id("ctx-12345678"):
        assert json.loads(JsonFormatter().format(make_record()))["request_id"] == "ctx-12345678"
        explicit = make_record(request_id="explicit-1234")
        assert json.loads(JsonFormatter().format(explicit))["request_id"] == "explicit-1234"
    assert request_id_var.get() is None


def test_exception_is_included_and_scrubbed() -> None:
    try:
        raise RuntimeError("db url postgresql://u:hunter2@h/db")
    except RuntimeError:
        record = make_record()
        record.exc_info = sys.exc_info()
    data = json.loads(JsonFormatter().format(record))
    assert "RuntimeError" in data["exception"]
    assert "hunter2" not in data["exception"]


def test_secrets_in_message_and_fields_never_reach_the_output() -> None:
    line = JsonFormatter().format(
        make_record("login password=hunter2", authorization="Bearer abcdefgh12345")
    )
    assert "hunter2" not in line
    assert "abcdefgh12345" not in line


def test_non_serialisable_extra_does_not_break_logging() -> None:
    data = json.loads(JsonFormatter().format(make_record(thing=object())))
    assert data["thing"].startswith("<object object")


def test_text_formatter_adds_the_request_id_and_scrubs() -> None:
    with bind_request_id("ctx-12345678"):
        line = TextFormatter().format(make_record("password=hunter2"))
    assert line.startswith("[ctx-12345678] ")
    assert "hunter2" not in line


def test_run_ids_are_distinct_and_recognisable() -> None:
    first, second = new_run_id(), new_run_id()
    assert first != second
    assert first.startswith("run-")
    assert len(first) == 16


def test_bind_restores_the_previous_value_even_after_an_error() -> None:
    with bind_request_id("outer-12345678"):
        with pytest.raises(ValueError, match="x"), bind_request_id("inner-12345678"):
            raise ValueError("x")
        assert request_id_var.get() == "outer-12345678"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, ("INFO", "json")),
        ({"LOG_LEVEL": " debug ", "LOG_FORMAT": "TEXT"}, ("DEBUG", "text")),
    ],
)
def test_log_settings(env: dict[str, str], expected: tuple[str, str]) -> None:
    settings = LogSettings.from_env(env)
    assert (settings.level, settings.format) == expected


@pytest.mark.parametrize("env", [{"LOG_LEVEL": "LOUD"}, {"LOG_FORMAT": "xml"}])
def test_invalid_log_settings_are_a_clear_error(env: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="LOG_"):
        LogSettings.from_env(env)


@pytest.fixture
def clean_logging() -> Iterator[None]:
    names = ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore")
    root = logging.getLogger()
    saved_root = (list(root.handlers), root.level)
    saved = {
        name: (
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).propagate,
            logging.getLogger(name).level,
        )
        for name in names
    }
    yield
    root.handlers[:] = saved_root[0]
    root.setLevel(saved_root[1])
    for name, (handlers, propagate, level) in saved.items():
        target = logging.getLogger(name)
        target.handlers[:] = handlers
        target.propagate = propagate
        target.setLevel(level)


@pytest.mark.usefixtures("clean_logging")
def test_configure_logging_is_idempotent_and_quietens_noisy_loggers() -> None:
    stream = io.StringIO()
    configure_logging("WARNING", "json", stream)
    configure_logging("INFO", "json", stream)
    root = logging.getLogger()
    assert sum(isinstance(h, ManagedHandler) for h in root.handlers) == 1
    logging.getLogger("scitracker.demo").info("once")
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "once"
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("uvicorn.access").propagate is False
    assert logging.getLogger("uvicorn.error").propagate is True
