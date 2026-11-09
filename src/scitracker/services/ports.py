from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from scitracker.domain.publication import Publication
from scitracker.domain.reading import Note, ReadingItem, StatusChange
from scitracker.domain.status import ReadingStatus
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
    def add(self, user: User) -> User:
        """Raise DuplicateRecordError if the email is taken."""
        ...

    def get(self, user_id: int) -> User | None: ...

    def get_by_email(self, email: str) -> User | None: ...


class TopicRepository(Protocol):
    def add(self, topic: Topic) -> Topic: ...

    def get(self, topic_id: int) -> Topic | None: ...

    def list_all(self) -> list[Topic]: ...

    def list_public(self) -> list[Topic]: ...

    def list_owned(self, owner_id: int) -> list[Topic]: ...

    def delete(self, topic_id: int) -> bool:
        """False if there was nothing to delete."""
        ...


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    query: str | None = None
    author: str | None = None
    topic_id: int | None = None
    published_from: date | None = None


class PublicationReader(Protocol):
    def get(self, publication_id: int) -> Publication | None: ...

    def search(
        self, criteria: SearchCriteria, *, after_id: int | None, limit: int
    ) -> list[Publication]:
        """Newest first (by id); only records with an id below `after_id`."""
        ...


class PasswordHasher(Protocol):
    def hash_password(self, password: str) -> str: ...

    def verify_password(self, password_hash: str | None, password: str) -> bool:
        """With None (unknown user) the check still costs the same time and returns False."""
        ...


class TokenService(Protocol):
    @property
    def ttl_seconds(self) -> int: ...

    def issue(self, user_id: int) -> str: ...

    def verify(self, token: str) -> int:
        """Return the user id; raise AuthenticationError for an invalid or expired token."""
        ...


class ReadingListRepository(Protocol):
    def add_if_absent(
        self, user_id: int, publication_id: int, at: datetime
    ) -> tuple[ReadingItem, bool]:
        """Return the user's item for the publication and whether it was just created."""
        ...

    def get(self, item_id: int, user_id: int) -> ReadingItem | None:
        """Only the owner's items: a foreign item looks exactly like a missing one."""
        ...

    def get_for_update(self, item_id: int, user_id: int) -> ReadingItem | None:
        """Like `get`, but locks the row until the end of the transaction."""
        ...

    def save_status(self, item: ReadingItem, change: StatusChange) -> None:
        """Store the new status and the history entry in the current transaction."""
        ...

    def list_for_user(
        self, user_id: int, *, status: ReadingStatus | None, after_id: int | None, limit: int
    ) -> list[ReadingItem]:
        """Newest first (by id); only records with an id below `after_id`."""
        ...

    def history(self, item_id: int) -> list[StatusChange]: ...

    def add_note(self, note: Note) -> Note: ...

    def list_notes(self, item_id: int) -> list[Note]: ...


class UnitOfWork(Protocol):
    """One request: repositories over one session; the caller decides when to commit."""

    @property
    def publications(self) -> PublicationReader: ...

    @property
    def topics(self) -> TopicRepository: ...

    @property
    def users(self) -> UserRepository: ...

    @property
    def reading(self) -> ReadingListRepository: ...

    def commit(self) -> None: ...
