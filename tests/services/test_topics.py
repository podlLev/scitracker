import pytest

from scitracker.domain.errors import PermissionDeniedError, QuotaExceededError, RecordNotFoundError
from scitracker.domain.user import Role, User
from scitracker.services.topics import MAX_PRIVATE_TOPICS, create_topic, delete_topic
from tests.services.fakes import InMemoryTopicRepository


def user(user_id: int, role: Role = Role.USER) -> User:
    return User(email=f"u{user_id}@example.com", password_hash="h", role=role, id=user_id)


def test_user_creates_a_private_topic() -> None:
    topic = create_topic(InMemoryTopicRepository(), user(1), name="ML", query="ml", public=False)
    assert topic.owner_id == 1


def test_only_admin_creates_public_topics() -> None:
    repo = InMemoryTopicRepository()
    with pytest.raises(PermissionDeniedError):
        create_topic(repo, user(1), name="ML", query="ml", public=True)
    topic = create_topic(repo, user(2, Role.ADMIN), name="ML", query="ml", public=True)
    assert topic.owner_id is None


def test_private_topic_quota() -> None:
    repo = InMemoryTopicRepository()
    for n in range(MAX_PRIVATE_TOPICS):
        create_topic(repo, user(1), name=f"T{n}", query="q", public=False)
    with pytest.raises(QuotaExceededError):
        create_topic(repo, user(1), name="extra", query="q", public=False)
    create_topic(repo, user(2), name="other user", query="q", public=False)  # quota is per user


def test_owner_deletes_own_topic_but_others_see_nothing() -> None:
    repo = InMemoryTopicRepository()
    topic = create_topic(repo, user(1), name="ML", query="ml", public=False)
    assert topic.id is not None
    with pytest.raises(RecordNotFoundError):
        delete_topic(repo, user(2), topic.id)
    with pytest.raises(RecordNotFoundError):
        delete_topic(repo, user(3, Role.ADMIN), topic.id)  # admins do not see private topics
    delete_topic(repo, user(1), topic.id)
    assert repo.get(topic.id) is None


def test_public_topics_are_deleted_by_admins_only() -> None:
    repo = InMemoryTopicRepository()
    topic = create_topic(repo, user(9, Role.ADMIN), name="P", query="p", public=True)
    assert topic.id is not None
    with pytest.raises(PermissionDeniedError):
        delete_topic(repo, user(1), topic.id)
    delete_topic(repo, user(9, Role.ADMIN), topic.id)


def test_deleting_a_missing_topic() -> None:
    with pytest.raises(RecordNotFoundError):
        delete_topic(InMemoryTopicRepository(), user(1), 123)
