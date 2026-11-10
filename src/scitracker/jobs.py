import asyncio
from typing import TYPE_CHECKING

from scitracker.domain.topic import Topic
from scitracker.services.collection import (
    CollectionReport,
    FetchedTopic,
    collect_topics,
    store_topic,
)
from scitracker.sources.arxiv import ARXIV_MIN_INTERVAL, ArxivSource
from scitracker.sources.crossref import CROSSREF_MIN_INTERVAL, CrossrefSource
from scitracker.sources.http import HttpFetcher, RateLimiter, create_http_client
from scitracker.storage.database import SessionFactory
from scitracker.storage.repositories import SqlPublicationRepository, SqlTopicRepository

if TYPE_CHECKING:
    from scitracker.services.ports import PublicationSource


async def _collect(
    session_factory: SessionFactory, limit: int, mailto: str | None
) -> list[CollectionReport]:
    async with create_http_client(mailto=mailto) as client:
        # Order matters: the record stored first wins when the sources disagree (ADR-003).
        sources: list[PublicationSource] = [
            CrossrefSource(
                HttpFetcher(client, source="crossref", limiter=RateLimiter(CROSSREF_MIN_INTERVAL)),
                mailto=mailto,
            ),
            ArxivSource(
                HttpFetcher(client, source="arxiv", limiter=RateLimiter(ARXIV_MIN_INTERVAL))
            ),
        ]
        with session_factory() as session:
            topics = SqlTopicRepository(session).list_all()

        def store(topic: Topic, fetched: FetchedTopic) -> CollectionReport:
            with session_factory() as session, session.begin():  # short transaction per topic
                return store_topic(SqlPublicationRepository(session), topic, fetched)

        return await collect_topics(sources, topics, store, limit=limit)


def run_collection(
    session_factory: SessionFactory, *, limit: int, mailto: str | None
) -> list[CollectionReport]:
    return asyncio.run(_collect(session_factory, limit, mailto))
