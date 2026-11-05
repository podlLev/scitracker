from dataclasses import replace

from scitracker.domain.errors import DuplicateRecordError
from scitracker.domain.publication import Publication
from scitracker.domain.topic import Topic
from scitracker.domain.user import User
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


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._items: dict[int, User] = {}

    def add(self, user: User) -> User:
        if self.get_by_email(user.email) is not None:
            raise DuplicateRecordError("email taken")
        stored = replace(user, id=len(self._items) + 1)
        self._items[stored.id or 0] = stored
        return stored

    def get(self, user_id: int) -> User | None:
        return self._items.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._items.values() if u.email == email), None)


class InMemoryTopicRepository:
    def __init__(self) -> None:
        self._items: dict[int, Topic] = {}

    def add(self, topic: Topic) -> Topic:
        stored = replace(topic, id=len(self._items) + 1)
        self._items[stored.id or 0] = stored
        return stored

    def get(self, topic_id: int) -> Topic | None:
        return self._items.get(topic_id)

    def list_all(self) -> list[Topic]:
        return list(self._items.values())

    def list_public(self) -> list[Topic]:
        return [t for t in self._items.values() if t.owner_id is None]

    def list_owned(self, owner_id: int) -> list[Topic]:
        return [t for t in self._items.values() if t.owner_id == owner_id]

    def delete(self, topic_id: int) -> bool:
        return self._items.pop(topic_id, None) is not None


class FakeHasher:
    def __init__(self) -> None:
        self.hashed = 0
        self.verified_with: list[str | None] = []

    def hash_password(self, password: str) -> str:
        self.hashed += 1
        return f"hashed:{password}"

    def verify_password(self, password_hash: str | None, password: str) -> bool:
        self.verified_with.append(password_hash)
        return password_hash == f"hashed:{password}"
