from dataclasses import replace
from datetime import datetime

from scitracker.domain.errors import DuplicateRecordError
from scitracker.domain.publication import Publication
from scitracker.domain.reading import Note, ReadingItem, StatusChange
from scitracker.domain.status import ReadingStatus
from scitracker.domain.topic import Topic
from scitracker.domain.user import User
from scitracker.services.errors import SourceError
from scitracker.services.ports import SearchCriteria, SourceResult


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


class StubPublicationReader:
    def __init__(self, *known_ids: int) -> None:
        self._known = set(known_ids)

    def get(self, publication_id: int) -> Publication | None:
        if publication_id not in self._known:
            return None
        return Publication(
            title="Known", authors=[], doi=f"10.1000/{publication_id}", id=publication_id
        )

    def search(
        self, criteria: SearchCriteria, *, after_id: int | None, limit: int
    ) -> list[Publication]:
        return []


class InMemoryReadingListRepository:
    def __init__(self) -> None:
        self.items: dict[int, ReadingItem] = {}
        self.changes: dict[int, list[StatusChange]] = {}
        self.notes: dict[int, list[Note]] = {}
        self.locked: list[int] = []

    def add_if_absent(
        self, user_id: int, publication_id: int, at: datetime
    ) -> tuple[ReadingItem, bool]:
        for item in self.items.values():
            if (item.user_id, item.publication_id) == (user_id, publication_id):
                return replace(item), False
        new = ReadingItem(
            user_id=user_id, publication_id=publication_id, added_at=at, id=len(self.items) + 1
        )
        self.items[new.id or 0] = new
        return replace(new), True

    def get(self, item_id: int, user_id: int) -> ReadingItem | None:
        item = self.items.get(item_id)
        return replace(item) if item is not None and item.user_id == user_id else None

    def get_for_update(self, item_id: int, user_id: int) -> ReadingItem | None:
        self.locked.append(item_id)
        return self.get(item_id, user_id)

    def save_status(self, item: ReadingItem, change: StatusChange) -> None:
        assert item.id is not None
        self.items[item.id] = replace(item)
        self.changes.setdefault(item.id, []).append(change)

    def list_for_user(
        self, user_id: int, *, status: ReadingStatus | None, after_id: int | None, limit: int
    ) -> list[ReadingItem]:
        found = [
            replace(i)
            for i in sorted(self.items.values(), key=lambda i: -(i.id or 0))
            if i.user_id == user_id
            and (status is None or i.status is status)
            and (after_id is None or (i.id or 0) < after_id)
        ]
        return found[:limit]

    def history(self, item_id: int) -> list[StatusChange]:
        return list(self.changes.get(item_id, []))

    def add_note(self, note: Note) -> Note:
        assert note.reading_item_id is not None
        stored = replace(note, id=sum(len(v) for v in self.notes.values()) + 1)
        self.notes.setdefault(note.reading_item_id, []).append(stored)
        return stored

    def list_notes(self, item_id: int) -> list[Note]:
        return list(self.notes.get(item_id, []))
