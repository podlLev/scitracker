from datetime import UTC, datetime

from scitracker.api.app import _utc_now


def test_utc_now_returns_current_utc_datetime() -> None:
    before = datetime.now(UTC)

    result = _utc_now()

    after = datetime.now(UTC)

    assert isinstance(result, datetime)
    assert result.tzinfo is UTC
    assert before <= result <= after
