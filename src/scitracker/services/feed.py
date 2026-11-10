from scitracker.domain.user import User
from scitracker.services.ports import PublicationReader, SearchCriteria, TopicRepository
from scitracker.services.search import Page, search_publications
from scitracker.services.topics import find_visible_topic, visible_topics


def user_feed(  # noqa: PLR0913
    reader: PublicationReader,
    topics: TopicRepository,
    user: User,
    *,
    topic_id: int | None = None,
    after_id: int | None = None,
    limit: int = 20,
) -> Page:
    """New publications in the topics the user can see (or in one of them)."""
    selected = (
        [find_visible_topic(topics, user, topic_id)]
        if topic_id is not None
        else visible_topics(topics, user)
    )
    ids = tuple(topic.id for topic in selected if topic.id is not None)
    if not ids:
        return Page([], None)
    return search_publications(
        reader, SearchCriteria(topic_ids=ids), after_id=after_id, limit=limit
    )
