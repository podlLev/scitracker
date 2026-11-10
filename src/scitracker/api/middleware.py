import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from scitracker.observability.context import bind_request_id

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")
access_logger = logging.getLogger("scitracker.access")


def _accept_or_generate(candidate: str | None) -> str:
    """A client may bring its own id (to trace a call through several systems), if it is sane."""
    if candidate and _VALID_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Gives every request a correlation id, returns it in a header and writes the access log."""

    def __init__(
        self, app: ASGIApp, *, quiet_paths: frozenset[str] = frozenset({"/healthz"})
    ) -> None:
        self.app = app
        self._quiet_paths = quiet_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _accept_or_generate(Headers(scope=scope).get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id  # exception handlers read it
        status = 500  # stays 500 when an exception escapes to the outer error handler
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = MutableHeaders(scope=message)
                if REQUEST_ID_HEADER not in headers:
                    headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        with bind_request_id(request_id):
            try:
                await self.app(scope, receive, send_with_id)
            finally:
                self._log(scope, status, time.perf_counter() - started)

    def _log(self, scope: Scope, status: int, seconds: float) -> None:
        path = str(scope["path"])[:200]
        quiet = path in self._quiet_paths and status < 400
        level = logging.ERROR if status >= 500 else logging.DEBUG if quiet else logging.INFO
        route = getattr(scope.get("route"), "path_format", None)
        access_logger.log(
            level,
            "%s %s %d",
            scope["method"],
            path,
            status,
            extra={
                "method": scope["method"],
                "path": path,
                "route": route,
                "status": status,
                "duration_ms": round(seconds * 1000, 2),
            },
        )
