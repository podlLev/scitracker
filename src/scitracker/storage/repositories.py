from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from scitracker.domain.errors import DuplicateRecordError, InvalidValueError, RecordNotFoundError
from scitracker.domain.publication import Author, Publication
from scitracker.domain.reading import Note, ReadingItem, StatusChange
from scitracker.domain.status import ReadingStatus
from scitracker.domain.topic import Topic
from scitracker.domain.user import Role, User
from scitracker.services.ports import SearchCriteria
from scitracker.storage.models import (
    AuthorRow,
    NoteRow,
    PublicationAuthorRow,
    PublicationRow,
    PublicationTopicRow,
    ReadingItemRow,
    StatusChangeRow,
    TopicRow,
    UserRow,
)


def _add_or_duplicate(
    session: Session, row: PublicationRow | UserRow | TopicRow, message: str
) -> None:
    """Insert in a savepoint so a uniqueness clash does not poison the outer transaction."""
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as exc:
        raise DuplicateRecordError(message) from exc


def _publication_to_domain(row: PublicationRow) -> Publication:
    return Publication(
        id=row.id,
        title=row.title,
        authors=[Author(name=link.author.name, id=link.author.id) for link in row.author_links],
        doi=row.doi,
        arxiv_id=row.arxiv_id,
        abstract=row.abstract,
        published_on=row.published_on,
        url=row.url,
    )


def _contains(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _item_to_domain(row: ReadingItemRow) -> ReadingItem:
    return ReadingItem(
        id=row.id,
        user_id=row.user_id,
        publication_id=row.publication_id,
        added_at=row.added_at,
        status=ReadingStatus(row.status),
        finished_at=row.finished_at,
    )


class SqlPublicationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, publication: Publication) -> Publication:
        ident = publication.doi or publication.arxiv_id
        try:
            # Authors are created inside the savepoint too: a clash leaves no orphans.
            with self._session.begin_nested():
                row = PublicationRow(
                    title=publication.title,
                    doi=publication.doi,
                    arxiv_id=publication.arxiv_id,
                    abstract=publication.abstract,
                    published_on=publication.published_on,
                    url=publication.url,
                )
                self._attach_authors(row, publication.authors)
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateRecordError(
                f"publication with identifier {ident} already exists"
            ) from exc
        return _publication_to_domain(row)

    def update(self, publication: Publication) -> Publication:
        if publication.id is None:
            raise InvalidValueError("cannot update a publication without an id")
        row = self._session.get(PublicationRow, publication.id)
        if row is None:  # pragma: no cover - the item was just loaded under lock
            raise RecordNotFoundError(f"publication {publication.id} does not exist")
        try:
            with self._session.begin_nested():
                row.title = publication.title
                row.doi = publication.doi
                row.arxiv_id = publication.arxiv_id
                row.abstract = publication.abstract
                row.published_on = publication.published_on
                row.url = publication.url
                current = [link.author.name for link in row.author_links]
                if current != [author.name for author in publication.authors]:
                    row.author_links.clear()
                    self._session.flush()  # delete old links before inserting new ones
                    self._attach_authors(row, publication.authors)
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateRecordError(
                f"identifiers of publication {publication.id} clash with another record"
            ) from exc
        return _publication_to_domain(row)

    def get(self, publication_id: int) -> Publication | None:
        row: PublicationRow | None = self._session.get(PublicationRow, publication_id)
        return _publication_to_domain(row) if row is not None else None

    def find_all_by_identifiers(
        self, *, doi: str | None, arxiv_id: str | None
    ) -> list[Publication]:
        conditions = []
        if doi is not None:
            conditions.append(PublicationRow.doi == doi)
        if arxiv_id is not None:
            conditions.append(PublicationRow.arxiv_id == arxiv_id)
        if not conditions:
            return []
        stmt = select(PublicationRow).where(or_(*conditions)).order_by(PublicationRow.id)
        return [_publication_to_domain(row) for row in self._session.scalars(stmt)]

    def search(
        self, criteria: SearchCriteria, *, after_id: int | None, limit: int
    ) -> list[Publication]:
        stmt = (
            select(PublicationRow)
            .options(
                selectinload(PublicationRow.author_links).selectinload(PublicationAuthorRow.author)
            )
            .order_by(PublicationRow.id.desc())
            .limit(limit)
        )
        if after_id is not None:
            stmt = stmt.where(PublicationRow.id < after_id)
        if criteria.query:
            stmt = stmt.where(PublicationRow.title.ilike(_contains(criteria.query)))
        if criteria.author:
            stmt = stmt.where(
                PublicationRow.author_links.any(
                    PublicationAuthorRow.author.has(
                        AuthorRow.name.ilike(_contains(criteria.author))
                    )
                )
            )
        if criteria.topic_id is not None:
            stmt = stmt.where(
                PublicationRow.id.in_(
                    select(PublicationTopicRow.publication_id).where(
                        PublicationTopicRow.topic_id == criteria.topic_id
                    )
                )
            )
        if criteria.topic_ids is not None:
            stmt = stmt.where(
                PublicationRow.id.in_(
                    select(PublicationTopicRow.publication_id).where(
                        PublicationTopicRow.topic_id.in_(criteria.topic_ids)
                    )
                )
            )
        if criteria.published_from is not None:
            stmt = stmt.where(PublicationRow.published_on >= criteria.published_from)
        return [_publication_to_domain(row) for row in self._session.scalars(stmt)]

    def link_topic(self, publication_id: int, topic_id: int) -> bool:
        stmt = (
            insert(PublicationTopicRow)
            .values(publication_id=publication_id, topic_id=topic_id)
            .on_conflict_do_nothing()
            .returning(PublicationTopicRow.publication_id)
        )
        return self._session.execute(stmt).first() is not None

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(PublicationRow)) or 0

    def _attach_authors(self, row: PublicationRow, authors: list[Author]) -> None:
        by_name = self._get_or_create_authors([author.name for author in authors])
        seen: set[int] = set()
        for author in authors:
            author_row = by_name[author.name]
            if author_row.id in seen:
                continue
            seen.add(author_row.id)
            row.author_links.append(PublicationAuthorRow(author=author_row, position=len(seen) - 1))

    def _get_or_create_authors(self, names: list[str]) -> dict[str, AuthorRow]:
        """Two statements for any number of authors (was two per author)."""
        unique = sorted(set(names))
        if not unique:
            return {}
        self._session.execute(
            insert(AuthorRow)
            .values([{"name": name} for name in unique])
            .on_conflict_do_nothing(index_elements=["name"])
        )
        rows = self._session.scalars(select(AuthorRow).where(AuthorRow.name.in_(unique)))
        return {row.name: row for row in rows}


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: int) -> User | None:
        row: UserRow | None = self._session.get(UserRow, user_id)
        return self._to_domain(row) if row is not None else None

    def add(self, user: User) -> User:
        row = UserRow(email=user.email, password_hash=user.password_hash, role=user.role.value)
        _add_or_duplicate(self._session, row, f"user {user.email} already exists")
        return self._to_domain(row)

    def get_by_email(self, email: str) -> User | None:
        row = self._session.scalars(select(UserRow).where(UserRow.email == email)).first()
        return self._to_domain(row) if row else None

    @staticmethod
    def _to_domain(row: UserRow) -> User:
        return User(
            id=row.id, email=row.email, password_hash=row.password_hash, role=Role(row.role)
        )


class SqlTopicRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, topic_id: int) -> Topic | None:
        row: TopicRow | None = self._session.get(TopicRow, topic_id)
        return self._to_domain(row) if row is not None else None

    def list_public(self) -> list[Topic]:
        stmt = select(TopicRow).where(TopicRow.owner_id.is_(None)).order_by(TopicRow.id)
        return [self._to_domain(row) for row in self._session.scalars(stmt)]

    def list_owned(self, owner_id: int) -> list[Topic]:
        stmt = select(TopicRow).where(TopicRow.owner_id == owner_id).order_by(TopicRow.id)
        return [self._to_domain(row) for row in self._session.scalars(stmt)]

    def delete(self, topic_id: int) -> bool:
        row: TopicRow | None = self._session.get(TopicRow, topic_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()  # links in publication_topics go away via ON DELETE CASCADE
        return True

    def add(self, topic: Topic) -> Topic:
        row = TopicRow(name=topic.name, query=topic.query, owner_id=topic.owner_id)
        self._session.add(row)
        self._session.flush()
        return self._to_domain(row)

    def list_all(self) -> list[Topic]:
        rows = self._session.scalars(select(TopicRow).order_by(TopicRow.id))
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: TopicRow) -> Topic:
        return Topic(id=row.id, name=row.name, query=row.query, owner_id=row.owner_id)


class SqlReadingListRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_if_absent(
        self, user_id: int, publication_id: int, at: datetime
    ) -> tuple[ReadingItem, bool]:
        # The unique constraint decides, not a prior SELECT: no race between check and insert.
        stmt = (
            insert(ReadingItemRow)
            .values(user_id=user_id, publication_id=publication_id, status="to_read", added_at=at)
            .on_conflict_do_nothing(index_elements=["user_id", "publication_id"])
            .returning(ReadingItemRow.id)
        )
        created = self._session.execute(stmt).scalar_one_or_none() is not None
        row = self._session.scalars(
            select(ReadingItemRow)
            .where(
                ReadingItemRow.user_id == user_id,
                ReadingItemRow.publication_id == publication_id,
            )
            .execution_options(populate_existing=True)
        ).one()
        return _item_to_domain(row), created

    def get(self, item_id: int, user_id: int) -> ReadingItem | None:
        return self._load(item_id, user_id, lock=False)

    def get_for_update(self, item_id: int, user_id: int) -> ReadingItem | None:
        return self._load(item_id, user_id, lock=True)

    def save_status(self, item: ReadingItem, change: StatusChange) -> None:
        row: ReadingItemRow | None = (
            self._session.get(ReadingItemRow, item.id) if item.id is not None else None
        )
        if row is None:  # pragma: no cover - the item was just loaded under lock
            raise RecordNotFoundError("reading list item does not exist")
        row.status = str(item.status)
        row.finished_at = item.finished_at
        self._session.add(
            StatusChangeRow(
                reading_item_id=row.id,
                from_status=str(change.from_status),
                to_status=str(change.to_status),
                changed_at=change.changed_at,
            )
        )
        self._session.flush()

    def list_for_user(
        self, user_id: int, *, status: ReadingStatus | None, after_id: int | None, limit: int
    ) -> list[ReadingItem]:
        stmt = (
            select(ReadingItemRow)
            .where(ReadingItemRow.user_id == user_id)
            .order_by(ReadingItemRow.id.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(ReadingItemRow.status == str(status))
        if after_id is not None:
            stmt = stmt.where(ReadingItemRow.id < after_id)
        return [_item_to_domain(row) for row in self._session.scalars(stmt)]

    def history(self, item_id: int) -> list[StatusChange]:
        stmt = (
            select(StatusChangeRow)
            .where(StatusChangeRow.reading_item_id == item_id)
            .order_by(StatusChangeRow.id)
        )
        return [
            StatusChange(
                ReadingStatus(row.from_status), ReadingStatus(row.to_status), row.changed_at
            )
            for row in self._session.scalars(stmt)
        ]

    def add_note(self, note: Note) -> Note:
        if note.reading_item_id is None:
            raise InvalidValueError("a note must belong to a reading list item")
        row = NoteRow(
            reading_item_id=note.reading_item_id, text=note.text, created_at=note.created_at
        )
        self._session.add(row)
        self._session.flush()
        return Note(
            id=row.id,
            reading_item_id=row.reading_item_id,
            text=row.text,
            created_at=row.created_at,
        )

    def list_notes(self, item_id: int) -> list[Note]:
        stmt = select(NoteRow).where(NoteRow.reading_item_id == item_id).order_by(NoteRow.id)
        return [
            Note(
                id=row.id,
                reading_item_id=row.reading_item_id,
                text=row.text,
                created_at=row.created_at,
            )
            for row in self._session.scalars(stmt)
        ]

    def _load(self, item_id: int, user_id: int, *, lock: bool) -> ReadingItem | None:
        stmt = select(ReadingItemRow).where(
            ReadingItemRow.id == item_id, ReadingItemRow.user_id == user_id
        )
        # populate_existing: after waiting for a lock, read the state the winner committed.
        stmt = stmt.execution_options(populate_existing=True)
        if lock:
            stmt = stmt.with_for_update()
        row = self._session.scalars(stmt).first()
        return _item_to_domain(row) if row is not None else None

    def list_with_publications(
        self, user_id: int, *, status: ReadingStatus | None
    ) -> list[tuple[ReadingItem, Publication]]:
        stmt = (
            select(ReadingItemRow, PublicationRow)
            .join(PublicationRow, PublicationRow.id == ReadingItemRow.publication_id)
            .options(
                selectinload(PublicationRow.author_links).selectinload(PublicationAuthorRow.author)
            )
            .where(ReadingItemRow.user_id == user_id)
            .order_by(ReadingItemRow.id)
        )
        if status is not None:
            stmt = stmt.where(ReadingItemRow.status == str(status))
        return [
            (_item_to_domain(item), _publication_to_domain(publication))
            for item, publication in self._session.execute(stmt)
        ]
