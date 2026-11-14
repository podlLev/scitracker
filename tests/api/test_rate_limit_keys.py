from typing import Any

from fastapi import FastAPI
from starlette.requests import Request

from scitracker.api.ratelimit import (
    RateLimits,
    enforce_login_limit,
    enforce_register_limit,
)
from scitracker.services.ratelimit import RateLimitDecision


class _Recorder:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def hit(self, key: str) -> RateLimitDecision:
        self.keys.append(key)
        return RateLimitDecision(True, 0, 1)


def _request(
    limits: RateLimits | None,
    *,
    host: str = "10.0.0.1",
    xff: str | None = None,
) -> Request:
    app = FastAPI()
    app.state.rate_limits = limits
    headers = [] if xff is None else [(b"x-forwarded-for", xff.encode())]
    scope: dict[str, Any] = {
        "type": "http",
        "app": app,
        "headers": headers,
        "client": (host, 5000),
    }
    return Request(scope)


def _limits(
    *, hops: int = 0, enabled: bool = True
) -> tuple[RateLimits, _Recorder, _Recorder, _Recorder]:
    account, ip, register = _Recorder(), _Recorder(), _Recorder()
    limits = RateLimits(
        enabled=enabled,
        trusted_proxy_hops=hops,
        login_account=account,
        login_ip=ip,
        register_ip=register,
    )
    return limits, account, ip, register


def test_login_uses_ip_and_account_keys() -> None:
    limits, account, ip, _ = _limits()
    enforce_login_limit(_request(limits), "user@example.com")
    assert ip.keys == ["login-ip:10.0.0.1"]
    assert len(account.keys) == 1
    assert account.keys[0].startswith("login-acc:10.0.0.1:")


def test_account_key_does_not_contain_email() -> None:
    limits, account, _, _ = _limits()
    enforce_login_limit(_request(limits), "Secret.Person@example.com")
    assert "secret" not in account.keys[0].lower()
    assert "example.com" not in account.keys[0]


def test_account_key_is_normalized() -> None:
    limits, account, _, _ = _limits()
    enforce_login_limit(_request(limits), "a@example.com")
    enforce_login_limit(_request(limits), "  A@EXAMPLE.com ")
    assert account.keys[0] == account.keys[1]


def test_different_emails_get_different_keys() -> None:
    limits, account, _, _ = _limits()
    enforce_login_limit(_request(limits), "a@example.com")
    enforce_login_limit(_request(limits), "b@example.com")
    assert account.keys[0] != account.keys[1]


def test_register_uses_ip_key_only() -> None:
    limits, account, ip, register = _limits()
    enforce_register_limit(_request(limits))
    assert register.keys == ["register-ip:10.0.0.1"]
    assert account.keys == []
    assert ip.keys == []


def test_trusted_proxy_changes_ip_in_keys() -> None:
    limits, _, ip, _ = _limits(hops=1)
    enforce_login_limit(_request(limits, xff="6.6.6.6, 203.0.113.9"), "a@example.com")
    assert ip.keys == ["login-ip:203.0.113.9"]


def test_disabled_limits_touch_nothing() -> None:
    limits, account, ip, register = _limits(enabled=False)
    enforce_login_limit(_request(limits), "a@example.com")
    enforce_register_limit(_request(limits))
    assert account.keys == ip.keys == register.keys == []


def test_missing_limits_are_a_noop() -> None:
    enforce_login_limit(_request(None), "a@example.com")
    enforce_register_limit(_request(None))
