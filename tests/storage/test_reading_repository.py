from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.publication import Publication
from scitracker.domain.reading import Note
from scitracker.domain.status import ReadingStatus
from scitracker.domain.user import User
from scitracker.services.reading import change_status
from scitracker.storage.models import ReadingItemRow, StatusChangeRow
from scitracker.storage.repositories import (
    SqlPublicationRepository,
    SqlReadingListRepository,
    SqlUserRepository,
)

S = ReadingStatus
T0 = datetime(2026, 11, 1, 12, tzinfo=UTC)
T1 = T0 + timedelta(days=1)


def make_user(session: Session, email: str) -> int:
    saved = SqlUserRepository(session).add(User(email=email, password_hash="h"))
    assert saved.id is not None
    return saved.id


def make_pub(session: Session, number: int) -> int:
    saved = SqlPublicationRepository(session).add(
        Publication(title=f"P{number}", authors=[], doi=f"10.1000/r{number}")
    )
    assert saved.id is not None
    return saved.id


def test_add_if_absent_is_idempotent(session: Session) -> None:
    repo = SqlReadingListRepository(session)
    user, pub = make_user(session, "a@example.com"), make_pub(session, 1)
    first, created_first = repo.add_if_absent(user, pub, T0)
    second, created_second = repo.add_if_absent(user, pub, T1)
    assert (created_first, created_second) == (True, False)
    assert first.id == second.id
    assert second.added_at == T0
    count = session.scalar(select(func.count()).select_from(ReadingItemRow))
    assert count == 1


def test_status_change_updates_the_row_and_writes_history(session: Session) -> None:
    repo = SqlReadingListRepository(session)
    user, pub = make_user(session, "a@example.com"), make_pub(session, 1)
    item, _ = repo.add_if_absent(user, pub, T0)
    assert item.id is not None
    change_status(repo, user, item.id, S.READING, T0)
    done = change_status(repo, user, item.id, S.DONE, T1)
    assert done.finished_at == T1
    reloaded = repo.get(item.id, user)
    assert reloaded is not None
    assert (reloaded.status, reloaded.finished_at) == (S.DONE, T1)
    assert [(c.from_status, c.to_status) for c in repo.history(item.id)] == [
        (S.TO_READ, S.READING),
        (S.READING, S.DONE),
    ]
    change_status(repo, user, item.id, S.DONE, T1 + timedelta(days=5))  # repeated request
    assert len(repo.history(item.id)) == 2


def test_foreign_item_is_invisible(session: Session) -> None:
    repo = SqlReadingListRepository(session)
    alice, bob = make_user(session, "a@example.com"), make_user(session, "b@example.com")
    item, _ = repo.add_if_absent(alice, make_pub(session, 1), T0)
    assert item.id is not None
    assert repo.get(item.id, bob) is None
    assert repo.get_for_update(item.id, bob) is None
    assert repo.list_for_user(bob, status=None, after_id=None, limit=10) == []


def test_list_filters_by_status_and_pages_by_id(session: Session) -> None:
    repo = SqlReadingListRepository(session)
    user = make_user(session, "a@example.com")
    items = [repo.add_if_absent(user, make_pub(session, n), T0)[0] for n in range(3)]
    assert items[0].id is not None
    change_status(repo, user, items[0].id, S.READING, T1)
    newest_two = repo.list_for_user(user, status=None, after_id=None, limit=2)
    assert [i.id for i in newest_two] == [items[2].id, items[1].id]
    older = repo.list_for_user(user, status=None, after_id=items[1].id, limit=10)
    assert [i.id for i in older] == [items[0].id]
    only_reading = repo.list_for_user(user, status=S.READING, after_id=None, limit=10)
    assert [i.id for i in only_reading] == [items[0].id]


def test_notes_belong_to_the_item_and_keep_their_order(session: Session) -> None:
    repo = SqlReadingListRepository(session)
    user = make_user(session, "a@example.com")
    first, _ = repo.add_if_absent(user, make_pub(session, 1), T0)
    second, _ = repo.add_if_absent(user, make_pub(session, 2), T0)
    assert first.id is not None
    assert second.id is not None
    repo.add_note(Note(reading_item_id=first.id, text="one", created_at=T0))
    repo.add_note(Note(reading_item_id=first.id, text="two", created_at=T1))
    repo.add_note(Note(reading_item_id=second.id, text="other", created_at=T0))
    assert [n.text for n in repo.list_notes(first.id)] == ["one", "two"]
    assert [n.text for n in repo.list_notes(second.id)] == ["other"]


def test_note_without_an_item_is_rejected(session: Session) -> None:
    with pytest.raises(InvalidValueError):
        SqlReadingListRepository(session).add_note(
            Note(reading_item_id=None, text="orphan", created_at=T0)
        )


def test_database_refuses_an_inconsistent_status_row(session: Session) -> None:
    """The CHECK constraint is the last line of defence, even if the code had a bug."""
    repo = SqlReadingListRepository(session)
    user = make_user(session, "a@example.com")
    item, _ = repo.add_if_absent(user, make_pub(session, 1), T0)
    row = session.get(ReadingItemRow, item.id)
    assert row is not None
    row.status = "done"  # no finished_at
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    assert session.scalar(select(func.count()).select_from(StatusChangeRow)) == 0
