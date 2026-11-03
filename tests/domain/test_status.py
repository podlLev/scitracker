import pytest

from scitracker.domain.errors import InvalidStatusTransitionError
from scitracker.domain.status import ReadingStatus, check_transition

S = ReadingStatus


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.TO_READ, S.READING),
        (S.READING, S.DONE),
        (S.READING, S.TO_READ),
        (S.DONE, S.READING),
        (S.TO_READ, S.TO_READ),
        (S.DONE, S.DONE),
    ],
)
def test_allowed_transitions(current: ReadingStatus, target: ReadingStatus) -> None:
    check_transition(current, target)


def test_skipping_forward_is_rejected_with_explanation() -> None:
    with pytest.raises(InvalidStatusTransitionError, match="skipped"):
        check_transition(S.TO_READ, S.DONE)


def test_going_back_two_steps_is_rejected_with_explanation() -> None:
    with pytest.raises(InvalidStatusTransitionError, match="one step"):
        check_transition(S.DONE, S.TO_READ)
