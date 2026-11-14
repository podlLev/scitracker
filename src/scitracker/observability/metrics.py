"""Prometheus metrics registry (ADR-013). No web framework imports."""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class Metrics:
    """HTTP metrics of one application instance, kept in its own registry."""

    content_type = CONTENT_TYPE_LATEST

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self._requests = Counter(
            "scitracker_http_requests_total",
            "HTTP requests by method, route template and status code.",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self._duration = Histogram(
            "scitracker_http_request_duration_seconds",
            "HTTP request duration in seconds.",
            ["method", "route"],
            buckets=BUCKETS,
            registry=self.registry,
        )
        self._in_progress = Gauge(
            "scitracker_http_requests_in_progress",
            "HTTP requests currently being handled.",
            registry=self.registry,
        )

    def started(self) -> None:
        self._in_progress.inc()

    def finished(self, method: str, route: str, status: int, seconds: float) -> None:
        self._in_progress.dec()
        self._requests.labels(method, route, str(status)).inc()
        self._duration.labels(method, route).observe(seconds)

    def render(self) -> bytes:
        return generate_latest(self.registry)
