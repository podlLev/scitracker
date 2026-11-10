from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from scitracker.api.deps import PROTECTED, CurrentUser, Now, Repositories
from scitracker.api.pagination import MAX_ID
from scitracker.api.problems import ProblemDetails
from scitracker.domain.status import ReadingStatus
from scitracker.domain.user import User
from scitracker.services import stats as service

router = APIRouter(prefix="/stats", tags=["stats"])

FromDate = Annotated[
    date | None, Query(alias="from", description="Start of the period, YYYY-MM-DD (inclusive)")
]
ToDate = Annotated[
    date | None, Query(alias="to", description="End of the period, YYYY-MM-DD (inclusive)")
]
ERRORS = {**PROTECTED, 404: {"model": ProblemDetails}, 422: {"model": ProblemDetails}}


def _uid(user: User) -> int:
    if user.id is None:  # pragma: no cover - authenticated users are always stored
        raise ValueError("user is not stored")
    return user.id


class MonthPointOut(BaseModel):
    month: str = Field(examples=["2026-03"])
    count: int


class TopicSeriesOut(BaseModel):
    topic_id: int
    topic: str
    total: int
    points: list[MonthPointOut]


class DynamicsOut(BaseModel):
    start: date
    end: date
    series: list[TopicSeriesOut]


class AuthorCountOut(BaseModel):
    author: str
    publications: int


class TopAuthorsOut(BaseModel):
    topic_id: int
    start: date | None
    end: date | None
    authors: list[AuthorCountOut]


class ReadingStatsOut(BaseModel):
    start: date
    end: date
    added: int = Field(description="Items added to the list during the period")
    finished: int = Field(description="Items whose finish date falls into the period")
    by_status: dict[ReadingStatus, int] = Field(description="The whole list right now")


@router.get(
    "/by-topic",
    response_model=DynamicsOut,
    summary="Publications per topic by month",
    description=(
        "Counted by publication date; publications without a date are not included. "
        "Default period: the last 12 months. At most ten years."
    ),
    responses=ERRORS,
)
def by_topic(  # noqa: PLR0913, PLR0917
    user: CurrentUser,
    repositories: Repositories,
    now: Now,
    published_from: FromDate = None,
    published_to: ToDate = None,
    topic: Annotated[int | None, Query(ge=1, le=MAX_ID, description="One topic only")] = None,
) -> DynamicsOut:
    result = service.topic_dynamics(
        repositories.topics,
        repositories.stats,
        user,
        start=published_from,
        end=published_to,
        today=now.date(),
        topic_id=topic,
    )
    return DynamicsOut(
        start=result.start,
        end=result.end,
        series=[
            TopicSeriesOut(
                topic_id=item.topic.id or 0,
                topic=item.topic.name,
                total=item.total,
                points=[
                    MonthPointOut(month=f"{p.year:04d}-{p.month:02d}", count=p.count)
                    for p in item.points
                ],
            )
            for item in result.series
        ],
    )


@router.get(
    "/top-authors",
    response_model=TopAuthorsOut,
    summary="Most productive authors of a topic",
    description="Authors are matched by name (see ADR-003), so spelling variants count separately.",
    responses=ERRORS,
)
def top_authors(  # noqa: PLR0913, PLR0917
    user: CurrentUser,
    repositories: Repositories,
    topic: Annotated[int, Query(ge=1, le=MAX_ID, description="Topic id")],
    published_from: FromDate = None,
    published_to: ToDate = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> TopAuthorsOut:
    authors = service.top_authors(
        repositories.topics,
        repositories.stats,
        user,
        topic,
        start=published_from,
        end=published_to,
        limit=limit,
    )
    return TopAuthorsOut(
        topic_id=topic,
        start=published_from,
        end=published_to,
        authors=[AuthorCountOut(author=a.name, publications=a.publications) for a in authors],
    )


@router.get(
    "/reading",
    response_model=ReadingStatsOut,
    summary="My reading statistics",
    description="Default period: the last 30 days. A future end date is cut to today.",
    responses={**PROTECTED, 422: {"model": ProblemDetails}},
)
def reading(
    user: CurrentUser,
    repositories: Repositories,
    now: Now,
    published_from: FromDate = None,
    published_to: ToDate = None,
) -> ReadingStatsOut:
    summary = service.reading_summary(
        repositories.stats, _uid(user), start=published_from, end=published_to, today=now.date()
    )
    return ReadingStatsOut(
        start=summary.start,
        end=summary.end,
        added=summary.counts.added,
        finished=summary.counts.finished,
        by_status=summary.counts.by_status,
    )
