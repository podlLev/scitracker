from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from scitracker.domain.publication import Author, Publication
from scitracker.domain.status import ReadingStatus
from scitracker.domain.topic import Topic
from scitracker.domain.user import User
from scitracker.services.ports import AuthorCount, MonthlyCount, SearchCriteria
from scitracker.services.reading import change_status
from scitracker.services.report import TopicTotal
from scitracker.storage.repositories import (
    SqlPublicationRepository,
    SqlReadingListRepository,
    SqlTopicRepository,
    SqlUserRepository,
)
from scitracker.storage.stats import SqlStatsRepository

S = ReadingStatus


def make_topic(session: Session, name: str) -> int:
    saved = SqlTopicRepository(session).add(Topic(name=name, query=name.lower()))
    assert saved.id is not None
    return saved.id


def make_pub(
    session: Session,
    number: int,
    *,
    published_on: date | None,
    authors: tuple[str, ...] = ("Ann Lee",),
    topics: tuple[int, ...] = (),
) -> int:
    repo = SqlPublicationRepository(session)
    saved = repo.add(
        Publication(
            title=f"P{number}",
            authors=[Author(name) for name in authors],
            doi=f"10.1000/st{number}",
            published_on=published_on,
        )
    )
    assert saved.id is not None
    for topic_id in topics:
        repo.link_topic(saved.id, topic_id)
    return saved.id


def test_monthly_counts_group_by_topic_and_month_inside_the_period(session: Session) -> None:
    ml, other = make_topic(session, "ML"), make_topic(session, "Other")
    make_pub(session, 1, published_on=date(2026, 1, 10), topics=(ml,))
    make_pub(session, 2, published_on=date(2026, 1, 25), topics=(ml, other))
    make_pub(session, 3, published_on=date(2026, 3, 1), topics=(ml,))
    make_pub(session, 4, published_on=None, topics=(ml,))  # undated: not counted
    make_pub(session, 5, published_on=date(2025, 12, 31), topics=(ml,))  # before the period
    make_pub(session, 6, published_on=date(2026, 2, 1))  # no topic
    rows = SqlStatsRepository(session).monthly_counts(
        [ml, other], start=date(2026, 1, 1), end=date(2026, 3, 31)
    )
    assert sorted(rows, key=lambda r: (r.topic_id, r.month)) == [
        MonthlyCount(ml, 2026, 1, 2),
        MonthlyCount(ml, 2026, 3, 1),
        MonthlyCount(other, 2026, 1, 1),
    ]


def test_monthly_counts_without_topics_is_empty(session: Session) -> None:
    assert (
        SqlStatsRepository(session).monthly_counts(
            [], start=date(2026, 1, 1), end=date(2026, 3, 31)
        )
        == []
    )


def test_period_bounds_are_inclusive(session: Session) -> None:
    topic = make_topic(session, "ML")
    make_pub(session, 1, published_on=date(2026, 1, 1), topics=(topic,))
    make_pub(session, 2, published_on=date(2026, 1, 31), topics=(topic,))
    rows = SqlStatsRepository(session).monthly_counts(
        [topic], start=date(2026, 1, 1), end=date(2026, 1, 31)
    )
    assert [r.count for r in rows] == [2]


def test_top_authors_are_ordered_by_count_then_name(session: Session) -> None:
    topic, other = make_topic(session, "ML"), make_topic(session, "Other")
    make_pub(
        session, 1, published_on=date(2026, 1, 1), authors=("Ann Lee", "Cy Dee"), topics=(topic,)
    )
    make_pub(
        session, 2, published_on=date(2026, 2, 1), authors=("Ann Lee", "Bob Ray"), topics=(topic,)
    )
    make_pub(session, 3, published_on=date(2026, 3, 1), authors=("Ann Lee",), topics=(topic,))
    make_pub(session, 4, published_on=date(2026, 4, 1), authors=("Zed Zed",), topics=(other,))
    stats = SqlStatsRepository(session)
    everything = stats.top_authors(topic, start=None, end=None, limit=10)
    assert everything == [
        AuthorCount("Ann Lee", 3),
        AuthorCount("Bob Ray", 1),  # a tie with Cy Dee is broken by name
        AuthorCount("Cy Dee", 1),
    ]
    assert stats.top_authors(topic, start=None, end=None, limit=1) == [AuthorCount("Ann Lee", 3)]
    early = stats.top_authors(topic, start=date(2026, 1, 1), end=date(2026, 1, 31), limit=10)
    assert early == [AuthorCount("Ann Lee", 1), AuthorCount("Cy Dee", 1)]


def test_reading_counts_cover_the_period_and_the_whole_list(session: Session) -> None:
    user_repo = SqlUserRepository(session)
    me = user_repo.add(User(email="me@example.com", password_hash="h"))
    someone = user_repo.add(User(email="x@example.com", password_hash="h"))
    assert me.id is not None
    assert someone.id is not None
    reading = SqlReadingListRepository(session)
    pubs = [make_pub(session, n, published_on=None) for n in range(4)]
    day = datetime(2026, 11, 2, 12, tzinfo=UTC)
    first, _ = reading.add_if_absent(me.id, pubs[0], day)
    old, _ = reading.add_if_absent(me.id, pubs[1], day - timedelta(days=40))
    reading.add_if_absent(me.id, pubs[2], day + timedelta(days=3))
    reading.add_if_absent(someone.id, pubs[3], day)  # another user's item never counts
    assert first.id is not None
    assert old.id is not None
    change_status(reading, me.id, first.id, S.READING, day)
    change_status(reading, me.id, first.id, S.DONE, day + timedelta(days=1))
    counts = SqlStatsRepository(session).reading_counts(
        me.id, start=datetime(2026, 11, 1, tzinfo=UTC), end=datetime(2026, 12, 1, tzinfo=UTC)
    )
    assert (counts.added, counts.finished) == (2, 1)
    assert counts.by_status == {S.TO_READ: 2, S.READING: 0, S.DONE: 1}


def test_search_by_several_topics_returns_each_publication_once(session: Session) -> None:
    first, second = make_topic(session, "A"), make_topic(session, "B")
    both = make_pub(session, 1, published_on=None, topics=(first, second))
    only_second = make_pub(session, 2, published_on=None, topics=(second,))
    make_pub(session, 3, published_on=None)
    found = SqlPublicationRepository(session).search(
        SearchCriteria(topic_ids=(first, second)), after_id=None, limit=10
    )
    assert [p.id for p in found] == [only_second, both]


def test_overview_counts_everything_and_lists_public_topics_only(session: Session) -> None:
    users = SqlUserRepository(session)
    owner = users.add(User(email="o@example.com", password_hash="h"))
    assert owner.id is not None
    topics = SqlTopicRepository(session)
    public = topics.add(Topic(name="Public", query="p"))
    topics.add(Topic(name="Private", query="q", owner_id=owner.id))
    assert public.id is not None
    make_pub(session, 1, published_on=None, topics=(public.id,))
    SqlPublicationRepository(session).add(
        Publication(title="No DOI", authors=[], arxiv_id="2101.00001")
    )
    overview = SqlStatsRepository(session).overview()
    assert (overview.publications, overview.without_doi) == (2, 1)
    assert overview.authors == 1
    assert (overview.users, overview.reading_items, overview.private_topics) == (1, 0, 1)
    assert overview.topics == [TopicTotal("Public", 1)]
