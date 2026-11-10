from typing import Annotated

from fastapi import APIRouter, Query

from scitracker.api.deps import PROTECTED, CurrentUser, Repositories
from scitracker.api.pagination import MAX_ID, decode_cursor, encode_cursor
from scitracker.api.problems import ProblemDetails
from scitracker.api.publications import PublicationOut, PublicationPage
from scitracker.services.feed import user_feed

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get(
    "",
    response_model=PublicationPage,
    summary="New publications in my topics",
    description=(
        "Publications of the public topics and of your own topics, newest first. "
        "Cursor pagination, the same as in the search."
    ),
    responses={**PROTECTED, 404: {"model": ProblemDetails}, 422: {"model": ProblemDetails}},
)
def feed(
    user: CurrentUser,
    repositories: Repositories,
    topic: Annotated[
        int | None, Query(ge=1, le=MAX_ID, description="Only this topic (public or your own)")
    ] = None,
    cursor: Annotated[str | None, Query(max_length=100, description="From `next_cursor`")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PublicationPage:
    after_id = decode_cursor(cursor) if cursor else None
    page = user_feed(
        repositories.publications,
        repositories.topics,
        user,
        topic_id=topic,
        after_id=after_id,
        limit=limit,
    )
    return PublicationPage(
        items=[PublicationOut.from_domain(item) for item in page.items],
        next_cursor=encode_cursor(page.next_after_id) if page.next_after_id else None,
    )
