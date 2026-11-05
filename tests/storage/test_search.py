from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from scitracker.domain.publication import Author, Publication
from scitracker.services.ports import SearchCriteria
from scitracker.storage.repositories import SqlPublicationRepository


def test_search_loads_authors_in_a_constant_number_of_queries(session: Session) -> None:
    repo = SqlPublicationRepository(session)
    for n in range(8):
        repo.add(
            Publication(
                title=f"P{n}", authors=[Author(f"A{n}"), Author("Common")], doi=f"10.1000/q{n}"
            )
        )
    session.expunge_all()  # force real loading instead of the identity map
    statements: list[str] = []

    def record(  # noqa: PLR0917
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        statements.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        found = repo.search(SearchCriteria(), after_id=None, limit=8)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(found) == 8
    assert all(len(p.authors) == 2 for p in found)
    assert len(statements) <= 3  # publications + links + authors, regardless of the page size
