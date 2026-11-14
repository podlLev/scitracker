"""In-memory TTL cache: LRU eviction, single-flight, generation guard (ADR-012)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from scitracker.services.cache import CacheResult

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


@dataclass(frozen=True, slots=True)
class _Entry:
    value: Any
    expires_at: float


class InMemoryTtlCache:
    """Thread-safe cache. Cached values must be treated as immutable by callers."""

    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._ttl = float(ttl_seconds)
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._inflight: dict[str, tuple[threading.Lock, int]] = {}
        self._generation = 0
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get_or_compute[T](self, key: str, factory: Callable[[], T]) -> CacheResult[T]:
        cached = self._lookup(key)
        if cached is not None:
            return CacheResult(cached.value, hit=True)
        with self._single_flight(key):
            cached = self._lookup(key)
            if cached is not None:
                return CacheResult(cached.value, hit=True)
            generation = self._current_generation()
            value = factory()
            self._store(key, value, generation)
            return CacheResult(value, hit=False)

    def invalidate(self, namespace: str) -> None:
        prefix = f"{namespace}:"
        with self._lock:
            self._generation += 1
            for key in [k for k in self._entries if k.startswith(prefix)]:
                del self._entries[key]

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._entries.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def hits(self) -> int:
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        with self._lock:
            return self._misses

    def _lookup(self, key: str) -> _Entry | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return entry

    def _current_generation(self) -> int:
        with self._lock:
            return self._generation

    def _store(self, key: str, value: object, generation: int) -> None:
        with self._lock:
            self._misses += 1
            if generation != self._generation:
                return  # invalidated while computing: do not store a possibly stale value
            self._entries[key] = _Entry(value, self._clock() + self._ttl)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    @contextmanager
    def _single_flight(self, key: str) -> Iterator[None]:
        with self._lock:
            lock, users = self._inflight.get(key, (threading.Lock(), 0))
            self._inflight[key] = (lock, users + 1)
        try:
            with lock:
                yield
        finally:
            with self._lock:
                lock, users = self._inflight[key]
                if users <= 1:
                    del self._inflight[key]
                else:
                    self._inflight[key] = (lock, users - 1)


class NullCache:
    """Used when caching is disabled: always computes."""

    def get_or_compute[T](self, key: str, factory: Callable[[], T]) -> CacheResult[T]:
        return CacheResult(factory(), hit=False)

    def invalidate(self, namespace: str) -> None:
        return None

    def clear(self) -> None:
        return None
