import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from scitracker.api.deps import Ping
from scitracker.api.problems import ApiProblem, ProblemDetails

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: str


@router.get(
    "/healthz",
    response_model=HealthOut,
    summary="Liveness and database check",
    responses={503: {"model": ProblemDetails}},
)
def healthz(request: Request) -> HealthOut:
    ping: Ping = request.app.state.ping
    try:
        ping()
    except Exception as exc:
        logger.warning("health check failed", exc_info=True)
        raise ApiProblem(
            503, "service-unavailable", "Service Unavailable", "The database is not reachable."
        ) from exc
    return HealthOut(status="ok")
