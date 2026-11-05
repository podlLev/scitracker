from typing import Annotated, Self

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field

from scitracker.api.deps import PROTECTED, CurrentUser, Repositories
from scitracker.api.pagination import MAX_ID
from scitracker.api.problems import ProblemDetails
from scitracker.domain.topic import Topic
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


@router.get("", response_model=list[TopicOut], summary="List public topics")
def list_topics(repositories: Repositories) -> list[TopicOut]:
    return [TopicOut.from_domain(topic) for topic in repositories.topics.list_public()]


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
def post_topic(body: TopicIn, user: CurrentUser, repositories: Repositories) -> TopicOut:
    topic = create_topic(
        repositories.topics, user, name=body.name, query=body.query, public=body.public
    )
    repositories.commit()
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
) -> None:
    delete_topic(repositories.topics, user, topic_id)
    repositories.commit()
