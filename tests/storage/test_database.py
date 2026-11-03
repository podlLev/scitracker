from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from scitracker.storage.database import create_session_factory


def test_session_factory_connects(engine: Engine) -> None:
    factory = create_session_factory(engine)
    with factory() as session:
        assert isinstance(session, Session)
        assert session.execute(text("select 1")).scalar_one() == 1
