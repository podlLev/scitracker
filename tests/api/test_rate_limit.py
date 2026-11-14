import logging
import uuid
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from scitracker.api.ratelimit import RateLimits
from scitracker.security.rate_limiter import InMemorySlidingWindowLimiter
from scitracker.services.accounts import MIN_PASSWORD_LENGTH

if TYPE_CHECKING:
    from fastapi import FastAPI

LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"
VALID_PASSWORD = "Aa1-" + "x" * MIN_PASSWORD_LENGTH


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _install(
    client: TestClient,
    clock: FakeClock,
    *,
    account: int = 2,
    ip: int = 100,
    register: int = 2,
    hops: int = 0,
    enabled: bool = True,
) -> None:
    def make(limit: int) -> InMemorySlidingWindowLimiter:
        return InMemorySlidingWindowLimiter(limit=limit, window_seconds=60, clock=clock)

    app = cast("FastAPI", client.app)
    app.state.rate_limits = RateLimits(
        enabled=enabled,
        trusted_proxy_hops=hops,
        login_account=make(account),
        login_ip=make(ip),
        register_ip=make(register),
    )


def _login(client: TestClient, email: str, headers: dict[str, str] | None = None) -> Response:
    return client.post(
        LOGIN,
        json={"email": email, "password": "wrong-password-123"},
        headers=headers or {},
    )


def _register(client: TestClient) -> Response:
    body = {"email": f"{uuid.uuid4().hex}@example.com", "password": VALID_PASSWORD}
    return client.post(REGISTER, json=body)


def test_login_is_blocked_after_limit(client: TestClient) -> None:
    _install(client, FakeClock(), account=2)
    assert _login(client, "a@example.com").status_code == 401
    assert _login(client, "a@example.com").status_code == 401
    blocked = _login(client, "a@example.com")
    assert blocked.status_code == 429
    assert blocked.headers["content-type"].startswith("application/problem+json")
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert blocked.json()["status"] == 429


def test_account_limit_does_not_block_other_account(client: TestClient) -> None:
    _install(client, FakeClock(), account=1)
    assert _login(client, "a@example.com").status_code == 401
    assert _login(client, "a@example.com").status_code == 429
    assert _login(client, "b@example.com").status_code == 401


def test_email_case_and_spaces_share_one_counter(client: TestClient) -> None:
    _install(client, FakeClock(), account=1)
    assert _login(client, "a@example.com").status_code == 401
    assert _login(client, "  A@Example.com ").status_code == 429


def test_ip_limit_blocks_email_spraying(client: TestClient) -> None:
    _install(client, FakeClock(), account=100, ip=2)
    assert _login(client, "a@example.com").status_code == 401
    assert _login(client, "b@example.com").status_code == 401
    assert _login(client, "c@example.com").status_code == 429


def test_other_client_ip_is_not_blocked_behind_proxy(client: TestClient) -> None:
    _install(client, FakeClock(), account=1, hops=1)
    first = {"X-Forwarded-For": "203.0.113.1"}
    assert _login(client, "a@example.com", first).status_code == 401
    assert _login(client, "a@example.com", first).status_code == 429
    second = {"X-Forwarded-For": "203.0.113.2"}
    assert _login(client, "a@example.com", second).status_code == 401


def test_forwarded_header_is_ignored_without_trusted_proxy(client: TestClient) -> None:
    _install(client, FakeClock(), account=1, hops=0)
    assert _login(client, "a@example.com", {"X-Forwarded-For": "1.1.1.1"}).status_code == 401
    spoofed = _login(client, "a@example.com", {"X-Forwarded-For": "2.2.2.2"})
    assert spoofed.status_code == 429


def test_limit_expires_after_window(client: TestClient) -> None:
    clock = FakeClock()
    _install(client, clock, account=1)
    assert _login(client, "a@example.com").status_code == 401
    assert _login(client, "a@example.com").status_code == 429
    clock.now += 61
    assert _login(client, "a@example.com").status_code == 401


def test_register_is_limited(client: TestClient) -> None:
    _install(client, FakeClock(), register=1)
    assert _register(client).status_code == 201
    blocked = _register(client)
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers


def test_login_and_register_limits_are_separate(client: TestClient) -> None:
    _install(client, FakeClock(), account=1, register=1)
    assert _login(client, "a@example.com").status_code == 401
    assert _login(client, "a@example.com").status_code == 429
    assert _register(client).status_code == 201


def test_disabled_limiter_never_blocks(client: TestClient) -> None:
    _install(client, FakeClock(), account=1, enabled=False)
    codes = {_login(client, "a@example.com").status_code for _ in range(5)}
    assert codes == {401}


def test_no_limits_configured_never_blocks(client: TestClient) -> None:
    app = cast("FastAPI", client.app)
    app.state.rate_limits = None
    codes = {_login(client, "a@example.com").status_code for _ in range(5)}
    assert codes == {401}


def test_429_is_documented_in_openapi(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "429" in paths["/api/v1/auth/login"]["post"]["responses"]
    assert "429" in paths["/api/v1/auth/register"]["post"]["responses"]


def test_log_does_not_contain_email(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    _install(client, FakeClock(), account=1)
    with caplog.at_level(logging.WARNING):
        _login(client, "secret.person@example.com")
        _login(client, "secret.person@example.com")
    assert "rate limit exceeded" in caplog.text
    assert "secret.person" not in caplog.text
