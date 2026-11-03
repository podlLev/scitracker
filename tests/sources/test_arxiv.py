import httpx
import pytest

from scitracker.services.errors import SourceError
from scitracker.sources.arxiv import ArxivSource, parse_feed
from tests.sources.helpers import fetcher_for

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is
      All You Need</title>
    <summary>  The dominant   models...  </summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <arxiv:doi>https://doi.org/10.1000/ABC</arxiv:doi>
    <link href="http://arxiv.org/pdf/1706.03762v7" rel="related"/>
    <link href="http://arxiv.org/abs/1706.03762v7" rel="alternate" type="text/html"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2101.00001v1</id>
    <published>2021-01-01T00:00:00Z</published>
    <title>No DOI paper</title>
    <author><name>Ann Lee</name></author>
    <arxiv:doi>not-a-doi</arxiv:doi>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2101.00002v1</id>
    <published>2021-01-01T00:00:00Z</published>
    <author><name>No Title</name></author>
  </entry>
  <entry>
    <id>garbage</id>
    <published>2021-01-01T00:00:00Z</published>
    <title>Bad id</title>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2101.00003v1</id>
    <published>2021-01-01T00:00:00Z</published>
    <title>No alternate link paper</title>
    <author><name>John Doe</name></author>
    <link href="http://arxiv.org/pdf/2101.00003v1" rel="related"/>
  </entry>
</feed>"""


def test_parse_feed_normalizes_records_and_counts_rejected() -> None:
    result = parse_feed(FEED)
    assert result.rejected == 2  # missing title, invalid arXiv ID
    first, second, third = result.publications
    assert first.title == "Attention Is All You Need"
    assert first.arxiv_id == "1706.03762"  # version stripped
    assert first.doi == "10.1000/abc"
    assert first.abstract == "The dominant models..."
    assert [a.name for a in first.authors] == ["Ashish Vaswani", "Noam Shazeer"]
    assert str(first.published_on) == "2017-06-12"
    assert first.url == "http://arxiv.org/abs/1706.03762v7"
    assert second.doi is None  # an invalid DOI is dropped, the record is kept
    assert third.url is None  # missing alternate link resolves to None


def test_empty_feed_gives_empty_result() -> None:
    result = parse_feed('<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
    assert result.publications == []
    assert result.rejected == 0


def test_invalid_xml_raises_source_error() -> None:
    with pytest.raises(SourceError, match="XML"):
        parse_feed("<feed>")


async def test_search_sends_expected_query() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, text=FEED)

    async with fetcher_for(handler) as fetcher:
        result = await ArxivSource(fetcher).search("graph neural networks", limit=5)
    assert seen["search_query"] == 'all:"graph neural networks"'
    assert seen["max_results"] == "5"
    assert len(result.publications) == 3
