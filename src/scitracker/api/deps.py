from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from scitracker.services.ports import PublicationReader, TopicRepository


@dataclass(frozen=True, slots=True)
class ReadRepositories:
    publications: PublicationReader
    topics: TopicRepository


ReadScope = Callable[[], AbstractContextManager[ReadRepositories]]
Ping = Callable[[], None]


def get_repositories(request: Request) -> Iterator[ReadRepositories]:
    """One scope (one database session) per request, closed when the response is done."""
    scope: ReadScope = request.app.state.read_scope
    with scope() as repositories:
        yield repositories


Repositories = Annotated[ReadRepositories, Depends(get_repositories)]
