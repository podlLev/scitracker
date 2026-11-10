import random
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from scitracker.domain.publication import Author, Publication
from scitracker.storage.models import AuthorRow, PublicationRow
from scitracker.storage.repositories import SqlPublicationRepository

THREADS = 8
AUTHORS = 10


def test_overlapping_author_lists_do_not_deadlock(engine: Engine) -> None:
    run = uuid4().hex[:8]
    names = [f"Deadlock {run} {n}" for n in range(AUTHORS)]
    barrier = threading.Barrier(THREADS)

    def task(index: int) -> None:
        order = names[:]
        random.Random(index).shuffle(order)  # noqa: S311  # every thread lists the authors differently
        with Session(engine) as session:
            barrier.wait(timeout=10)
            SqlPublicationRepository(session).add(
                Publication(
                    title=f"P{index}",
                    authors=[Author(name) for name in order],
                    doi=f"10.1000/dl-{run}-{index}",
                )
            )
            session.commit()

    try:
        with ThreadPoolExecutor(THREADS) as pool:
            for future in [pool.submit(task, i) for i in range(THREADS)]:
                future.result(timeout=30)  # a deadlock would surface here as an exception
        with Session(engine) as session:
            created = session.scalar(
                select(func.count()).select_from(AuthorRow).where(AuthorRow.name.in_(names))
            )
        assert created == AUTHORS
    finally:
        with Session(engine) as session, session.begin():
            session.execute(
                delete(PublicationRow).where(PublicationRow.doi.like(f"10.1000/dl-{run}-%"))
            )
            session.execute(delete(AuthorRow).where(AuthorRow.name.in_(names)))
