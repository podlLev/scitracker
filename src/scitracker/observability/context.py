import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


@contextmanager
def bind_request_id(value: str) -> Iterator[None]:
    """Everything logged inside the block (in this thread or task) carries `value`."""
    token = request_id_var.set(value)
    try:
        yield
    finally:
        request_id_var.reset(token)


def new_run_id() -> str:
    """Correlation id of a background run (a CLI command or one scheduled collection)."""
    return f"run-{uuid.uuid4().hex[:12]}"
