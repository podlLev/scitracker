from datetime import UTC, datetime

import pytest

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.validation import require_aware, require_text


def test_require_text_strips_value() -> None:
    assert require_text("  abc  ", "field", max_length=10) == "abc"


def test_require_text_rejects_empty() -> None:
    with pytest.raises(InvalidValueError, match="must not be empty"):
        require_text("   ", "field", max_length=10)


def test_require_text_rejects_too_long() -> None:
    with pytest.raises(InvalidValueError, match="at most 5"):
        require_text("abcdef", "field", max_length=5)


def test_require_aware_accepts_aware_datetime() -> None:
    value = datetime(2026, 11, 1, tzinfo=UTC)
    assert require_aware(value, "field") == value


def test_require_aware_rejects_naive_datetime() -> None:
    with pytest.raises(InvalidValueError, match="timezone-aware"):
        require_aware(datetime(2026, 11, 1), "field")
