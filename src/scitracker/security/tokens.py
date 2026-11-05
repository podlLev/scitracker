from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from scitracker.domain.errors import AuthenticationError

MIN_SECRET_LENGTH = 32
_ALGORITHM = "HS256"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class JwtTokenService:
    def __init__(
        self,
        secret: str,
        *,
        ttl: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if len(secret) < MIN_SECRET_LENGTH:
            raise ValueError(f"JWT secret must be at least {MIN_SECRET_LENGTH} characters")
        self._secret = secret
        self._ttl = ttl
        self._clock = clock

    @property
    def ttl_seconds(self) -> int:
        return int(self._ttl.total_seconds())

    def issue(self, user_id: int) -> str:
        now = self._clock()
        payload: dict[str, Any] = {"sub": str(user_id), "iat": now, "exp": now + self._ttl}
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def verify(self, token: str) -> int:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],  # a fixed list: "alg: none" tokens are rejected
                options={"require": ["exp", "sub"]},
            )
            return int(claims["sub"])
        except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
            raise AuthenticationError("Invalid or expired token.") from exc
