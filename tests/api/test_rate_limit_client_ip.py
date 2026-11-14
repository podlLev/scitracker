from typing import Any

import pytest
from starlette.requests import Request

from scitracker.api.ratelimit import get_client_ip


def _request(xff: str | None, host: str | None = "10.0.0.1") -> Request:
    headers = [] if xff is None else [(b"x-forwarded-for", xff.encode())]
    scope: dict[str, Any] = {
        "type": "http",
        "headers": headers,
        "client": (host, 5000) if host else None,
    }
    return Request(scope)


@pytest.mark.parametrize(
    ("xff", "hops", "host", "expected"),
    [
        ("203.0.113.5", 0, "10.0.0.1", "10.0.0.1"),  # заголовок ігнорується
        ("203.0.113.5", 1, "10.0.0.1", "203.0.113.5"),
        ("6.6.6.6, 203.0.113.5", 1, "10.0.0.1", "203.0.113.5"),  # підробка зліва
        ("1.1.1.1, 203.0.113.5, 10.1.1.1", 2, "10.0.0.1", "203.0.113.5"),
        (None, 1, "10.0.0.1", "10.0.0.1"),
        ("203.0.113.5", 3, "10.0.0.1", "10.0.0.1"),  # коротше за hops
        (" , ", 1, "10.0.0.1", "10.0.0.1"),  # порожні елементи
        (None, 0, None, "unknown"),
    ],
)
def test_get_client_ip(xff: str | None, hops: int, host: str | None, expected: str) -> None:
    assert get_client_ip(_request(xff, host), hops) == expected
