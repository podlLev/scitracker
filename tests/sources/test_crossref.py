from typing import Any

import httpx
import pytest

from scitracker.services.errors import SourceError
from scitracker.sources.crossref import CrossrefSource, parse_works
from tests.sources.helpers import fetcher_for

PAYLOAD: dict[str, Any] = {
    "message": {
        "items": [
            {
                "DOI": "10.1000/ABC",
                "title": ["Deep <i>learning</i> &amp; more"],
                "author": [
                    {"given": "Ann", "family": "Lee"},
                    {"name": "Research Consortium"},
                    {},
                ],
                "abstract": "<jats:p>Short   abstract.</jats:p>",
                "issued": {"date-parts": [[2021, 3]]},
                "URL": "https://doi.org/10.1000/abc",
            },
            {"DOI": "10.1000/nodate", "title": ["No date"], "issued": {"date-parts": [[None]]}},
            {"DOI": "10.1000/notitle", "title": []},
            {"title": ["No DOI"]},
            "not an object",
        ]
    }
}


def test_parse_works_cleans_markup_and_counts_rejected() -> None:
    result = parse_works(PAYLOAD)
    assert result.rejected == 3  # no title, no DOI, not an object
    first, second = result.publications
    assert first.doi == "10.1000/abc"
    assert first.title == "Deep learning & more"
    assert [a.name for a in first.authors] == ["Ann Lee", "Research Consortium"]
    assert first.abstract == "Short abstract."
    assert str(first.published_on) == "2021-03-01"
    assert second.published_on is None
    assert second.arxiv_id is None


@pytest.mark.parametrize("payload", [{}, {"message": {}}, {"message": {"items": "x"}}, []])
def test_unexpected_structure_raises_source_error(payload: object) -> None:
    with pytest.raises(SourceError, match="structure"):
        parse_works(payload)


async def test_search_sends_polite_pool_email_and_query() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json=PAYLOAD)

    async with fetcher_for(handler) as fetcher:
        source = CrossrefSource(fetcher, mailto="me@example.com")
        result = await source.search("machine learning", limit=20)
    assert seen["query"] == "machine learning"
    assert seen["rows"] == "20"
    assert seen["mailto"] == "me@example.com"
    assert len(result.publications) == 2


async def test_invalid_json_raises_source_error() -> None:
    async with fetcher_for(lambda r: httpx.Response(200, text="<html>")) as fetcher:
        with pytest.raises(SourceError, match="JSON"):
            await CrossrefSource(fetcher).search("x")
