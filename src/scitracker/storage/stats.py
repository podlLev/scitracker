from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import ColumnElement, extract, func, select
from sqlalchemy.orm import Session

from scitracker.domain.status import ReadingStatus
from scitracker.services.ports import AuthorCount, MonthlyCount, ReadingCounts
from scitracker.storage.models import (
    AuthorRow,
    PublicationAuthorRow,
    PublicationRow,
    PublicationTopicRow,
    ReadingItemRow,
)


class SqlStatsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def monthly_counts(
        self, topic_ids: Sequence[int], *, start: date, end: date
    ) -> list[MonthlyCount]:
        if not topic_ids:
            return []
        # EXTRACT instead of date_trunc: a date is not shifted by the session time zone,
        # and no bind parameter appears twice (GROUP BY must match the SELECT list).
        year = extract("year", PublicationRow.published_on)
        month = extract("month", PublicationRow.published_on)
        stmt = (
            select(
                PublicationTopicRow.topic_id,
                year.label("y"),
                month.label("m"),
                func.count().label("n"),
            )
            .join(PublicationRow, PublicationRow.id == PublicationTopicRow.publication_id)
            .where(
                PublicationTopicRow.topic_id.in_(topic_ids),
                PublicationRow.published_on >= start,
                PublicationRow.published_on <= end,
            )
            .group_by(PublicationTopicRow.topic_id, year, month)
        )
        return [
            MonthlyCount(topic_id=row.topic_id, year=int(row.y), month=int(row.m), count=row.n)
            for row in self._session.execute(stmt)
        ]

    def top_authors(
        self, topic_id: int, *, start: date | None, end: date | None, limit: int
    ) -> list[AuthorCount]:
        total = func.count(PublicationAuthorRow.publication_id)
        stmt = (
            select(AuthorRow.name, total.label("n"))
            .join(PublicationAuthorRow, PublicationAuthorRow.author_id == AuthorRow.id)
            .join(PublicationRow, PublicationRow.id == PublicationAuthorRow.publication_id)
            .join(PublicationTopicRow, PublicationTopicRow.publication_id == PublicationRow.id)
            .where(PublicationTopicRow.topic_id == topic_id)
            .group_by(AuthorRow.id, AuthorRow.name)
            .order_by(total.desc(), AuthorRow.name)
            .limit(limit)
        )
        if start is not None:
            stmt = stmt.where(PublicationRow.published_on >= start)
        if end is not None:
            stmt = stmt.where(PublicationRow.published_on <= end)
        return [
            AuthorCount(name=row.name, publications=row.n) for row in self._session.execute(stmt)
        ]

    def reading_counts(self, user_id: int, *, start: datetime, end: datetime) -> ReadingCounts:
        mine = ReadingItemRow.user_id == user_id
        added = self._count(mine, ReadingItemRow.added_at >= start, ReadingItemRow.added_at < end)
        finished = self._count(
            mine, ReadingItemRow.finished_at >= start, ReadingItemRow.finished_at < end
        )
        by_status = dict.fromkeys(ReadingStatus, 0)
        rows = self._session.execute(
            select(ReadingItemRow.status, func.count()).where(mine).group_by(ReadingItemRow.status)
        )
        for status, number in rows:
            by_status[ReadingStatus(status)] = number
        return ReadingCounts(added=added, finished=finished, by_status=by_status)

    def _count(self, *conditions: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(ReadingItemRow).where(*conditions)
        return self._session.scalar(stmt) or 0
