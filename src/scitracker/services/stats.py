from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.topic import Topic
from scitracker.domain.user import User
from scitracker.services.ports import AuthorCount, ReadingCounts, StatsRepository, TopicRepository
from scitracker.services.topics import find_visible_topic, visible_topics

MAX_SPAN_DAYS = 3660  # about ten years: bounds the size of a response
DEFAULT_MONTHS = 12
DEFAULT_READING_DAYS = 30


@dataclass(frozen=True, slots=True)
class MonthPoint:
    year: int
    month: int
    count: int


@dataclass(frozen=True, slots=True)
class TopicSeries:
    topic: Topic
    points: list[MonthPoint]

    @property
    def total(self) -> int:
        return sum(point.count for point in self.points)


@dataclass(frozen=True, slots=True)
class Dynamics:
    start: date
    end: date
    series: list[TopicSeries]


@dataclass(frozen=True, slots=True)
class ReadingSummary:
    start: date
    end: date
    counts: ReadingCounts


def _check_period(start: date, end: date) -> None:
    if start > end:
        raise InvalidValueError("'from' must not be later than 'to'")
    if (end - start).days > MAX_SPAN_DAYS:
        raise InvalidValueError("the period must not exceed ten years")


def _first_of_month(day: date, months_back: int) -> date:
    index = day.year * 12 + (day.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


def _months(start: date, end: date) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        result.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


def topic_dynamics(  # noqa: PLR0913
    topics: TopicRepository,
    stats: StatsRepository,
    user: User,
    *,
    start: date | None,
    end: date | None,
    today: date,
    topic_id: int | None = None,
) -> Dynamics:
    """Monthly publication counts per visible topic; empty months are filled with zeros."""
    end = end or today
    start = start or _first_of_month(end, DEFAULT_MONTHS - 1)
    _check_period(start, end)
    selected = (
        [find_visible_topic(topics, user, topic_id)]
        if topic_id is not None
        else visible_topics(topics, user)
    )
    ids = [topic.id for topic in selected if topic.id is not None]
    counts = {
        (row.topic_id, row.year, row.month): row.count
        for row in stats.monthly_counts(ids, start=start, end=end)
    }
    months = _months(start, end)
    series: list[TopicSeries] = []
    for topic in selected:
        if topic.id is None:  # pragma: no cover - stored topics always have an id
            continue
        points = [
            MonthPoint(year, month, counts.get((topic.id, year, month), 0))
            for year, month in months
        ]
        series.append(TopicSeries(topic, points))
    return Dynamics(start, end, series)


def top_authors(  # noqa: PLR0913
    topics: TopicRepository,
    stats: StatsRepository,
    user: User,
    topic_id: int,
    *,
    start: date | None,
    end: date | None,
    limit: int,
) -> list[AuthorCount]:
    find_visible_topic(topics, user, topic_id)
    if start is not None and end is not None:
        _check_period(start, end)
    return stats.top_authors(topic_id, start=start, end=end, limit=limit)


def reading_summary(
    stats: StatsRepository,
    user_id: int,
    *,
    start: date | None,
    end: date | None,
    today: date,
) -> ReadingSummary:
    end = min(end or today, today)  # nothing can happen in the future
    start = start or end - timedelta(days=DEFAULT_READING_DAYS - 1)
    _check_period(start, end)
    lower = datetime.combine(start, time.min, tzinfo=UTC)
    upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)  # end is inclusive
    return ReadingSummary(start, end, stats.reading_counts(user_id, start=lower, end=upper))
