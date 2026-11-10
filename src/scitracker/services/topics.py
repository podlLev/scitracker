from scitracker.domain.errors import (
    InvalidValueError,
    PermissionDeniedError,
    QuotaExceededError,
    RecordNotFoundError,
)
from scitracker.domain.topic import Topic
from scitracker.domain.user import Role, User
from scitracker.services.ports import TopicRepository

MAX_PRIVATE_TOPICS = 20  # every topic costs requests to external sources on each collection


def _user_id(actor: User) -> int:
    if actor.id is None:  # pragma: no cover - authenticated users are always stored
        raise InvalidValueError("user is not stored")
    return actor.id


def create_topic(
    topics: TopicRepository, actor: User, *, name: str, query: str, public: bool
) -> Topic:
    if public:
        if actor.role is not Role.ADMIN:
            raise PermissionDeniedError("Only administrators can create public topics.")
        owner_id = None
    else:
        owner_id = _user_id(actor)
        if len(topics.list_owned(owner_id)) >= MAX_PRIVATE_TOPICS:
            raise QuotaExceededError(f"At most {MAX_PRIVATE_TOPICS} private topics are allowed.")
    return topics.add(Topic(name=name, query=query, owner_id=owner_id))


def delete_topic(topics: TopicRepository, actor: User, topic_id: int) -> None:
    topic = topics.get(topic_id)
    if topic is None:
        raise RecordNotFoundError(f"topic {topic_id} does not exist")
    if topic.owner_id is None:  # public: administrators only
        if actor.role is not Role.ADMIN:
            raise PermissionDeniedError("Only administrators can delete public topics.")
    elif topic.owner_id != actor.id:  # someone else's private topic: do not reveal it exists
        raise RecordNotFoundError(f"topic {topic_id} does not exist")
    topics.delete(topic_id)


def visible_topics(topics: TopicRepository, actor: User) -> list[Topic]:
    """Public topics plus the user's own private ones."""
    return [*topics.list_public(), *topics.list_owned(_user_id(actor))]


def find_visible_topic(topics: TopicRepository, actor: User, topic_id: int) -> Topic:
    """Someone else's private topic looks exactly like a missing one."""
    for topic in visible_topics(topics, actor):
        if topic.id == topic_id:
            return topic
    raise RecordNotFoundError(f"topic {topic_id} does not exist")
