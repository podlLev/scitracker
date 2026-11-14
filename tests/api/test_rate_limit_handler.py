import json
from typing import Any

import pytest
from starlette.requests import Request

from scitracker.api.ratelimit import rate_limit_exceeded_handler
from scitracker.services.ratelimit import RateLimitExceededError


def _request(path: str = "/api/v1/auth/login") -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": path,
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_handler_builds_problem_response() -> None:
    response = rate_limit_exceeded_handler(_request(), RateLimitExceededError("login", 17))
    assert response.status_code == 429
    assert response.headers["retry-after"] == "17"
    assert response.media_type == "application/problem+json"
    body = json.loads(bytes(response.body))
    assert body["status"] == 429
    assert body["title"] == "Too Many Requests"
    assert body["instance"] == "/api/v1/auth/login"
    assert "17" in body["detail"]


def test_handler_reraises_foreign_exceptions() -> None:
    with pytest.raises(RuntimeError):
        rate_limit_exceeded_handler(_request(), RuntimeError("boom"))
