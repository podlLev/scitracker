from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx

from scitracker.sources.http import HttpFetcher, RateLimiter, RetryPolicy

FAST = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0, timeout=1.0)


class FakeTime:
    """Deterministic clock: sleeping advances time instantly."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@asynccontextmanager
async def fetcher_for(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    fake: FakeTime | None = None,
    policy: RetryPolicy = FAST,
) -> AsyncIterator[HttpFetcher]:
    fake = fake or FakeTime()
    limiter = RateLimiter(0, clock=fake.clock, sleep=fake.sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        yield HttpFetcher(client, source="test", policy=policy, limiter=limiter, sleep=fake.sleep)
