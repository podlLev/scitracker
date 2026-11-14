import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from scitracker.cache.memory import InMemoryTtlCache, NullCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Counter:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        return self.calls


def test_second_call_is_a_hit() -> None:
    cache = InMemoryTtlCache(ttl_seconds=60, clock=FakeClock())
    counter = Counter()
    first = cache.get_or_compute("k", counter)
    second = cache.get_or_compute("k", counter)
    assert (first.hit, second.hit) == (False, True)
    assert first.value == second.value == 1
    assert counter.calls == 1


def test_entry_expires_after_ttl() -> None:
    clock = FakeClock()
    cache = InMemoryTtlCache(ttl_seconds=60, clock=clock)
    counter = Counter()
    cache.get_or_compute("k", counter)
    clock.now += 59
    assert cache.get_or_compute("k", counter).hit is True
    clock.now += 2
    assert cache.get_or_compute("k", counter).hit is False
    assert counter.calls == 2


def test_keys_are_independent() -> None:
    cache = InMemoryTtlCache(ttl_seconds=60, clock=FakeClock())
    assert cache.get_or_compute("a", lambda: "A").value == "A"
    assert cache.get_or_compute("b", lambda: "B").value == "B"


def test_lru_evicts_least_recently_used() -> None:
    cache = InMemoryTtlCache(ttl_seconds=60, max_entries=2, clock=FakeClock())
    cache.get_or_compute("a", lambda: 1)
    cache.get_or_compute("b", lambda: 2)
    cache.get_or_compute("a", lambda: 1)  # touch a, so b is the oldest
    cache.get_or_compute("c", lambda: 3)
    assert cache.size() == 2
    assert cache.get_or_compute("a", lambda: 0).hit is True
    assert cache.get_or_compute("b", lambda: 0).hit is False


def test_invalidate_removes_only_matching_namespace() -> None:
    cache = InMemoryTtlCache(ttl_seconds=60, clock=FakeClock())
    cache.get_or_compute("stats:by-topic:x", lambda: 1)
    cache.get_or_compute("stats:top:y", lambda: 2)
    cache.get_or_compute("statsx:z", lambda: 3)
    cache.get_or_compute("topics:w", lambda: 4)
    cache.invalidate("stats")
    assert cache.get_or_compute("stats:by-topic:x", lambda: 0).hit is False
    assert cache.get_or_compute("stats:top:y", lambda: 0).hit is False
    assert cache.get_or_compute("statsx:z", lambda: 0).hit is True
    assert cache.get_or_compute("topics:w", lambda: 0).hit is True


def test_clear_drops_everything() -> None:
    cache = InMemoryTtlCache(ttl_seconds=60, clock=FakeClock())
    cache.get_or_compute("a", lambda: 1)
    cache.clear()
    assert cache.size() == 0


def test_factory_error_is_not_cached() -> None:
    cache = InMemoryTtlCache(ttl_seconds=60, clock=FakeClock())

    def boom() -> int:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        cache.get_or_compute("k", boom)
    result = cache.get_or_compute("k", lambda: 7)
    assert (result.value, result.hit) == (7, False)


def test_invalidation_during_compute_prevents_stale_store() -> None:
    cache = InMemoryTtlCache(ttl_seconds=60, clock=FakeClock())

    def factory() -> str:
        cache.invalidate("ns")  # data changed while we were computing
        return "old"

    result = cache.get_or_compute("ns:k", factory)
    assert (result.value, result.hit) == ("old", False)
    assert cache.size() == 0


def test_concurrent_misses_compute_once() -> None:
    cache = InMemoryTtlCache(ttl_seconds=60)
    guard = threading.Lock()
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def factory() -> str:
        nonlocal calls
        with guard:
            calls += 1
        started.set()
        release.wait(timeout=5)
        return "value"

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(cache.get_or_compute, "k", factory) for _ in range(8)]
        assert started.wait(timeout=5)
        release.set()
        results = [future.result(timeout=5) for future in futures]
    assert calls == 1
    assert sum(1 for result in results if result.hit) == 7


def test_counters() -> None:
    cache = InMemoryTtlCache(ttl_seconds=60, clock=FakeClock())
    cache.get_or_compute("k", lambda: 1)
    cache.get_or_compute("k", lambda: 1)
    cache.get_or_compute("k", lambda: 1)
    assert (cache.hits, cache.misses) == (2, 1)


@pytest.mark.parametrize(
    ("ttl", "max_entries", "match"),
    [(0, 10, "ttl_seconds"), (60, 0, "max_entries")],
)
def test_invalid_arguments_rejected(ttl: float, max_entries: int, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        InMemoryTtlCache(ttl_seconds=ttl, max_entries=max_entries)


def test_null_cache_always_computes() -> None:
    cache = NullCache()
    counter = Counter()
    assert cache.get_or_compute("k", counter).hit is False
    assert cache.get_or_compute("k", counter).hit is False
    assert counter.calls == 2
    cache.invalidate("k")
    cache.clear()
