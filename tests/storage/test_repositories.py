from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scitracker.domain.errors import DuplicateRecordError
from scitracker.domain.publication import Author, Publication
from scitracker.domain.topic import Topic
from scitracker.domain.user import User
from scitracker.storage.models import AuthorRow, ReadingItemRow
from scitracker.storage.repositories import (
    SqlPublicationRepository,
    SqlTopicRepository,
    SqlUserRepository,
)

NOW = datetime(2026, 11, 1, tzinfo=UTC)
FAKE_HASH = "not-a-real-hash"


def make_pub(doi: str | None = "10.1000/a", arxiv_id: str | None = None) -> Publication:
    return Publication(
        title="Title", authors=[Author("Ann Lee"), Author("Bob Ray")], doi=doi, arxiv_id=arxiv_id
    )


def test_publication_roundtrip_keeps_author_order(session: Session) -> None:
    repo = SqlPublicationRepository(session)
    saved = repo.add(make_pub())
    assert saved.id is not None
    loaded = repo.get(saved.id)
    assert loaded is not None
    assert [a.name for a in loaded.authors] == ["Ann Lee", "Bob Ray"]


def test_author_is_shared_between_publications(session: Session) -> None:
    repo = SqlPublicationRepository(session)
    repo.add(make_pub(doi="10.1000/a"))
    repo.add(make_pub(doi="10.1000/b"))
    names = session.scalars(select(func.count()).select_from(AuthorRow)).one()
    assert names == 2


def test_publication_without_doi_is_stored(session: Session) -> None:
    saved = SqlPublicationRepository(session).add(make_pub(doi=None, arxiv_id="2101.12345"))
    assert saved.doi is None
    assert saved.arxiv_id == "2101.12345"


def test_duplicate_doi_raises_and_session_stays_usable(session: Session) -> None:
    repo = SqlPublicationRepository(session)
    repo.add(make_pub())
    with pytest.raises(DuplicateRecordError):
        repo.add(make_pub())
    assert repo.count() == 1


def test_find_by_identifiers(session: Session) -> None:
    repo = SqlPublicationRepository(session)
    repo.add(make_pub(doi="10.1000/a", arxiv_id="2101.12345"))
    assert repo.find_by_identifiers(doi="10.1000/a", arxiv_id=None) is not None
    assert repo.find_by_identifiers(doi=None, arxiv_id="2101.12345") is not None
    assert repo.find_by_identifiers(doi="10.1000/zzz", arxiv_id=None) is None
    assert repo.find_by_identifiers(doi=None, arxiv_id=None) is None


def test_user_email_is_unique(session: Session) -> None:
    repo = SqlUserRepository(session)
    repo.add(User(email="a@example.com", password_hash=FAKE_HASH))
    with pytest.raises(DuplicateRecordError):
        repo.add(User(email="a@example.com", password_hash=FAKE_HASH))
    found = repo.get_by_email("a@example.com")
    assert found is not None
    assert found.id is not None
    assert repo.get_by_email("none@example.com") is None


def test_topics_are_listed_in_creation_order(session: Session) -> None:
    repo = SqlTopicRepository(session)
    repo.add(Topic(name="A", query="a"))
    repo.add(Topic(name="B", query="b"))
    assert [t.name for t in repo.list_all()] == ["A", "B"]


def _make_item_ids(session: Session) -> tuple[int, int]:
    user = SqlUserRepository(session).add(User(email="u@example.com", password_hash=FAKE_HASH))
    pub = SqlPublicationRepository(session).add(make_pub())
    assert user.id is not None
    assert pub.id is not None
    return user.id, pub.id


def test_reading_list_has_no_duplicates_per_user(session: Session) -> None:
    user_id, pub_id = _make_item_ids(session)
    session.add(ReadingItemRow(user_id=user_id, publication_id=pub_id, added_at=NOW))
    session.add(ReadingItemRow(user_id=user_id, publication_id=pub_id, added_at=NOW))
    with pytest.raises(IntegrityError):
        session.flush()


def test_done_status_requires_finish_date(session: Session) -> None:
    user_id, pub_id = _make_item_ids(session)
    session.add(ReadingItemRow(user_id=user_id, publication_id=pub_id, added_at=NOW, status="done"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_author_in_one_publication_is_stored_once(session: Session) -> None:
    pub = Publication(title="T", authors=[Author("Ann Lee"), Author("Ann Lee")], doi="10.1000/dup")
    saved = SqlPublicationRepository(session).add(pub)
    assert [a.name for a in saved.authors] == ["Ann Lee"]
