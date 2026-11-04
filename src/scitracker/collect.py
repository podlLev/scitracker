import asyncio
import logging
import os
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, sessionmaker

from scitracker.services.collection import CollectionReport, fetch_topic, store_topic
from scitracker.sources.arxiv import ARXIV_MIN_INTERVAL, ArxivSource
from scitracker.sources.crossref import CROSSREF_MIN_INTERVAL, CrossrefSource
from scitracker.sources.http import HttpFetcher, RateLimiter, create_http_client
from scitracker.storage.database import create_db_engine, create_session_factory
from scitracker.storage.repositories import SqlPublicationRepository, SqlTopicRepository

logger = logging.getLogger(__name__)
if TYPE_CHECKING:
    from scitracker.services.ports import PublicationSource


async def collect_all(
    session_factory: sessionmaker[Session], *, limit: int = 50, mailto: str | None = None
) -> list[CollectionReport]:
    async with create_http_client(mailto=mailto) as client:
        # Order matters: the record stored first wins when the sources disagree.
        crossref: PublicationSource = CrossrefSource(
            HttpFetcher(client, source="crossref", limiter=RateLimiter(CROSSREF_MIN_INTERVAL)),
            mailto=mailto,
        )
        arxiv: PublicationSource = ArxivSource(
            HttpFetcher(client, source="arxiv", limiter=RateLimiter(ARXIV_MIN_INTERVAL))
        )
        sources = [crossref, arxiv]  # order matters: the record stored first wins
        with session_factory() as session:
            topics = SqlTopicRepository(session).list_all()
        reports: list[CollectionReport] = []
        for topic in topics:
            fetched = await fetch_topic(sources, topic, limit=limit)  # no DB connection held
            with session_factory() as session, session.begin():  # short transaction per topic
                reports.append(store_topic(SqlPublicationRepository(session), topic, fetched))
        return reports


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    engine = create_db_engine(os.environ["DATABASE_URL"])
    reports = asyncio.run(
        collect_all(create_session_factory(engine), mailto=os.environ.get("CROSSREF_MAILTO"))
    )
    for report in reports:
        logger.info("done: %s", report.summary())


if __name__ == "__main__":
    main()
