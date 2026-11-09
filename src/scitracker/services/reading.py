from dataclasses import dataclass
from datetime import datetime

from scitracker.domain.errors import RecordNotFoundError
from scitracker.domain.reading import Note, ReadingItem, StatusChange
from scitracker.domain.status import ReadingStatus
from scitracker.services.ports import PublicationReader, ReadingListRepository


@dataclass(frozen=True, slots=True)
class AddResult:
    item: ReadingItem
    created: bool


@dataclass(frozen=True, slots=True)
class ReadingPage:
    items: list[ReadingItem]
    next_after_id: int | None  # None on the last page


def _not_found(item_id: int) -> RecordNotFoundError:
    # The same message for "missing" and "belongs to someone else".
    return RecordNotFoundError(f"reading list item {item_id} does not exist")


def _owned(reading: ReadingListRepository, user_id: int, item_id: int) -> ReadingItem:
    item = reading.get(item_id, user_id)
    if item is None:
        raise _not_found(item_id)
    return item


def add_to_reading_list(
    reading: ReadingListRepository,
    publications: PublicationReader,
    user_id: int,
    publication_id: int,
    at: datetime,
) -> AddResult:
    """Idempotent: adding the same publication again returns the existing item."""
    if publications.get(publication_id) is None:
        raise RecordNotFoundError(f"publication {publication_id} does not exist")
    item, created = reading.add_if_absent(user_id, publication_id, at)
    return AddResult(item, created)


def change_status(
    reading: ReadingListRepository,
    user_id: int,
    item_id: int,
    target: ReadingStatus,
    at: datetime,
) -> ReadingItem:
    """Move the item to `target`. The caller commits; any error leaves nothing behind.

    The row is locked first, so two concurrent requests cannot both act on the old state:
    the second one waits, sees the new status and changes nothing.
    """
    item = reading.get_for_update(item_id, user_id)
    if item is None:
        raise _not_found(item_id)
    change = item.change_status(target, at)  # raises InvalidStatusTransitionError
    if change is not None:
        reading.save_status(item, change)
    return item


def list_reading_list(
    reading: ReadingListRepository,
    user_id: int,
    *,
    status: ReadingStatus | None = None,
    after_id: int | None = None,
    limit: int = 20,
) -> ReadingPage:
    if limit < 1:
        raise ValueError("limit must be positive")
    found = reading.list_for_user(user_id, status=status, after_id=after_id, limit=limit + 1)
    if len(found) <= limit:
        return ReadingPage(found, None)
    items = found[:limit]
    last_id = items[-1].id
    if last_id is None:  # pragma: no cover - stored records always have an id
        raise ValueError("stored item without an id")
    return ReadingPage(items, last_id)


def get_history(reading: ReadingListRepository, user_id: int, item_id: int) -> list[StatusChange]:
    _owned(reading, user_id, item_id)
    return reading.history(item_id)


def add_note(
    reading: ReadingListRepository, user_id: int, item_id: int, text: str, at: datetime
) -> Note:
    item = _owned(reading, user_id, item_id)
    return reading.add_note(item.add_note(text, at))


def list_notes(reading: ReadingListRepository, user_id: int, item_id: int) -> list[Note]:
    _owned(reading, user_id, item_id)
    return reading.list_notes(item_id)
