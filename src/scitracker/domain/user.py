from dataclasses import dataclass
from enum import StrEnum

from scitracker.domain.errors import InvalidValueError


class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"


@dataclass(slots=True)
class User:
    email: str
    password_hash: str
    role: Role = Role.USER
    id: int | None = None

    def __post_init__(self) -> None:
        email = self.email.strip().lower()
        local, separator, domain = email.partition("@")
        if not (local and separator and "." in domain):
            raise InvalidValueError(f"invalid email: {self.email!r}")
        self.email = email
        if not self.password_hash:
            raise InvalidValueError("password hash must not be empty")
