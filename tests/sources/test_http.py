import httpx
import pytest

from scitracker.services.errors import SourceError
from scitracker.sources.http import RateLimiter, create_http_client, ensure_limit
from tests.sources.helpers import FakeTime, fetcher_for

URL = "https://example.test/api"


async def test_successful_response_is_returned() -> None:
    async with fetcher_for(lambda request: httpx.Response(200, text="ok")) as fetcher:
        response = await fetcher.get(URL, {"q": "x"})
    assert response.text == "ok"


async def test_server_errors_are_retried_with_exponential_backoff() -> None:
    statuses = iter([503, 503, 200])
    fake = FakeTime()
    async with fetcher_for(lambda r: httpx.Response(next(statuses)), fake=fake) as fetcher:
        response = await fetcher.get(URL, {})
    assert response.status_code == 200
    assert fake.sleeps == [1.0, 2.0]


async def test_gives_up_after_max_attempts() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    fake = FakeTime()
    async with fetcher_for(handler, fake=fake) as fetcher:
        with pytest.raises(SourceError, match="503"):
            await fetcher.get(URL, {})
    assert calls == 3
    assert fake.sleeps == [1.0, 2.0]  # no pause after the last attempt


async def test_retry_after_header_is_respected_and_capped() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(429, headers={"Retry-After": "999"}),
            httpx.Response(200),
        ]
    )
    fake = FakeTime()
    async with fetcher_for(lambda r: next(responses), fake=fake) as fetcher:
        await fetcher.get(URL, {})
    assert fake.sleeps == [7.0, 30.0]


async def test_client_errors_are_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    async with fetcher_for(handler) as fetcher:
        with pytest.raises(SourceError, match="404"):
            await fetcher.get(URL, {})
    assert calls == 1


async def test_network_errors_are_retried_and_keep_the_cause() -> None:
    def always_down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    async with fetcher_for(always_down) as fetcher:
        with pytest.raises(SourceError) as info:
            await fetcher.get(URL, {})
    assert isinstance(info.value.__cause__, httpx.ConnectError)


async def test_network_error_then_success() -> None:
    state = {"failed": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if not state["failed"]:
            state["failed"] = True
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200)

    async with fetcher_for(handler) as fetcher:
        response = await fetcher.get(URL, {})
    assert response.status_code == 200


async def test_rate_limiter_enforces_minimum_interval() -> None:
    fake = FakeTime()
    limiter = RateLimiter(3.0, clock=fake.clock, sleep=fake.sleep)
    await limiter.wait()
    await limiter.wait()
    await limiter.wait()
    assert fake.sleeps == [3.0, 3.0]


def test_ensure_limit_rejects_out_of_range_values() -> None:
    assert ensure_limit(10) == 10
    for bad in (0, 101):
        with pytest.raises(ValueError, match="limit"):
            ensure_limit(bad)


async def test_create_http_client_without_mailto() -> None:
    async with create_http_client() as client:
        assert "mailto:" not in client.headers["User-Agent"]


async def test_create_http_client_with_mailto() -> None:
    async with create_http_client(mailto="researcher@example.com") as client:
        assert "mailto:researcher@example.com" in client.headers["User-Agent"]
