"""Обмежувач частоти в пам'яті: ковзне вікно (ADR-011)."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

from scitracker.services.ratelimit import RateLimitDecision

if TYPE_CHECKING:
    from collections.abc import Callable


class InMemorySlidingWindowLimiter:
    """Потокобезпечний лічильник спроб за ключем.

    Відхилені спроби не записуються, тож блокування не продовжується
    самими запитами під час блокування.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        if max_keys < 1:
            raise ValueError("max_keys must be >= 1")
        self._limit = limit
        self._window = float(window_seconds)
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> RateLimitDecision:
        with self._lock:
            now = self._clock()
            window = self._hits.get(key)
            if window is None:
                window = deque()
                self._hits[key] = window
            self._drop_expired(window, now)
            if len(window) >= self._limit:
                retry = math.ceil(window[0] + self._window - now)
                return RateLimitDecision(False, max(1, retry), 0)
            window.append(now)
            if len(self._hits) > self._max_keys:
                self._shrink(now, keep=key)
            return RateLimitDecision(True, 0, self._limit - len(window))

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._hits)

    def _drop_expired(self, window: deque[float], now: float) -> None:
        cutoff = now - self._window
        while window and window[0] <= cutoff:
            window.popleft()

    def _shrink(self, now: float, *, keep: str) -> None:
        """Drop expired keys first, then the oldest inserted ones."""
        cutoff = now - self._window
        for key in [k for k, w in self._hits.items() if not w or w[-1] <= cutoff]:
            if key != keep:
                del self._hits[key]
        for key in list(self._hits):
            if len(self._hits) <= self._max_keys:
                break
            if key != keep:
                del self._hits[key]
