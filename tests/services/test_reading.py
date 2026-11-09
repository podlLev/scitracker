from datetime import UTC, datetime, timedelta

import pytest

from scitracker.domain.errors import InvalidStatusTransitionError, RecordNotFoundError
from scitracker.domain.status import ReadingStatus
from scitracker.services.reading import (
    add_note,
    add_to_reading_list,
    change_status,
    get_history,
    list_notes,
    list_reading_list,
)
from tests.services.fakes import InMemoryReadingListRepository, StubPublicationReader

S = ReadingStatus
T0 = datetime(2026, 11, 1, 12, tzinfo=UTC)
T1 = T0 + timedelta(days=1)
T2 = T0 + timedelta(days=2)
ALICE, BOB = 1, 2


def setup() -> tuple[InMemoryReadingListRepository, StubPublicationReader]:
    return InMemoryReadingListRepository(), StubPublicationReader(10, 11, 12)


def test_adding_creates_then_returns_the_same_item() -> None:
    repo, pubs = setup()
    first = add_to_reading_list(repo, pubs, ALICE, 10, T0)
    second = add_to_reading_list(repo, pubs, ALICE, 10, T1)
    assert (first.created, second.created) == (True, False)
    assert first.item.id == second.item.id
    assert second.item.added_at == T0  # the original date is kept
    assert len(repo.items) == 1


def test_two_users_may_add_the_same_publication() -> None:
    repo, pubs = setup()
    add_to_reading_list(repo, pubs, ALICE, 10, T0)
    assert add_to_reading_list(repo, pubs, BOB, 10, T0).created is True


def test_adding_an_unknown_publication_is_not_found() -> None:
    repo, pubs = setup()
    with pytest.raises(RecordNotFoundError):
        add_to_reading_list(repo, pubs, ALICE, 999, T0)


def test_status_goes_forward_and_the_row_is_locked_first() -> None:
    repo, pubs = setup()
    item = add_to_reading_list(repo, pubs, ALICE, 10, T0).item
    assert item.id is not None
    change_status(repo, ALICE, item.id, S.READING, T1)
    done = change_status(repo, ALICE, item.id, S.DONE, T2)
    assert done.finished_at == T2
    assert repo.locked == [item.id, item.id]
    assert [(c.from_status, c.to_status) for c in get_history(repo, ALICE, item.id)] == [
        (S.TO_READ, S.READING),
        (S.READING, S.DONE),
    ]


def test_skipping_a_status_is_rejected_and_nothing_is_written() -> None:
    repo, pubs = setup()
    item = add_to_reading_list(repo, pubs, ALICE, 10, T0).item
    assert item.id is not None
    with pytest.raises(InvalidStatusTransitionError, match="reading"):
        change_status(repo, ALICE, item.id, S.DONE, T1)
    assert repo.items[item.id].status is S.TO_READ
    assert repo.history(item.id) == []


def test_repeating_done_keeps_the_date_and_adds_no_history() -> None:
    repo, pubs = setup()
    item = add_to_reading_list(repo, pubs, ALICE, 10, T0).item
    assert item.id is not None
    change_status(repo, ALICE, item.id, S.READING, T1)
    change_status(repo, ALICE, item.id, S.DONE, T1)
    again = change_status(repo, ALICE, item.id, S.DONE, T2)
    assert again.finished_at == T1
    assert len(repo.history(item.id)) == 2


def test_foreign_and_missing_items_are_indistinguishable() -> None:
    repo, pubs = setup()
    item = add_to_reading_list(repo, pubs, ALICE, 10, T0).item
    assert item.id is not None
    with pytest.raises(RecordNotFoundError) as foreign:
        change_status(repo, BOB, item.id, S.READING, T1)
    with pytest.raises(RecordNotFoundError) as missing:
        change_status(repo, BOB, 999, S.READING, T1)
    assert str(foreign.value).replace(str(item.id), "N") == str(missing.value).replace("999", "N")


def test_notes_are_private_to_the_owner() -> None:
    repo, pubs = setup()
    item = add_to_reading_list(repo, pubs, ALICE, 10, T0).item
    assert item.id is not None
    note = add_note(repo, ALICE, item.id, "  important  ", T1)
    assert note.text == "important"
    assert [n.text for n in list_notes(repo, ALICE, item.id)] == ["important"]
    with pytest.raises(RecordNotFoundError):
        list_notes(repo, BOB, item.id)
    with pytest.raises(RecordNotFoundError):
        add_note(repo, BOB, item.id, "intruder", T1)


def test_listing_filters_by_status_and_paginates() -> None:
    repo, pubs = setup()
    ids = [add_to_reading_list(repo, pubs, ALICE, p, T0).item.id for p in (10, 11, 12)]
    assert all(i is not None for i in ids)
    change_status(repo, ALICE, ids[0] or 0, S.READING, T1)
    first = list_reading_list(repo, ALICE, limit=2)
    assert [i.id for i in first.items] == [ids[2], ids[1]]
    assert first.next_after_id == ids[1]
    rest = list_reading_list(repo, ALICE, after_id=first.next_after_id, limit=2)
    assert [i.id for i in rest.items] == [ids[0]]
    assert rest.next_after_id is None
    reading = list_reading_list(repo, ALICE, status=S.READING)
    assert [i.id for i in reading.items] == [ids[0]]


def test_listing_requires_a_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        list_reading_list(InMemoryReadingListRepository(), ALICE, limit=0)
