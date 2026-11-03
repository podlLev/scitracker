from datetime import datetime

from scitracker.domain.errors import InvalidValueError


def require_text(value: str, field: str, *, max_length: int) -> str:
    """Return the stripped text or raise if it is empty or too long."""
    cleaned = value.strip()
    if not cleaned:
        raise InvalidValueError(f"{field} must not be empty")
    if len(cleaned) > max_length:
        raise InvalidValueError(f"{field} must be at most {max_length} characters")
    return cleaned


def require_aware(value: datetime, field: str) -> datetime:
    """Reject naive datetimes: all timestamps in the system are timezone-aware."""
    if value.tzinfo is None:
        raise InvalidValueError(f"{field} must be timezone-aware")
    return value
