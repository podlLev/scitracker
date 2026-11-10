from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from scitracker.storage.database import SessionFactory


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[SessionFactory]:
    with engine.connect() as connection:
        outer = connection.begin()

        def factory() -> Session:
            return Session(bind=connection, join_transaction_mode="create_savepoint")

        yield factory
        outer.rollback()
