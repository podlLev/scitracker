from sqlalchemy.orm import Session

from scitracker.storage.repositories import (
    SqlPublicationRepository,
    SqlReadingListRepository,
    SqlTopicRepository,
    SqlUserRepository,
)


class SqlUnitOfWork:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._publications = SqlPublicationRepository(session)
        self._topics = SqlTopicRepository(session)
        self._users = SqlUserRepository(session)
        self._reading = SqlReadingListRepository(session)

    @property
    def reading(self) -> SqlReadingListRepository:
        return self._reading

    @property
    def publications(self) -> SqlPublicationRepository:
        return self._publications

    @property
    def topics(self) -> SqlTopicRepository:
        return self._topics

    @property
    def users(self) -> SqlUserRepository:
        return self._users

    def commit(self) -> None:  # pragma: no cover - tests use a flush-only subclass
        self._session.commit()
