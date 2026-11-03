from enum import StrEnum

from scitracker.domain.errors import InvalidStatusTransitionError


class ReadingStatus(StrEnum):
    TO_READ = "to_read"
    READING = "reading"
    DONE = "done"


_ORDER = (ReadingStatus.TO_READ, ReadingStatus.READING, ReadingStatus.DONE)


def check_transition(current: ReadingStatus, target: ReadingStatus) -> None:
    """Raise if the move is not allowed.

    Allowed: one step forward, one step back, or staying in the same status (no-op).
    """
    step = _ORDER.index(target) - _ORDER.index(current)
    if abs(step) <= 1:
        return
    if step > 1:
        reason = "statuses cannot be skipped, move through 'reading' first"
    else:
        reason = "you can go back only one step"
    raise InvalidStatusTransitionError(str(current), str(target), reason)
