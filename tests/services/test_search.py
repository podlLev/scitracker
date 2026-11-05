import pytest

from scitracker.domain.publication import Publication
from scitracker.services.ports import SearchCriteria
from scitracker.services.search import search_publications


def pub(number: int) -> Publication:
    return Publication(title=f"P{number}", authors=[], doi=f"10.1000/{number}", id=number)


class FakeReader:
    def __init__(self, count: int) -> None:
        self._ids = list(range(count, 0, -1))  # newest first, like the database
        self.requested_limits: list[int] = []

    def get(self, publication_id: int) -> Publication | None:
        return pub(publication_id) if publication_id in self._ids else None

    def search(
        self, criteria: SearchCriteria, *, after_id: int | None, limit: int
    ) -> list[Publication]:
        self.requested_limits.append(limit)
        pool = [i for i in self._ids if after_id is None or i < after_id]
        return [pub(i) for i in pool[:limit]]


def test_full_page_points_to_the_next_one() -> None:
    reader = FakeReader(25)
    page = search_publications(reader, SearchCriteria(), limit=10)
    assert [p.id for p in page.items] == list(range(25, 15, -1))
    assert page.next_after_id == 16
    assert reader.requested_limits == [11]  # one extra row reveals the next page


def test_last_page_has_no_cursor() -> None:
    page = search_publications(FakeReader(25), SearchCriteria(), after_id=6, limit=10)
    assert len(page.items) == 5
    assert page.next_after_id is None


def test_exactly_full_last_page_has_no_cursor() -> None:
    page = search_publications(FakeReader(10), SearchCriteria(), limit=10)
    assert len(page.items) == 10
    assert page.next_after_id is None


def test_limit_must_be_positive() -> None:
    with pytest.raises(ValueError, match="limit"):
        search_publications(FakeReader(1), SearchCriteria(), limit=0)
