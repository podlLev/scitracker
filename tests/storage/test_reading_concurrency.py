import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from scitracker.domain.publication import Publication
from scitracker.domain.status import ReadingStatus
from scitracker.domain.user import User
from scitracker.services.reading import change_status
from scitracker.storage.models import PublicationRow, ReadingItemRow, StatusChangeRow, UserRow
from scitracker.storage.repositories import (
    SqlPublicationRepository,
    SqlReadingListRepository,
    SqlUserRepository,
)

THREADS = 8
T0 = datetime(2026, 11, 1, 12, tzinfo=UTC)


@dataclass(frozen=True)
class Seeded:
    user_id: int
    publication_id: int


@pytest.fixture
def committed(engine: Engine) -> Iterator[Seeded]:
    """Real committed rows (the rolled-back `session` fixture cannot be shared by threads)."""
    with Session(engine) as session, session.begin():
        user = SqlUserRepository(session).add(
            User(email=f"race-{uuid4().hex}@example.com", password_hash="h")
        )
        pub = SqlPublicationRepository(session).add(
            Publication(title="Race", authors=[], doi=f"10.1000/race-{uuid4().hex}")
        )
    assert user.id is not None
    assert pub.id is not None
    yield Seeded(user.id, pub.id)
    with Session(engine) as session, session.begin():
        # ON DELETE CASCADE removes items, history and notes with the user
        session.execute(delete(UserRow).where(UserRow.id == user.id))
        session.execute(delete(PublicationRow).where(PublicationRow.id == pub.id))


def run_in_parallel[T](engine: Engine, work: Callable[[Session], T]) -> list[T]:
    """Every thread has its own session and starts at the same moment."""
    barrier = threading.Barrier(THREADS)

    def task() -> T:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            result = work(session)
            session.commit()
            return result

    with ThreadPoolExecutor(THREADS) as pool:
        futures = [pool.submit(task) for _ in range(THREADS)]
        return [future.result(timeout=30) for future in futures]


def test_concurrent_adds_create_exactly_one_item(engine: Engine, committed: Seeded) -> None:
    def work(session: Session) -> bool:
        _, created = SqlReadingListRepository(session).add_if_absent(
            committed.user_id, committed.publication_id, T0
        )
        return created

    results = run_in_parallel(engine, work)
    assert results.count(True) == 1
    with Session(engine) as session:
        items = session.scalar(
            select(func.count())
            .select_from(ReadingItemRow)
            .where(ReadingItemRow.user_id == committed.user_id)
        )
    assert items == 1


def test_concurrent_done_requests_record_one_transition(engine: Engine, committed: Seeded) -> None:
    with Session(engine) as session, session.begin():
        repo = SqlReadingListRepository(session)
        item, _ = repo.add_if_absent(committed.user_id, committed.publication_id, T0)
        assert item.id is not None
        change_status(repo, committed.user_id, item.id, ReadingStatus.READING, T0)
    item_id = item.id

    def work(session: Session) -> datetime | None:
        done = change_status(
            SqlReadingListRepository(session),
            committed.user_id,
            item_id,
            ReadingStatus.DONE,
            datetime.now(UTC),  # a different moment for every request
        )
        return done.finished_at

    finish_dates = run_in_parallel(engine, work)
    assert len(set(finish_dates)) == 1  # everyone sees the same date: the winner's
    with Session(engine) as session:
        to_done = session.scalar(
            select(func.count())
            .select_from(StatusChangeRow)
            .where(StatusChangeRow.reading_item_id == item_id, StatusChangeRow.to_status == "done")
        )
        stored = session.get(ReadingItemRow, item_id)
    assert to_done == 1  # exactly one history entry for the transition
    assert stored is not None
    assert stored.finished_at == finish_dates[0]
