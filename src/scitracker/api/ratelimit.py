"""HTTP-шар обмеження частоти: ключі, IP клієнта, відповідь 429."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

from scitracker.services.ratelimit import (
    RateLimiter,
    RateLimitExceededError,
    enforce,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimits:
    enabled: bool
    trusted_proxy_hops: int
    login_account: RateLimiter
    login_ip: RateLimiter
    register_ip: RateLimiter


def get_client_ip(request: Request, trusted_hops: int) -> str:
    """Return the client IP; behind trusted proxies, count X-Forwarded-For from the end."""
    if trusted_hops > 0:
        header = request.headers.get("x-forwarded-for")
        if header:
            parts = [p.strip() for p in header.split(",") if p.strip()]
            if len(parts) >= trusted_hops:
                return parts[-trusted_hops]
    client = request.client
    return client.host if client else "unknown"


def _digest(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:16]


def _limits(request: Request) -> RateLimits | None:
    limits: RateLimits | None = getattr(request.app.state, "rate_limits", None)
    if limits is None or not limits.enabled:
        return None
    return limits


def enforce_login_limit(request: Request, email: str) -> None:
    limits = _limits(request)
    if limits is None:
        return
    ip = get_client_ip(request, limits.trusted_proxy_hops)
    enforce(limits.login_ip, f"login-ip:{ip}", scope="login")
    enforce(limits.login_account, f"login-acc:{ip}:{_digest(email)}", scope="login")


def enforce_register_limit(request: Request) -> None:
    limits = _limits(request)
    if limits is None:
        return
    ip = get_client_ip(request, limits.trusted_proxy_hops)
    enforce(limits.register_ip, f"register-ip:{ip}", scope="register")


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RateLimitExceededError):
        raise exc
    logger.warning(
        "rate limit exceeded: scope=%s retry_after=%s path=%s",
        exc.scope,
        exc.retry_after_seconds,
        request.url.path,
    )
    body = {
        "type": "urn:scitracker:problem:rate-limit-exceeded",
        "title": "Too Many Requests",
        "status": 429,
        "detail": f"Too many attempts. Retry in {exc.retry_after_seconds} s.",
        "instance": request.url.path,
    }
    return JSONResponse(
        status_code=429,
        content=body,
        media_type="application/problem+json",
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


@dataclass(frozen=True, slots=True)
class RateLimitSettings:
    enabled: bool = True
    login_per_account: int = 5
    login_per_ip: int = 20
    login_window_seconds: int = 60
    register_per_ip: int = 5
    register_window_seconds: int = 600
    trusted_proxy_hops: int = 0

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> RateLimitSettings:
        def number(name: str, default: int, *, minimum: int) -> int:
            raw = env.get(name, str(default))
            try:
                value = int(raw)
            except ValueError as error:
                raise ValueError(f"{name} must be an integer, got {raw!r}") from error
            if value < minimum:
                raise ValueError(f"{name} must be >= {minimum}")
            return value

        enabled = env.get("RATE_LIMIT_ENABLED", "true").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        return cls(
            enabled=enabled,
            login_per_account=number("RATE_LIMIT_LOGIN_PER_ACCOUNT", 5, minimum=1),
            login_per_ip=number("RATE_LIMIT_LOGIN_PER_IP", 20, minimum=1),
            login_window_seconds=number("RATE_LIMIT_LOGIN_WINDOW_SECONDS", 60, minimum=1),
            register_per_ip=number("RATE_LIMIT_REGISTER_PER_IP", 5, minimum=1),
            register_window_seconds=number("RATE_LIMIT_REGISTER_WINDOW_SECONDS", 600, minimum=1),
            trusted_proxy_hops=number("RATE_LIMIT_TRUSTED_PROXY_HOPS", 0, minimum=0),
        )
