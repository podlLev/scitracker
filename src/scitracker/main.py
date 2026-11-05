import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI
from sqlalchemy import text

from scitracker.api.app import create_app
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.security.tokens import JwtTokenService
from scitracker.services.ports import UnitOfWork
from scitracker.storage.database import create_db_engine, create_session_factory
from scitracker.storage.unit_of_work import SqlUnitOfWork


def build_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    session_factory = create_session_factory(create_db_engine(os.environ["DATABASE_URL"]))

    @contextmanager
    def scope() -> Iterator[UnitOfWork]:
        with session_factory() as session:
            yield SqlUnitOfWork(session)

    def ping() -> None:
        with session_factory() as session:
            session.execute(text("SELECT 1"))

    return create_app(
        scope=scope,
        ping=ping,
        hasher=Argon2PasswordHasher(),
        tokens=JwtTokenService(os.environ["JWT_SECRET"]),
    )
