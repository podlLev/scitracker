from fastapi import APIRouter, FastAPI

from scitracker import __version__
from scitracker.api import health, publications, topics
from scitracker.api.deps import Ping, ReadScope
from scitracker.api.problems import register_problem_handlers


def create_app(*, read_scope: ReadScope, ping: Ping) -> FastAPI:
    """Build the application. Everything infrastructural is injected by the caller."""
    app = FastAPI(
        title="scitracker",
        version=__version__,
        description="Tracker of scientific publications (arXiv + Crossref).",
    )
    app.state.read_scope = read_scope
    app.state.ping = ping
    register_problem_handlers(app)
    app.include_router(health.router)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(publications.router)
    api_v1.include_router(topics.router)
    app.include_router(api_v1)
    return app
