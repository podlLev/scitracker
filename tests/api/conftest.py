from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from scitracker.api.app import create_app
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.security.tokens import JwtTokenService
from scitracker.services.ports import UnitOfWork
from scitracker.storage.unit_of_work import SqlUnitOfWork
from tests.api.helpers import TEST_SECRET, FakeClock


class FlushOnlyUnitOfWork(SqlUnitOfWork):
    """A real commit would escape the test's rolled-back transaction."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._test_session = session

    def commit(self) -> None:
        self._test_session.flush()


@pytest.fixture(scope="session")
def hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(
    session: Session, hasher: Argon2PasswordHasher, clock: FakeClock
) -> Iterator[TestClient]:
    """The real API over the real repositories, inside the test's rolled-back transaction."""

    @contextmanager
    def scope() -> Iterator[UnitOfWork]:
        yield FlushOnlyUnitOfWork(session)

    def ping() -> None:
        session.execute(text("SELECT 1"))

    app = create_app(
        scope=scope,
        ping=ping,
        hasher=hasher,
        tokens=JwtTokenService(TEST_SECRET),
        clock=clock,
    )
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
