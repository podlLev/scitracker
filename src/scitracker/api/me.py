from fastapi import APIRouter

from scitracker.api.auth import UserOut
from scitracker.api.deps import PROTECTED, CurrentUser, Repositories
from scitracker.api.topics import TopicOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut, summary="Current user", responses=PROTECTED)
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_domain(user)


@router.get(
    "/topics", response_model=list[TopicOut], summary="My private topics", responses=PROTECTED
)
def my_topics(user: CurrentUser, repositories: Repositories) -> list[TopicOut]:
    if user.id is None:  # pragma: no cover - authenticated users are always stored
        raise ValueError("user is not stored")
    return [TopicOut.from_domain(topic) for topic in repositories.topics.list_owned(user.id)]
