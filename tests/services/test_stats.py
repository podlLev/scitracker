from datetime import UTC, date, datetime

import pytest

from scitracker.domain.errors import InvalidValueError, RecordNotFoundError
from scitracker.domain.topic import Topic
from scitracker.domain.user import User
from scitracker.services.ports import AuthorCount, MonthlyCount
from scitracker.services.stats import (
    MAX_SPAN_DAYS,
    reading_summary,
    top_authors,
    topic_dynamics,
)
from tests.services.fakes import InMemoryTopicRepository, StubStatsRepository

TODAY = date(2026, 11, 10)
ALICE = User(email="a@example.com", password_hash="h", id=1)


def topics_repo() -> InMemoryTopicRepository:
    repo = InMemoryTopicRepository()
    repo.add(Topic(name="Public", query="p"))  # id 1
    repo.add(Topic(name="Mine", query="m", owner_id=1))  # id 2
    repo.add(Topic(name="Theirs", query="t", owner_id=2))  # id 3
    return repo


def labels(points: list) -> list[tuple[int, int]]:  # type: ignore[type-arg]
    return [(p.year, p.month) for p in points]


def test_default_period_is_the_last_twelve_months_and_covers_visible_topics_only() -> None:
    stats = StubStatsRepository()
    result = topic_dynamics(topics_repo(), stats, ALICE, start=None, end=None, today=TODAY)
    assert (result.start, result.end) == (date(2025, 12, 1), TODAY)
    assert stats.last_monthly is not None
    assert stats.last_monthly[0] == [1, 2]  # public and own, never somebody else's private one
    assert len(result.series[0].points) == 12
    assert labels(result.series[0].points)[0] == (2025, 12)
    assert labels(result.series[0].points)[-1] == (2026, 11)


def test_empty_months_are_filled_with_zeros_and_totals_add_up() -> None:
    stats = StubStatsRepository(monthly=[MonthlyCount(1, 2026, 1, 2), MonthlyCount(1, 2026, 3, 5)])
    result = topic_dynamics(
        topics_repo(),
        stats,
        ALICE,
        start=date(2026, 1, 1),
        end=date(2026, 3, 31),
        today=TODAY,
        topic_id=1,
    )
    [series] = result.series
    assert [p.count for p in series.points] == [2, 0, 5]
    assert series.total == 7


def test_months_cross_the_year_boundary() -> None:
    result = topic_dynamics(
        topics_repo(),
        StubStatsRepository(),
        ALICE,
        start=date(2025, 11, 15),
        end=date(2026, 2, 1),
        today=TODAY,
        topic_id=1,
    )
    assert labels(result.series[0].points) == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def test_foreign_private_topic_looks_missing() -> None:
    with pytest.raises(RecordNotFoundError):
        topic_dynamics(
            topics_repo(),
            StubStatsRepository(),
            ALICE,
            start=None,
            end=None,
            today=TODAY,
            topic_id=3,
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 5, 1), date(2026, 4, 1)), (date(2010, 1, 1), date(2026, 1, 1))],
)
def test_invalid_periods_are_rejected(start: date, end: date) -> None:
    assert (end - start).days > MAX_SPAN_DAYS or start > end
    with pytest.raises(InvalidValueError):
        topic_dynamics(
            topics_repo(), StubStatsRepository(), ALICE, start=start, end=end, today=TODAY
        )


def test_top_authors_checks_visibility_and_passes_the_limit() -> None:
    stats = StubStatsRepository(authors=[AuthorCount("Ann", 3), AuthorCount("Bob", 1)])
    result = top_authors(topics_repo(), stats, ALICE, 2, start=None, end=None, limit=1)
    assert result == [AuthorCount("Ann", 3)]
    with pytest.raises(RecordNotFoundError):
        top_authors(topics_repo(), stats, ALICE, 3, start=None, end=None, limit=5)


def test_top_authors_rejects_a_reversed_period() -> None:
    with pytest.raises(InvalidValueError):
        top_authors(
            topics_repo(),
            StubStatsRepository(),
            ALICE,
            1,
            start=date(2026, 5, 1),
            end=date(2026, 4, 1),
            limit=5,
        )


def test_reading_summary_defaults_to_30_days_with_an_inclusive_end() -> None:
    stats = StubStatsRepository()
    result = reading_summary(stats, 1, start=None, end=None, today=TODAY)
    assert (result.start, result.end) == (date(2026, 10, 12), TODAY)
    assert stats.last_reading == (
        1,
        datetime(2026, 10, 12, tzinfo=UTC),
        datetime(2026, 11, 11, tzinfo=UTC),  # the end day is included
    )


def test_reading_period_end_is_cut_to_today() -> None:
    result = reading_summary(
        StubStatsRepository(), 1, start=date(2026, 11, 1), end=date(2030, 1, 1), today=TODAY
    )
    assert result.end == TODAY


def test_reading_period_starting_in_the_future_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        reading_summary(StubStatsRepository(), 1, start=date(2027, 1, 1), end=None, today=TODAY)
