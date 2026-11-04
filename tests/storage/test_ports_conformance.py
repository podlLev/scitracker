from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from scitracker.storage.repositories import SqlPublicationRepository

if TYPE_CHECKING:
    from scitracker.services.ports import PublicationRepository


def test_repository_satisfies_port(session: Session) -> None:
    repo: PublicationRepository = SqlPublicationRepository(session)
    assert repo.count() >= 0
