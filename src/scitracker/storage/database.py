from collections.abc import Callable

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = Callable[[], Session]


def create_db_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,  # error messages never include bound values (emails, hashes)
        connect_args={"options": "-c timezone=UTC"},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
