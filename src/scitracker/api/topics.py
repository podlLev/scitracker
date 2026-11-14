from typing import Annotated, Self

from fastapi import APIRouter, Path, Response
from pydantic import BaseModel, Field

from scitracker.api.caching import CacheDep, mark_cache
from scitracker.api.deps import PROTECTED, CurrentUser, Repositories
from scitracker.api.pagination import MAX_ID
from scitracker.api.problems import ProblemDetails
from scitracker.domain.topic import Topic
from scitracker.services.cache import Cache, make_key
from scitracker.services.topics import create_topic, delete_topic

router = APIRouter(prefix="/topics", tags=["topics"])


class TopicOut(BaseModel):
    id: int
    name: str
    query: str
    public: bool

    @classmethod
    def from_domain(cls, topic: Topic) -> Self:
        if topic.id is None:  # pragma: no cover - stored topics always have an id
            raise ValueError("only stored topics can be returned by the API")
        return cls(id=topic.id, name=topic.name, query=topic.query, public=topic.owner_id is None)


class TopicIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=500)
    public: bool = Field(default=False, description="Public topics require an administrator")


def _invalidate(cache: Cache) -> None:
    """Topics changed: visible topics in listings and stats may differ now."""
    cache.invalidate("topics")
    cache.invalidate("stats")


@router.get("", response_model=list[TopicOut], summary="List public topics")
def list_topics(response: Response, repositories: Repositories, cache: CacheDep) -> list[TopicOut]:
    cached = cache.get_or_compute(
        make_key("topics:public", user_id=None),
        lambda: tuple(repositories.topics.list_public()),
    )
    mark_cache(response, cached)
    return [TopicOut.from_domain(topic) for topic in cached.value]


@router.post(
    "",
    status_code=201,
    response_model=TopicOut,
    summary="Create a topic",
    responses={
        **PROTECTED,
        403: {"model": ProblemDetails},
        409: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
def post_topic(
    body: TopicIn, user: CurrentUser, repositories: Repositories, cache: CacheDep
) -> TopicOut:
    topic = create_topic(
        repositories.topics, user, name=body.name, query=body.query, public=body.public
    )
    repositories.commit()
    _invalidate(cache)  # after the commit, otherwise a concurrent request caches the old state
    return TopicOut.from_domain(topic)


@router.delete(
    "/{topic_id}",
    status_code=204,
    summary="Delete a topic",
    responses={
        **PROTECTED,
        403: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
def remove_topic(
    topic_id: Annotated[int, Path(ge=1, le=MAX_ID)],
    user: CurrentUser,
    repositories: Repositories,
    cache: CacheDep,
) -> None:
    delete_topic(repositories.topics, user, topic_id)
    repositories.commit()
    _invalidate(cache)
