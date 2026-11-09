from datetime import datetime
from typing import Annotated, Self

from fastapi import APIRouter, Path, Query, Response
from pydantic import BaseModel, Field

from scitracker.api.deps import PROTECTED, CurrentUser, Now, Repositories
from scitracker.api.pagination import MAX_ID, decode_cursor, encode_cursor
from scitracker.api.problems import ProblemDetails
from scitracker.domain.reading import Note, ReadingItem, StatusChange
from scitracker.domain.status import ReadingStatus
from scitracker.domain.user import User
from scitracker.services import reading as service

router = APIRouter(prefix="/reading-list", tags=["reading-list"])

ItemId = Annotated[int, Path(ge=1, le=MAX_ID)]


def _uid(user: User) -> int:
    if user.id is None:  # pragma: no cover - authenticated users are always stored
        raise ValueError("user is not stored")
    return user.id


class ReadingItemOut(BaseModel):
    id: int
    publication_id: int
    status: ReadingStatus
    added_at: datetime
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, item: ReadingItem) -> Self:
        if item.id is None:  # pragma: no cover - stored items always have an id
            raise ValueError("only stored items can be returned by the API")
        return cls(
            id=item.id,
            publication_id=item.publication_id,
            status=item.status,
            added_at=item.added_at,
            finished_at=item.finished_at,
        )


class ReadingListPage(BaseModel):
    items: list[ReadingItemOut]
    next_cursor: str | None


class AddIn(BaseModel):
    publication_id: int = Field(ge=1, le=MAX_ID)


class StatusIn(BaseModel):
    status: ReadingStatus


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


class NoteOut(BaseModel):
    id: int
    text: str
    created_at: datetime

    @classmethod
    def from_domain(cls, note: Note) -> Self:
        if note.id is None:  # pragma: no cover - stored notes always have an id
            raise ValueError("only stored notes can be returned by the API")
        return cls(id=note.id, text=note.text, created_at=note.created_at)


class StatusChangeOut(BaseModel):
    from_status: ReadingStatus
    to_status: ReadingStatus
    changed_at: datetime

    @classmethod
    def from_domain(cls, change: StatusChange) -> Self:
        return cls(
            from_status=change.from_status,
            to_status=change.to_status,
            changed_at=change.changed_at,
        )


@router.post(
    "",
    status_code=201,
    response_model=ReadingItemOut,
    summary="Add a publication to my reading list",
    description="Idempotent: 201 when created, 200 with the existing item when already added.",
    responses={
        **PROTECTED,
        200: {"model": ReadingItemOut, "description": "Already in the list"},
        404: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
def add_item(
    body: AddIn, response: Response, user: CurrentUser, repositories: Repositories, now: Now
) -> ReadingItemOut:
    result = service.add_to_reading_list(
        repositories.reading, repositories.publications, _uid(user), body.publication_id, now
    )
    repositories.commit()
    if not result.created:
        response.status_code = 200
    return ReadingItemOut.from_domain(result.item)


@router.get(
    "",
    response_model=ReadingListPage,
    summary="My reading list",
    responses={**PROTECTED, 422: {"model": ProblemDetails}},
)
def list_items(
    user: CurrentUser,
    repositories: Repositories,
    status: Annotated[ReadingStatus | None, Query(description="Filter by status")] = None,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReadingListPage:
    after_id = decode_cursor(cursor) if cursor else None
    page = service.list_reading_list(
        repositories.reading, _uid(user), status=status, after_id=after_id, limit=limit
    )
    return ReadingListPage(
        items=[ReadingItemOut.from_domain(item) for item in page.items],
        next_cursor=encode_cursor(page.next_after_id) if page.next_after_id else None,
    )


@router.patch(
    "/{item_id}",
    response_model=ReadingItemOut,
    summary="Change the reading status",
    description=(
        "Order: to_read, reading, done. One step forward or back; skipping is rejected (409). "
        "Repeating the current status changes nothing (the finish date is kept)."
    ),
    responses={
        **PROTECTED,
        404: {"model": ProblemDetails},
        409: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
def patch_item(
    item_id: ItemId, body: StatusIn, user: CurrentUser, repositories: Repositories, now: Now
) -> ReadingItemOut:
    item = service.change_status(repositories.reading, _uid(user), item_id, body.status, now)
    repositories.commit()
    return ReadingItemOut.from_domain(item)


@router.get(
    "/{item_id}/history",
    response_model=list[StatusChangeOut],
    summary="Status history of an item",
    responses={**PROTECTED, 404: {"model": ProblemDetails}, 422: {"model": ProblemDetails}},
)
def item_history(
    item_id: ItemId, user: CurrentUser, repositories: Repositories
) -> list[StatusChangeOut]:
    changes = service.get_history(repositories.reading, _uid(user), item_id)
    return [StatusChangeOut.from_domain(change) for change in changes]


@router.post(
    "/{item_id}/notes",
    status_code=201,
    response_model=NoteOut,
    summary="Add a private note",
    responses={**PROTECTED, 404: {"model": ProblemDetails}, 422: {"model": ProblemDetails}},
)
def post_note(
    item_id: ItemId, body: NoteIn, user: CurrentUser, repositories: Repositories, now: Now
) -> NoteOut:
    note = service.add_note(repositories.reading, _uid(user), item_id, body.text, now)
    repositories.commit()
    return NoteOut.from_domain(note)


@router.get(
    "/{item_id}/notes",
    response_model=list[NoteOut],
    summary="My notes on an item",
    responses={**PROTECTED, 404: {"model": ProblemDetails}, 422: {"model": ProblemDetails}},
)
def get_notes(item_id: ItemId, user: CurrentUser, repositories: Repositories) -> list[NoteOut]:
    notes = service.list_notes(repositories.reading, _uid(user), item_id)
    return [NoteOut.from_domain(note) for note in notes]
