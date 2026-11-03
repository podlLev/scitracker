from datetime import UTC, datetime, timedelta

import pytest

from scitracker.domain.errors import InvalidStatusTransitionError, InvalidValueError
from scitracker.domain.reading import ReadingItem
from scitracker.domain.status import ReadingStatus

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(days=1)
T2 = T0 + timedelta(days=2)


def make_item() -> ReadingItem:
    return ReadingItem(user_id=1, publication_id=10, added_at=T0, id=5)


def test_new_item_starts_as_to_read() -> None:
    item = make_item()
    assert item.status is ReadingStatus.TO_READ
    assert item.finished_at is None


def test_full_path_records_finish_date_and_history() -> None:
    item = make_item()
    first = item.change_status(ReadingStatus.READING, T1)
    second = item.change_status(ReadingStatus.DONE, T2)
    assert first is not None
    assert second is not None
    assert (second.from_status, second.to_status) == (ReadingStatus.READING, ReadingStatus.DONE)
    assert item.finished_at == T2


def test_skip_to_done_is_rejected_and_state_is_unchanged() -> None:
    item = make_item()
    with pytest.raises(InvalidStatusTransitionError):
        item.change_status(ReadingStatus.DONE, T1)
    assert item.status is ReadingStatus.TO_READ
    assert item.finished_at is None


def test_repeating_done_does_not_change_date_or_create_history() -> None:
    item = make_item()
    item.change_status(ReadingStatus.READING, T1)
    item.change_status(ReadingStatus.DONE, T1)
    repeat = item.change_status(ReadingStatus.DONE, T2)
    assert repeat is None
    assert item.finished_at == T1


def test_going_back_from_done_clears_finish_date() -> None:
    item = make_item()
    item.change_status(ReadingStatus.READING, T1)
    item.change_status(ReadingStatus.DONE, T1)
    item.change_status(ReadingStatus.READING, T2)
    assert item.finished_at is None


def test_naive_datetime_is_rejected() -> None:
    item = make_item()
    with pytest.raises(InvalidValueError):
        item.change_status(ReadingStatus.READING, datetime(2026, 11, 1, 12, 0))


def test_inconsistent_finished_at_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        ReadingItem(1, 10, T0, status=ReadingStatus.DONE, finished_at=None)


def test_add_note() -> None:
    note = make_item().add_note("  important  ", T1)
    assert note.text == "important"
    assert note.reading_item_id == 5
    assert note.created_at == T1


def test_blank_note_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        make_item().add_note("   ", T1)
