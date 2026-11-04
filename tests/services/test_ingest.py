from datetime import date

import pytest

from scitracker.domain.errors import DuplicateRecordError
from scitracker.domain.publication import Author, Publication
from scitracker.services.ingest import IngestOutcome, ingest_publication, ingest_stream
from tests.services.fakes import InMemoryPublicationRepository


def make(
    *,
    title: str = "Title",
    authors: list[Author] | None = None,
    doi: str | None = "10.1000/a",
    arxiv_id: str | None = None,
    abstract: str | None = None,
    published_on: date | None = None,
) -> Publication:
    return Publication(
        title=title,
        authors=authors or [],
        doi=doi,
        arxiv_id=arxiv_id,
        abstract=abstract,
        published_on=published_on,
    )


def test_new_publication_is_created() -> None:
    repo = InMemoryPublicationRepository()
    result = ingest_publication(repo, make())
    assert result.outcome is IngestOutcome.CREATED
    assert result.publication is not None
    assert result.publication.id is not None


def test_same_doi_is_merged_not_duplicated() -> None:
    repo = InMemoryPublicationRepository()
    ingest_publication(repo, make(abstract=None))
    result = ingest_publication(repo, make(abstract="Filled in"))
    assert result.outcome is IngestOutcome.MERGED
    assert repo.count() == 1
    assert result.publication is not None
    assert result.publication.abstract == "Filled in"


def test_arxiv_only_and_doi_only_records_meet_through_the_arxiv_doi() -> None:
    repo = InMemoryPublicationRepository()
    ingest_publication(repo, make(doi=None, arxiv_id="1706.03762"))
    result = ingest_publication(repo, make(doi="10.48550/arXiv.1706.03762"))
    assert result.outcome is IngestOutcome.MERGED  # the DOI is a new fact: it fills the gap
    assert repo.count() == 1
    assert result.publication is not None
    assert result.publication.doi == "10.48550/arxiv.1706.03762"
    assert result.publication.arxiv_id == "1706.03762"


def test_record_with_both_identifiers_enriches_an_arxiv_only_record() -> None:
    repo = InMemoryPublicationRepository()
    ingest_publication(repo, make(doi=None, arxiv_id="2101.00001"))
    result = ingest_publication(repo, make(doi="10.1000/z", arxiv_id="2101.00001"))
    assert result.outcome is IngestOutcome.MERGED
    assert result.publication is not None
    assert result.publication.doi == "10.1000/z"
    assert repo.count() == 1


def test_repeating_the_same_record_changes_nothing() -> None:
    repo = InMemoryPublicationRepository()
    ingest_publication(repo, make(authors=[Author("Ann Lee")]))
    result = ingest_publication(repo, make(authors=[Author("Ann Lee")]))
    assert result.outcome is IngestOutcome.UNCHANGED
    assert repo.count() == 1


def test_identifiers_matching_two_publications_are_a_conflict() -> None:
    repo = InMemoryPublicationRepository()
    ingest_publication(repo, make(doi="10.1000/x"))
    ingest_publication(repo, make(doi=None, arxiv_id="2101.00001"))
    result = ingest_publication(repo, make(doi="10.1000/x", arxiv_id="2101.00001"))
    assert result.outcome is IngestOutcome.CONFLICT
    assert result.publication is None
    assert repo.count() == 2


class RacyRepository(InMemoryPublicationRepository):
    """A competitor inserts the same publication between our lookup and our insert."""

    def __init__(self, rival: Publication) -> None:
        super().__init__()
        self._rival: Publication | None = rival

    def add(self, publication: Publication) -> Publication:
        if self._rival is not None:
            rival, self._rival = self._rival, None
            super().add(rival)
            raise DuplicateRecordError("concurrent insert")
        return super().add(publication)


def test_concurrent_insert_is_resolved_by_merging() -> None:
    repo = RacyRepository(rival=make(abstract=None))
    result = ingest_publication(repo, make(abstract="Mine"))
    assert result.outcome is IngestOutcome.MERGED
    assert repo.count() == 1


def test_stream_is_lazy() -> None:
    repo = InMemoryPublicationRepository()
    stream = ingest_stream(repo, iter([make(doi="10.1000/a"), make(doi="10.1000/b")]))
    assert repo.count() == 0  # nothing happens until the consumer asks
    next(stream)
    assert repo.count() == 1


class AlwaysClashingRepository(InMemoryPublicationRepository):
    def add(self, publication: Publication) -> Publication:
        raise DuplicateRecordError("always")


def test_persistent_clash_raises_after_retry() -> None:
    with pytest.raises(DuplicateRecordError, match="keeps clashing"):
        ingest_publication(AlwaysClashingRepository(), make())
