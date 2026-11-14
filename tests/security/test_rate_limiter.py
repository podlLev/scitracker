from concurrent.futures import ThreadPoolExecutor

import pytest

from scitracker.security.rate_limiter import InMemorySlidingWindowLimiter


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_allows_up_to_limit_then_denies() -> None:
    limiter = InMemorySlidingWindowLimiter(limit=3, window_seconds=60, clock=FakeClock())
    assert [limiter.hit("a").allowed for _ in range(4)] == [True, True, True, False]


def test_remaining_counts_down() -> None:
    limiter = InMemorySlidingWindowLimiter(limit=3, window_seconds=60, clock=FakeClock())
    assert [limiter.hit("a").remaining for _ in range(3)] == [2, 1, 0]


def test_denied_decision_has_zero_remaining() -> None:
    limiter = InMemorySlidingWindowLimiter(limit=1, window_seconds=60, clock=FakeClock())
    limiter.hit("a")
    denied = limiter.hit("a")
    assert denied.allowed is False
    assert denied.remaining == 0


def test_window_slides_and_allows_again() -> None:
    clock = FakeClock()
    limiter = InMemorySlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)
    assert limiter.hit("a").allowed
    clock.advance(10)
    assert limiter.hit("a").allowed
    assert not limiter.hit("a").allowed
    clock.advance(50)  # перша спроба вийшла з вікна рівно зараз
    assert limiter.hit("a").allowed
    assert not limiter.hit("a").allowed


def test_retry_after_rounds_up_and_is_at_least_one() -> None:
    clock = FakeClock()
    limiter = InMemorySlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("a")
    clock.advance(20)
    assert limiter.hit("a").retry_after_seconds == 40
    clock.advance(39.5)
    assert limiter.hit("a").retry_after_seconds == 1


def test_denied_attempts_do_not_extend_block() -> None:
    clock = FakeClock()
    limiter = InMemorySlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("a")
    clock.advance(20)
    assert limiter.hit("a").retry_after_seconds == 40
    clock.advance(1)
    assert limiter.hit("a").retry_after_seconds == 39
    clock.advance(39)
    assert limiter.hit("a").allowed


def test_keys_are_independent() -> None:
    limiter = InMemorySlidingWindowLimiter(limit=1, window_seconds=60, clock=FakeClock())
    assert limiter.hit("a").allowed
    assert not limiter.hit("a").allowed
    assert limiter.hit("b").allowed


def test_memory_is_bounded() -> None:
    limiter = InMemorySlidingWindowLimiter(
        limit=1, window_seconds=60, clock=FakeClock(), max_keys=3
    )
    for index in range(10):
        limiter.hit(f"k{index}")
    assert limiter.tracked_keys() <= 3


def test_current_key_survives_eviction() -> None:
    limiter = InMemorySlidingWindowLimiter(
        limit=1, window_seconds=60, clock=FakeClock(), max_keys=2
    )
    for index in range(5):
        limiter.hit(f"k{index}")
    assert not limiter.hit("k4").allowed  # лічильник останнього ключа не втрачено


def test_expired_keys_are_swept() -> None:
    clock = FakeClock()
    limiter = InMemorySlidingWindowLimiter(limit=1, window_seconds=60, clock=clock, max_keys=2)
    limiter.hit("a")
    limiter.hit("b")
    clock.advance(120)
    limiter.hit("c")
    assert limiter.tracked_keys() == 1


@pytest.mark.parametrize(
    ("limit", "window", "max_keys", "match"),
    [(0, 60, 10, "limit"), (1, 0, 10, "window_seconds"), (1, 60, 0, "max_keys")],
)
def test_invalid_arguments_rejected(limit: int, window: float, max_keys: int, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        InMemorySlidingWindowLimiter(limit=limit, window_seconds=window, max_keys=max_keys)


def test_concurrent_hits_never_exceed_limit() -> None:
    limiter = InMemorySlidingWindowLimiter(limit=50, window_seconds=60)
    with ThreadPoolExecutor(max_workers=16) as pool:
        decisions = list(pool.map(lambda _: limiter.hit("shared"), range(200)))
    assert sum(1 for decision in decisions if decision.allowed) == 50
