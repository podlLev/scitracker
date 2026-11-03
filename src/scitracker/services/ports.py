from typing import Protocol

from scitracker.domain.publication import Publication
from scitracker.domain.topic import Topic
from scitracker.domain.user import User


class PublicationRepository(Protocol):
    def add(self, publication: Publication) -> Publication:
        """Persist the publication; raise DuplicateRecordError on a DOI/arXiv ID clash."""
        ...

    def get(self, publication_id: int) -> Publication | None: ...

    def find_by_identifiers(
        self, *, doi: str | None, arxiv_id: str | None
    ) -> Publication | None: ...

    def count(self) -> int: ...


class UserRepository(Protocol):
    def add(self, user: User) -> User: ...

    def get_by_email(self, email: str) -> User | None: ...


class TopicRepository(Protocol):
    def add(self, topic: Topic) -> Topic: ...

    def list_all(self) -> list[Topic]: ...
