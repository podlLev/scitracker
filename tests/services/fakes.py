from dataclasses import replace

from scitracker.domain.errors import DuplicateRecordError
from scitracker.domain.publication import Publication
from scitracker.services.errors import SourceError
from scitracker.services.ports import SourceResult


class InMemoryPublicationRepository:
    """Test double that honours the same uniqueness rules as the database."""

    def __init__(self) -> None:
        self._items: dict[int, Publication] = {}
        self._links: set[tuple[int, int]] = set()
        self._next_id = 1

    def _clashes(self, publication: Publication) -> bool:
        return any(
            (publication.doi is not None and other.doi == publication.doi)
            or (publication.arxiv_id is not None and other.arxiv_id == publication.arxiv_id)
            for other in self._items.values()
            if other.id != publication.id
        )

    def add(self, publication: Publication) -> Publication:
        if self._clashes(publication):
            raise DuplicateRecordError("duplicate identifier")
        new_id = self._next_id
        self._next_id += 1
        self._items[new_id] = replace(publication, id=new_id)
        return self._items[new_id]

    def update(self, publication: Publication) -> Publication:
        assert publication.id is not None
        if self._clashes(publication):
            raise DuplicateRecordError("duplicate identifier")
        self._items[publication.id] = replace(publication)
        return self._items[publication.id]

    def get(self, publication_id: int) -> Publication | None:
        return self._items.get(publication_id)

    def find_all_by_identifiers(
        self, *, doi: str | None, arxiv_id: str | None
    ) -> list[Publication]:
        return [
            replace(item)
            for item in self._items.values()
            if (doi is not None and item.doi == doi)
            or (arxiv_id is not None and item.arxiv_id == arxiv_id)
        ]

    def link_topic(self, publication_id: int, topic_id: int) -> bool:
        key = (publication_id, topic_id)
        if key in self._links:
            return False
        self._links.add(key)
        return True

    def count(self) -> int:
        return len(self._items)


class StubSource:
    def __init__(
        self,
        name: str,
        publications: list[Publication] | None = None,
        *,
        rejected: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._result = SourceResult(publications or [], rejected)
        self._error = error

    async def search(self, query: str, *, limit: int = 50) -> SourceResult:
        if self._error is not None:
            raise self._error
        return self._result


def unavailable(name: str) -> StubSource:
    return StubSource(name, error=SourceError(name, "giving up after 3 attempts: HTTP 503"))
