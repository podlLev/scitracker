import pytest

from scitracker.sources.arxiv import ARXIV_MIN_INTERVAL, ArxivSource
from scitracker.sources.crossref import CROSSREF_MIN_INTERVAL, CrossrefSource
from scitracker.sources.http import HttpFetcher, RateLimiter, create_http_client

pytestmark = pytest.mark.live


async def test_arxiv_live() -> None:
    async with create_http_client() as client:
        fetcher = HttpFetcher(client, source="arxiv", limiter=RateLimiter(ARXIV_MIN_INTERVAL))
        result = await ArxivSource(fetcher).search("graph neural networks", limit=20)
        assert result.publications


async def test_crossref_live() -> None:
    async with create_http_client(mailto="sk8e.staff@gmail.com") as client:
        fetcher = HttpFetcher(client, source="crossref", limiter=RateLimiter(CROSSREF_MIN_INTERVAL))
        source = CrossrefSource(fetcher, mailto="sk8e.staff@gmail.com")
        result = await source.search("graph neural networks", limit=50)
        assert result.publications
