import logging

import pytest

from scitracker.domain.publication import Publication
from scitracker.domain.topic import Topic
from scitracker.services.collection import FetchedTopic, fetch_topic, store_topic
from tests.services.fakes import InMemoryPublicationRepository, StubSource, unavailable

TOPIC = Topic(name="GNN", query="graph neural networks", id=1)


def pub(doi: str) -> Publication:
    return Publication(title=f"Paper {doi}", authors=[], doi=doi)


async def test_failed_source_is_reported_and_the_other_one_still_works(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sources = [unavailable("crossref"), StubSource("arxiv", [pub("10.1000/a")], rejected=2)]
    with caplog.at_level(logging.WARNING, logger="scitracker.services.collection"):
        fetched = await fetch_topic(sources, TOPIC)
    repo = InMemoryPublicationRepository()
    report = store_topic(repo, TOPIC, fetched)
    assert report.failed_sources == ["crossref"]
    assert report.rejected == 2
    assert report.created == 1
    assert repo.count() == 1
    assert "crossref failed" in caplog.text


async def test_unexpected_errors_are_not_swallowed() -> None:
    broken = StubSource("arxiv", error=RuntimeError("bug"))
    with pytest.raises(RuntimeError, match="bug"):
        await fetch_topic([broken], TOPIC)


async def test_records_from_both_sources_are_counted_and_linked() -> None:
    fetched = await fetch_topic(
        [
            StubSource("crossref", [pub("10.1000/a"), pub("10.1000/b")]),
            StubSource("arxiv", [pub("10.1000/a")]),
        ],
        TOPIC,
    )
    repo = InMemoryPublicationRepository()
    report = store_topic(repo, TOPIC, fetched)
    assert (report.created, report.unchanged, report.new_links) == (2, 1, 2)
    assert "created=2" in report.summary()


async def test_repeated_collection_adds_nothing() -> None:
    fetched = await fetch_topic([StubSource("crossref", [pub("10.1000/a")])], TOPIC)
    repo = InMemoryPublicationRepository()
    store_topic(repo, TOPIC, fetched)
    second = store_topic(repo, TOPIC, fetched)
    assert (second.created, second.new_links, second.unchanged) == (0, 0, 1)


def test_topic_must_be_persisted() -> None:
    with pytest.raises(ValueError, match="persisted"):
        store_topic(
            InMemoryPublicationRepository(),
            Topic(name="x", query="x"),
            FetchedTopic([], []),
        )
