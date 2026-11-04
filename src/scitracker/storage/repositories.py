from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scitracker.domain.errors import DuplicateRecordError, InvalidValueError, RecordNotFoundError
from scitracker.domain.publication import Author, Publication
from scitracker.domain.topic import Topic
from scitracker.domain.user import Role, User
from scitracker.storage.models import (
    AuthorRow,
    PublicationAuthorRow,
    PublicationRow,
    PublicationTopicRow,
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
        if row is None:
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
        seen: set[int] = set()
        for author in authors:
            author_row = self._get_or_create_author(author.name)
            if author_row.id in seen:
                continue
            seen.add(author_row.id)
            row.author_links.append(PublicationAuthorRow(author=author_row, position=len(seen) - 1))

    def _get_or_create_author(self, name: str) -> AuthorRow:
        # ON CONFLICT keeps this safe when two processes insert the same author.
        self._session.execute(
            insert(AuthorRow).values(name=name).on_conflict_do_nothing(index_elements=["name"])
        )
        return self._session.scalars(select(AuthorRow).where(AuthorRow.name == name)).one()


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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
