from fastapi import APIRouter, FastAPI

from scitracker import __version__
from scitracker.api import auth, health, me, publications, topics
from scitracker.api.deps import Ping, Scope
from scitracker.api.problems import register_problem_handlers
from scitracker.services.ports import PasswordHasher, TokenService


def create_app(
    *, scope: Scope, ping: Ping, hasher: PasswordHasher, tokens: TokenService
) -> FastAPI:
    """Build the application. Everything infrastructural is injected by the caller."""
    app = FastAPI(
        title="scitracker",
        version=__version__,
        description="Tracker of scientific publications (arXiv + Crossref).",
    )
    app.state.scope = scope
    app.state.ping = ping
    app.state.hasher = hasher
    app.state.tokens = tokens
    register_problem_handlers(app)
    app.include_router(health.router)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(auth.router)
    api_v1.include_router(me.router)
    api_v1.include_router(publications.router)
    api_v1.include_router(topics.router)
    app.include_router(api_v1)
    return app
