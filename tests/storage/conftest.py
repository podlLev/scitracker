import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from scitracker.storage.database import create_db_engine
from tests.settings import get_test_database_url

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = get_test_database_url()
    db_engine = create_db_engine(url)
    try:
        db_engine.connect().close()
    except OperationalError:
        db_engine.dispose()
        if os.environ.get("CI"):
            raise  # in CI a missing database is a failure, not a skip
        pytest.skip("PostgreSQL is not available (run: docker compose up -d db)")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "src/scitracker/storage/migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as db_session:
        yield db_session
        db_session.rollback()  # every test leaves the database untouched
