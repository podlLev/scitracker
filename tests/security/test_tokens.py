from datetime import UTC, datetime, timedelta

import jwt
import pytest

from scitracker.domain.errors import AuthenticationError
from scitracker.security.tokens import JwtTokenService

SECRET = "a" * 40
SERVICE = JwtTokenService(SECRET)


def test_roundtrip() -> None:
    assert SERVICE.verify(SERVICE.issue(42)) == 42
    assert SERVICE.ttl_seconds == 1800


def test_short_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="at least"):
        JwtTokenService("short")


def test_expired_token_is_rejected() -> None:
    old = JwtTokenService(SECRET, clock=lambda: datetime(2020, 1, 1, tzinfo=UTC))
    with pytest.raises(AuthenticationError):
        SERVICE.verify(old.issue(1))


def test_token_signed_with_another_secret_is_rejected() -> None:
    with pytest.raises(AuthenticationError):
        SERVICE.verify(JwtTokenService("b" * 40).issue(1))


def test_unsigned_token_is_rejected() -> None:
    exp = datetime.now(UTC) + timedelta(hours=1)
    forged = jwt.encode({"sub": "1", "exp": exp}, "", algorithm="none")
    with pytest.raises(AuthenticationError):
        SERVICE.verify(forged)


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
def test_malformed_tokens_are_rejected(token: str) -> None:
    with pytest.raises(AuthenticationError):
        SERVICE.verify(token)


def test_non_numeric_subject_is_rejected() -> None:
    exp = datetime.now(UTC) + timedelta(hours=1)
    token = jwt.encode({"sub": "abc", "exp": exp}, SECRET, algorithm="HS256")
    with pytest.raises(AuthenticationError):
        SERVICE.verify(token)
