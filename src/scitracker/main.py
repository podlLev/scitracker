import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI
from sqlalchemy import text

from scitracker.api.app import create_app
from scitracker.api.deps import ReadRepositories
from scitracker.storage.database import create_db_engine, create_session_factory
from scitracker.storage.repositories import SqlPublicationRepository, SqlTopicRepository


def build_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    session_factory = create_session_factory(create_db_engine(os.environ["DATABASE_URL"]))

    @contextmanager
    def read_scope() -> Iterator[ReadRepositories]:
        with session_factory() as session:
            yield ReadRepositories(SqlPublicationRepository(session), SqlTopicRepository(session))

    def ping() -> None:
        with session_factory() as session:
            session.execute(text("SELECT 1"))

    return create_app(read_scope=read_scope, ping=ping)
