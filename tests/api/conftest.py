from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from scitracker.api.app import create_app
from scitracker.api.deps import ReadRepositories
from scitracker.storage.repositories import SqlPublicationRepository, SqlTopicRepository


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    """The real API over the real repositories, inside the test's rolled-back transaction."""

    @contextmanager
    def read_scope() -> Iterator[ReadRepositories]:
        yield ReadRepositories(SqlPublicationRepository(session), SqlTopicRepository(session))

    def ping() -> None:
        session.execute(text("SELECT 1"))

    app = create_app(read_scope=read_scope, ping=ping)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
