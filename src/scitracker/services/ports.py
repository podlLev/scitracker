from dataclasses import dataclass, field
from typing import Protocol

from scitracker.domain.publication import Publication
from scitracker.domain.topic import Topic
from scitracker.domain.user import User


@dataclass(frozen=True, slots=True)
class SourceResult:
    """Publications parsed from one source and the number of rejected records."""

    publications: list[Publication] = field(default_factory=list)
    rejected: int = 0


class PublicationSource(Protocol):
    @property
    def name(self) -> str: ...

    async def search(self, query: str, *, limit: int = 50) -> SourceResult:
        """Return up to `limit` publications; raise SourceError if the source is unavailable."""
        ...


class PublicationRepository(Protocol):
    def add(self, publication: Publication) -> Publication:
        """Persist the publication; raise DuplicateRecordError on a DOI/arXiv ID clash."""
        ...

    def update(self, publication: Publication) -> Publication:
        """Overwrite the stored publication with the same id.

        Raise RecordNotFoundError if it does not exist, DuplicateRecordError on an identifier clash.
        """
        ...

    def get(self, publication_id: int) -> Publication | None: ...

    def find_all_by_identifiers(
        self, *, doi: str | None, arxiv_id: str | None
    ) -> list[Publication]:
        """Return every stored publication matching the DOI or the arXiv ID."""
        ...

    def link_topic(self, publication_id: int, topic_id: int) -> bool:
        """Attach the publication to the topic; False if it was already attached."""
        ...

    def count(self) -> int: ...


class UserRepository(Protocol):
    def add(self, user: User) -> User: ...

    def get_by_email(self, email: str) -> User | None: ...


class TopicRepository(Protocol):
    def add(self, topic: Topic) -> Topic: ...

    def list_all(self) -> list[Topic]: ...
