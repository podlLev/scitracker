from dataclasses import dataclass
from datetime import datetime

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.status import ReadingStatus, check_transition
from scitracker.domain.validation import require_aware, require_text


@dataclass(frozen=True, slots=True)
class StatusChange:
    """One entry of the status history."""

    from_status: ReadingStatus
    to_status: ReadingStatus
    changed_at: datetime


@dataclass(slots=True)
class Note:
    reading_item_id: int | None
    text: str
    created_at: datetime
    id: int | None = None

    def __post_init__(self) -> None:
        self.text = require_text(self.text, "note text", max_length=10_000)
        require_aware(self.created_at, "created_at")


@dataclass(slots=True)
class ReadingItem:
    user_id: int
    publication_id: int
    added_at: datetime
    status: ReadingStatus = ReadingStatus.TO_READ
    finished_at: datetime | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        require_aware(self.added_at, "added_at")
        if (self.status is ReadingStatus.DONE) != (self.finished_at is not None):
            raise InvalidValueError("finished_at must be set if and only if status is 'done'")

    def change_status(self, target: ReadingStatus, at: datetime) -> StatusChange | None:
        """Move to the target status.

        Returns the history entry, or None if the status is already the target
        (repeating a request changes nothing, including finished_at).
        """
        require_aware(at, "at")
        if target is self.status:
            return None
        check_transition(self.status, target)
        change = StatusChange(self.status, target, at)
        self.status = target
        self.finished_at = at if target is ReadingStatus.DONE else None
        return change

    def add_note(self, text: str, at: datetime) -> Note:
        return Note(reading_item_id=self.id, text=text, created_at=at)
