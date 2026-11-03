from sqlalchemy.orm import Session

from scitracker.domain.topic import Topic
from scitracker.storage.repositories import SqlPublicationRepository, SqlTopicRepository
from scitracker.storage.seed import seed


def test_seed_fills_empty_database_with_enough_records(session: Session) -> None:
    created = seed(session)
    assert created >= 200
    assert SqlPublicationRepository(session).count() == created


def test_seed_is_idempotent(session: Session) -> None:
    seed(session)
    assert seed(session) == 0


def test_seed_keeps_existing_topics(session: Session) -> None:
    SqlTopicRepository(session).add(Topic(name="Own", query="own"))
    seed(session)
    names = [t.name for t in SqlTopicRepository(session).list_all()]
    assert "Own" in names
    assert len(names) == 1  # seed does not add topics when some already exist
