class DomainError(Exception):
    """Base class for all domain errors."""


class InvalidValueError(DomainError):
    """A value violates a domain invariant."""


class InvalidStatusTransitionError(DomainError):
    """Requested reading status change is not allowed."""

    def __init__(self, current: str, target: str, reason: str) -> None:
        super().__init__(f"Cannot change status from '{current}' to '{target}': {reason}")
        self.current = current
        self.target = target
        self.reason = reason


class DuplicateRecordError(DomainError):
    """A record violating a uniqueness rule already exists."""
