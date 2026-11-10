import pytest

from scitracker.domain.errors import DuplicateRecordError
from scitracker.domain.publication import Publication
from scitracker.domain.topic import Topic
from scitracker.services.collection import (
    CollectionReport,
    FetchedTopic,
    SourceReport,
    collect_topics,
    run_failed,
    store_topic,
)
from scitracker.services.ports import SourceResult
from tests.services.fakes import InMemoryPublicationRepository, StubSource


class CountingSource(StubSource):
    def __init__(self, name: str, publications: list[Publication]) -> None:
        super().__init__(name, publications)
        self.calls = 0

    async def search(self, query: str, *, limit: int = 50) -> SourceResult:
        self.calls += 1
        return await super().search(query, limit=limit)


def pub(doi: str) -> Publication:
    return Publication(title=f"Paper {doi}", authors=[], doi=doi)


async def test_topics_with_the_same_query_share_one_round_of_requests() -> None:
    source = CountingSource("arxiv", [pub("10.1000/a")])
    repo = InMemoryPublicationRepository()
    topics = [
        Topic(name="A", query="Graph   Networks", id=1),
        Topic(name="B", query="graph networks", id=2),
    ]
    reports = await collect_topics(
        [source], topics, lambda topic, fetched: store_topic(repo, topic, fetched)
    )
    assert source.calls == 1
    first, second = reports
    assert (first.created, first.new_links) == (1, 1)
    assert (second.created, second.unchanged, second.new_links) == (0, 1, 1)


async def test_a_topic_that_cannot_be_stored_does_not_stop_the_others() -> None:
    repo = InMemoryPublicationRepository()

    def store(topic: Topic, fetched: FetchedTopic) -> CollectionReport:
        if topic.id == 1:
            raise DuplicateRecordError("clash")
        return store_topic(repo, topic, fetched)

    topics = [Topic(name="Bad", query="a", id=1), Topic(name="Good", query="b", id=2)]
    reports = await collect_topics([StubSource("arxiv", [pub("10.1000/a")])], topics, store)
    assert reports[0].error == "clash"
    assert "error='clash'" in reports[0].summary()
    assert reports[1].created == 1
    assert run_failed(reports)


def report(*, failed: tuple[bool, ...], error: str | None = None) -> CollectionReport:
    sources = [
        SourceReport(f"s{n}", error="down" if down else None) for n, down in enumerate(failed)
    ]
    return CollectionReport("t", sources, error=error)


@pytest.mark.parametrize(
    ("reports", "expected"),
    [
        ([], False),
        ([report(failed=(False, False))], False),
        ([report(failed=(True, False))], False),  # one source is enough
        ([report(failed=(True, True))], True),
        ([report(failed=(True, True)), report(failed=(False, True))], False),
        ([report(failed=(False,), error="x")], True),
    ],
)
def test_run_failed(reports: list[CollectionReport], expected: bool) -> None:
    assert run_failed(reports) is expected
