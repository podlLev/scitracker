import pytest

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.topic import Topic
from scitracker.domain.user import Role, User

FAKE_HASH = "not-a-real-hash"


def test_topic_fields_are_stripped() -> None:
    topic = Topic(name="  ML  ", query=" machine learning ")
    assert (topic.name, topic.query) == ("ML", "machine learning")


def test_topic_without_owner_is_admin_managed() -> None:
    assert Topic(name="ML", query="machine learning").owner_id is None


def test_blank_topic_name_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        Topic(name="  ", query="machine learning")


def test_blank_topic_query_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        Topic(name="ML", query="  ")


def test_email_is_normalized_and_default_role_is_user() -> None:
    user = User(email="  Ivan@Example.COM ", password_hash=FAKE_HASH)
    assert user.email == "ivan@example.com"
    assert user.role is Role.USER


def test_admin_role_can_be_set() -> None:
    user = User(email="a@example.com", password_hash=FAKE_HASH, role=Role.ADMIN)
    assert user.role is Role.ADMIN


@pytest.mark.parametrize("email", ["", "no-at", "a@b", "@example.com"])
def test_invalid_email_is_rejected(email: str) -> None:
    with pytest.raises(InvalidValueError):
        User(email=email, password_hash=FAKE_HASH)


def test_empty_password_hash_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        User(email="a@example.com", password_hash="")
