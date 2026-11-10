import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import chain

from scitracker.domain.errors import DomainError
from scitracker.domain.publication import Publication
from scitracker.domain.topic import Topic
from scitracker.services.errors import SourceError
from scitracker.services.ingest import IngestOutcome, ingest_stream
from scitracker.services.ports import PublicationRepository, PublicationSource

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SourceReport:
    source: str
    fetched: int = 0
    rejected: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FetchedTopic:
    reports: list[SourceReport]
    batches: list[list[Publication]]


@dataclass(slots=True)
class CollectionReport:
    topic: str
    sources: list[SourceReport]
    created: int = 0
    merged: int = 0
    unchanged: int = 0
    conflicts: int = 0
    new_links: int = 0
    error: str | None = None

    @property
    def rejected(self) -> int:
        return sum(report.rejected for report in self.sources)

    @property
    def failed_sources(self) -> list[str]:
        return [report.source for report in self.sources if report.error is not None]

    def summary(self) -> str:
        failed = ", ".join(self.failed_sources) or "none"
        text = (
            f"topic={self.topic!r} created={self.created} merged={self.merged} "
            f"unchanged={self.unchanged} conflicts={self.conflicts} "
            f"new_links={self.new_links} rejected={self.rejected} failed_sources={failed}"
        )
        return f"{text} error={self.error!r}" if self.error else text


async def fetch_topic(
    sources: Sequence[PublicationSource], topic: Topic, *, limit: int = 50
) -> FetchedTopic:
    """Query all sources concurrently. A failing source is reported, the others still count."""
    outcomes = await asyncio.gather(
        *(source.search(topic.query, limit=limit) for source in sources),
        return_exceptions=True,
    )
    reports: list[SourceReport] = []
    batches: list[list[Publication]] = []
    for source, outcome in zip(sources, outcomes, strict=True):
        report = SourceReport(source.name)
        reports.append(report)
        if isinstance(outcome, SourceError):
            report.error = str(outcome)
            logger.warning(
                "collection: %s failed for topic %r: %s", source.name, topic.name, outcome
            )
        elif isinstance(outcome, BaseException):
            raise outcome  # a bug, not an unavailable source: do not hide it
        else:
            report.fetched = len(outcome.publications)
            report.rejected = outcome.rejected
            batches.append(outcome.publications)
    return FetchedTopic(reports, batches)


def store_topic(
    repo: PublicationRepository, topic: Topic, fetched: FetchedTopic
) -> CollectionReport:
    """Deduplicate, store and link to the topic. The caller owns the transaction."""
    if topic.id is None:
        raise ValueError("topic must be persisted before collecting")
    report = CollectionReport(topic.name, fetched.reports)
    for result in ingest_stream(repo, chain.from_iterable(fetched.batches)):
        match result.outcome:
            case IngestOutcome.CREATED:
                report.created += 1
            case IngestOutcome.MERGED:
                report.merged += 1
            case IngestOutcome.UNCHANGED:
                report.unchanged += 1
            case IngestOutcome.CONFLICT:
                report.conflicts += 1
        publication = result.publication
        if (
            publication is not None
            and publication.id is not None
            and repo.link_topic(publication.id, topic.id)
        ):
            report.new_links += 1
    logger.info("collection: %s", report.summary())
    return report


Store = Callable[[Topic, FetchedTopic], CollectionReport]


async def collect_topics(
    sources: Sequence[PublicationSource],
    topics: Sequence[Topic],
    store: Store,
    *,
    limit: int = 50,
) -> list[CollectionReport]:
    """Collect every topic.

    Topics with the same query share one round of requests to the sources. A topic that
    cannot be stored is reported and does not stop the others.
    """
    fetched_by_query: dict[str, FetchedTopic] = {}
    reports: list[CollectionReport] = []
    for topic in topics:
        key = " ".join(topic.query.casefold().split())
        fetched = fetched_by_query.get(key)
        if fetched is None:
            fetched = await fetch_topic(sources, topic, limit=limit)
            fetched_by_query[key] = fetched
        try:
            reports.append(store(topic, fetched))
        except DomainError as exc:
            logger.error("collection: topic %r could not be stored: %s", topic.name, exc)
            reports.append(CollectionReport(topic.name, fetched.reports, error=str(exc)))
    return reports


def run_failed(reports: Sequence[CollectionReport]) -> bool:
    """True when a topic could not be stored, or every source failed for every topic."""
    if any(report.error for report in reports):
        return True
    return bool(reports) and all(
        bool(report.sources) and len(report.failed_sources) == len(report.sources)
        for report in reports
    )
