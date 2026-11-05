from datetime import date
from typing import Annotated, Self

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field

from scitracker.api.deps import Repositories
from scitracker.api.pagination import MAX_ID, decode_cursor, encode_cursor
from scitracker.api.problems import ProblemDetails
from scitracker.domain.errors import RecordNotFoundError
from scitracker.domain.publication import Publication
from scitracker.services.ports import SearchCriteria
from scitracker.services.search import search_publications

router = APIRouter(prefix="/publications", tags=["publications"])


class PublicationOut(BaseModel):
    id: int
    title: str
    authors: list[str]
    doi: str | None
    arxiv_id: str | None
    abstract: str | None
    published_on: date | None
    url: str | None

    @classmethod
    def from_domain(cls, publication: Publication) -> Self:
        if publication.id is None:  # pragma: no cover - stored records always have an id
            raise ValueError("only stored publications can be returned by the API")
        return cls(
            id=publication.id,
            title=publication.title,
            authors=[author.name for author in publication.authors],
            doi=publication.doi,
            arxiv_id=publication.arxiv_id,
            abstract=publication.abstract,
            published_on=publication.published_on,
            url=publication.url,
        )


class PublicationPage(BaseModel):
    items: list[PublicationOut]
    next_cursor: str | None = Field(
        description="Pass it as `cursor` to get the next page. Null on the last page."
    )


@router.get(
    "",
    response_model=PublicationPage,
    summary="Search publications",
    responses={422: {"model": ProblemDetails}},
)
def list_publications(  # noqa: PLR0913, PLR0917
    repositories: Repositories,
    q: Annotated[
        str | None, Query(min_length=1, max_length=200, description="Part of the title")
    ] = None,
    author: Annotated[
        str | None, Query(min_length=1, max_length=200, description="Part of an author name")
    ] = None,
    topic: Annotated[int | None, Query(ge=1, le=MAX_ID, description="Topic id")] = None,
    published_from: Annotated[
        date | None, Query(alias="from", description="Published on or after (YYYY-MM-DD)")
    ] = None,
    cursor: Annotated[str | None, Query(max_length=100, description="From `next_cursor`")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PublicationPage:
    criteria = SearchCriteria(
        query=q.strip() if q else None,
        author=author.strip() if author else None,
        topic_id=topic,
        published_from=published_from,
    )
    after_id = decode_cursor(cursor) if cursor else None
    page = search_publications(repositories.publications, criteria, after_id=after_id, limit=limit)
    return PublicationPage(
        items=[PublicationOut.from_domain(item) for item in page.items],
        next_cursor=encode_cursor(page.next_after_id) if page.next_after_id else None,
    )


@router.get(
    "/{publication_id}",
    response_model=PublicationOut,
    summary="Get a publication",
    responses={404: {"model": ProblemDetails}, 422: {"model": ProblemDetails}},
)
def get_publication(
    publication_id: Annotated[int, Path(ge=1, le=MAX_ID)], repositories: Repositories
) -> PublicationOut:
    publication = repositories.publications.get(publication_id)
    if publication is None:
        raise RecordNotFoundError(f"publication {publication_id} does not exist")
    return PublicationOut.from_domain(publication)
