import pytest

from scitracker.domain.errors import RecordNotFoundError
from scitracker.domain.publication import Publication
from scitracker.domain.topic import Topic
from scitracker.domain.user import User
from scitracker.services.feed import user_feed
from scitracker.services.ports import SearchCriteria
from tests.services.fakes import InMemoryTopicRepository

ALICE = User(email="a@example.com", password_hash="h", id=1)


class RecordingReader:
    def __init__(self) -> None:
        self.criteria: SearchCriteria | None = None

    def get(self, publication_id: int) -> Publication | None:
        return None

    def search(
        self, criteria: SearchCriteria, *, after_id: int | None, limit: int
    ) -> list[Publication]:
        self.criteria = criteria
        return []


def make_topics() -> InMemoryTopicRepository:
    repo = InMemoryTopicRepository()
    repo.add(Topic(name="Public", query="p"))  # id 1
    repo.add(Topic(name="Mine", query="m", owner_id=1))  # id 2
    repo.add(Topic(name="Theirs", query="t", owner_id=2))  # id 3
    return repo


def test_feed_covers_public_and_own_topics_only() -> None:
    reader = RecordingReader()
    user_feed(reader, make_topics(), ALICE)
    assert reader.criteria is not None
    assert reader.criteria.topic_ids == (1, 2)


def test_feed_can_be_narrowed_to_one_visible_topic() -> None:
    reader = RecordingReader()
    user_feed(reader, make_topics(), ALICE, topic_id=2)
    assert reader.criteria is not None
    assert reader.criteria.topic_ids == (2,)


def test_foreign_topic_looks_missing() -> None:
    with pytest.raises(RecordNotFoundError):
        user_feed(RecordingReader(), make_topics(), ALICE, topic_id=3)


def test_no_topics_means_an_empty_feed_without_touching_the_reader() -> None:
    reader = RecordingReader()
    page = user_feed(reader, InMemoryTopicRepository(), ALICE)
    assert (page.items, page.next_after_id) == ([], None)
    assert reader.criteria is None
