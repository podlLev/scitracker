from fastapi import APIRouter
from pydantic import BaseModel

from scitracker.api.deps import Repositories

router = APIRouter(prefix="/topics", tags=["topics"])


class TopicOut(BaseModel):
    id: int
    name: str
    query: str


@router.get("", response_model=list[TopicOut], summary="List public topics")
def list_topics(repositories: Repositories) -> list[TopicOut]:
    # Topics owned by users are private and appear only after authentication (later PR).
    return [
        TopicOut(id=topic.id, name=topic.name, query=topic.query)
        for topic in repositories.topics.list_all()
        if topic.owner_id is None and topic.id is not None
    ]
