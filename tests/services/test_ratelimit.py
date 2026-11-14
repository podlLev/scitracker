import pytest

from scitracker.services.ratelimit import (
    RateLimitDecision,
    RateLimitExceededError,
    enforce,
)


class _Stub:
    def __init__(self, decision: RateLimitDecision) -> None:
        self.decision = decision
        self.keys: list[str] = []

    def hit(self, key: str) -> RateLimitDecision:
        self.keys.append(key)
        return self.decision


def test_enforce_passes_when_allowed() -> None:
    stub = _Stub(RateLimitDecision(True, 0, 4))
    enforce(stub, "k", scope="login")
    assert stub.keys == ["k"]


def test_enforce_raises_with_scope_and_retry_after() -> None:
    stub = _Stub(RateLimitDecision(False, 42, 0))
    with pytest.raises(RateLimitExceededError) as info:
        enforce(stub, "k", scope="login")
    assert info.value.scope == "login"
    assert info.value.retry_after_seconds == 42
    assert "login" in str(info.value)
