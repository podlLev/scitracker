import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import httpx

from scitracker import __version__
from scitracker.services.errors import SourceError

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    timeout: float = 10.0


class RateLimiter:
    """Guarantees a minimum interval between consecutive requests."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._next_slot = float("-inf")
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            delay = self._next_slot - now
            if delay > 0:
                await self._sleep(delay)
            self._next_slot = max(now, self._next_slot) + self._min_interval


def create_http_client(*, mailto: str | None = None) -> httpx.AsyncClient:
    agent = f"scitracker/{__version__}"
    if mailto:
        agent += f" (mailto:{mailto})"
    return httpx.AsyncClient(headers={"User-Agent": agent}, follow_redirects=True)


def ensure_limit(limit: int) -> int:
    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    return limit


class HttpFetcher:
    """GET with timeout, rate limiting and retries with exponential backoff."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        source: str,
        policy: RetryPolicy | None = None,
        limiter: RateLimiter | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._client = client
        self._source = source
        self._policy = policy or RetryPolicy()
        self._limiter = limiter or RateLimiter(0)
        self._sleep = sleep

    async def get(self, url: str, params: Mapping[str, str | int]) -> httpx.Response:
        attempts = self._policy.max_attempts
        reason = "no attempts made"
        cause: Exception | None = None
        for attempt in range(1, attempts + 1):
            await self._limiter.wait()
            delay = self._backoff(attempt)
            try:
                response = await self._client.get(url, params=params, timeout=self._policy.timeout)
            except httpx.TransportError as exc:  # includes timeouts
                cause, reason = exc, f"network error: {exc!r}"
            else:
                status = response.status_code
                if status < 400:
                    return response
                if status not in RETRYABLE_STATUSES:
                    raise SourceError(self._source, f"HTTP {status}")
                cause, reason = None, f"HTTP {status}"
                delay = self._retry_after(response) or delay
            if attempt < attempts:
                logger.warning(
                    "%s: %s, retry %d/%d in %.1fs",
                    self._source,
                    reason,
                    attempt,
                    attempts - 1,
                    delay,
                )
                await self._sleep(delay)
        raise SourceError(self._source, f"giving up after {attempts} attempts: {reason}") from cause

    def _backoff(self, attempt: int) -> float:
        return float(min(self._policy.max_delay, self._policy.base_delay * 2 ** (attempt - 1)))

    def _retry_after(self, response: httpx.Response) -> float | None:
        try:
            seconds: float = float(response.headers["Retry-After"])
        except (KeyError, ValueError):
            return None  # absent or an HTTP-date: fall back to backoff
        return float(min(max(seconds, 0.0), self._policy.max_delay))
