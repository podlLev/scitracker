import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum

from scitracker.domain.errors import DuplicateRecordError
from scitracker.domain.merge import merge_publications
from scitracker.domain.publication import Publication
from scitracker.services.ports import PublicationRepository

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2  # the second one handles a concurrent insert of the same publication


class IngestOutcome(StrEnum):
    CREATED = "created"
    MERGED = "merged"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class IngestResult:
    outcome: IngestOutcome
    publication: Publication | None = None


def ingest_publication(repo: PublicationRepository, incoming: Publication) -> IngestResult:
    """Store the publication, merging it with an existing record of the same work."""
    for _ in range(_MAX_ATTEMPTS):
        matches = repo.find_all_by_identifiers(doi=incoming.doi, arxiv_id=incoming.arxiv_id)
        if len(matches) > 1:
            logger.warning(
                "ingest: doi=%s arxiv_id=%s match %d different publications, record skipped",
                incoming.doi,
                incoming.arxiv_id,
                len(matches),
            )
            return IngestResult(IngestOutcome.CONFLICT)
        try:
            if not matches:
                return IngestResult(IngestOutcome.CREATED, repo.add(incoming))
            existing = matches[0]
            merged = merge_publications(existing, incoming)
            if merged == existing:
                return IngestResult(IngestOutcome.UNCHANGED, existing)
            return IngestResult(IngestOutcome.MERGED, repo.update(merged))
        except DuplicateRecordError:
            continue  # someone inserted it concurrently: look again and merge
    raise DuplicateRecordError("publication keeps clashing with concurrent writers")


def ingest_stream(
    repo: PublicationRepository, publications: Iterable[Publication]
) -> Iterator[IngestResult]:
    """Lazy stage: a record is stored only when the consumer asks for its result."""
    for publication in publications:
        yield ingest_publication(repo, publication)
