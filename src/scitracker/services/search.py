from dataclasses import dataclass

from scitracker.domain.publication import Publication
from scitracker.services.ports import PublicationReader, SearchCriteria


@dataclass(frozen=True, slots=True)
class Page:
    items: list[Publication]
    next_after_id: int | None


def search_publications(
    reader: PublicationReader,
    criteria: SearchCriteria,
    *,
    after_id: int | None = None,
    limit: int = 20,
) -> Page:
    """One page of results. Asks for limit + 1 rows to learn whether another page exists."""
    if limit < 1:
        raise ValueError("limit must be positive")
    found = reader.search(criteria, after_id=after_id, limit=limit + 1)
    if len(found) <= limit:
        return Page(found, None)
    items = found[:limit]
    last_id = items[-1].id
    if last_id is None:  # pragma: no cover - stored records always have an id
        raise ValueError("stored publication without an id")
    return Page(items, last_id)
