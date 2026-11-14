"""Порт обмеження частоти запитів (ADR-011). Лише stdlib."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    remaining: int


class RateLimiter(Protocol):
    def hit(self, key: str) -> RateLimitDecision:
        """Record an attempt for the key and return the decision."""
        ...


class RateLimitExceededError(Exception):
    def __init__(self, scope: str, retry_after_seconds: int) -> None:
        super().__init__(f"rate limit exceeded: {scope}")
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds


def enforce(limiter: RateLimiter, key: str, *, scope: str) -> None:
    decision = limiter.hit(key)
    if not decision.allowed:
        raise RateLimitExceededError(scope, decision.retry_after_seconds)
