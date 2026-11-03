from dataclasses import dataclass

from scitracker.domain.validation import require_text


@dataclass(slots=True)
class Topic:
    name: str
    query: str
    owner_id: int | None = None  # None: topic managed by an administrator
    id: int | None = None

    def __post_init__(self) -> None:
        self.name = require_text(self.name, "topic name", max_length=200)
        self.query = require_text(self.query, "topic query", max_length=500)
