"""Metrics middleware, settings and the protected /metrics endpoint (ADR-013)."""

from __future__ import annotations

import hmac
import time
from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import APIRouter, Request, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from scitracker.domain.errors import AuthenticationError
from scitracker.observability.metrics import Metrics

MIN_TOKEN_LENGTH = 16
UNMATCHED = "unmatched"
_TRUE_VALUES = {"1", "true", "yes", "on"}
API_PREFIX = "/api/v1"

router = APIRouter()


@dataclass(frozen=True, slots=True)
class MetricsSettings:
    enabled: bool = False
    token: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> MetricsSettings:
        enabled = env.get("METRICS_ENABLED", "false").strip().lower() in _TRUE_VALUES
        token = env.get("METRICS_TOKEN", "").strip()
        if enabled and len(token) < MIN_TOKEN_LENGTH:
            raise ValueError(
                f"METRICS_TOKEN must be at least {MIN_TOKEN_LENGTH} characters "
                "when METRICS_ENABLED is true"
            )
        return cls(enabled=enabled, token=token)


@dataclass(frozen=True, slots=True)
class MetricsAccess:
    metrics: Metrics
    token: str


class MetricsMiddleware:
    """Counts every HTTP request, labelled by route template (bounded cardinality)."""

    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        self._app = app
        self._metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        status = 500  # stays 500 if the application raises before responding
        started = time.perf_counter()
        self._metrics.started()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        finally:
            route = _route_label(scope)
            self._metrics.finished(scope["method"], route, status, time.perf_counter() - started)


def _route_label(scope: Scope) -> str:
    """Route template with the API prefix, so future API versions stay separate."""
    template: str | None = getattr(scope.get("route"), "path", None)
    if not template:
        return UNMATCHED
    if str(scope["path"]).startswith(API_PREFIX) and not template.startswith(API_PREFIX):
        return f"{API_PREFIX}{template}"
    return template


def _authorized(header: str | None, token: str) -> bool:
    if header is None:
        return False
    scheme, _, value = header.partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(
        value.strip().encode(), token.encode()
    )


@router.get("/metrics", include_in_schema=False)
def scrape(request: Request) -> Response:
    access: MetricsAccess | None = getattr(request.app.state, "metrics", None)
    if access is None:
        return Response(status_code=404)
    if not _authorized(request.headers.get("authorization"), access.token):
        raise AuthenticationError("Authentication required.")
    return Response(access.metrics.render(), headers={"Content-Type": access.metrics.content_type})
