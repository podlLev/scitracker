from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI

from scitracker import __version__
from scitracker.api import auth, feed, health, me, publications, reading_list, stats, topics
from scitracker.api.deps import Ping, Scope
from scitracker.api.middleware import RequestContextMiddleware
from scitracker.api.problems import register_problem_handlers
from scitracker.api.ratelimit import RateLimits, rate_limit_exceeded_handler
from scitracker.services.cache import Cache
from scitracker.services.ports import PasswordHasher, TokenService
from scitracker.services.ratelimit import RateLimitExceededError


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(  # noqa: PLR0913 - composition root: every dependency is injected by keyword
    *,
    scope: Scope,
    ping: Ping,
    hasher: PasswordHasher,
    tokens: TokenService,
    clock: Callable[[], datetime] = _utc_now,
    rate_limits: RateLimits | None = None,
    cache: Cache | None = None,
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
    app.state.clock = clock
    app.state.rate_limits = rate_limits
    app.state.cache = cache
    register_problem_handlers(app)
    app.include_router(health.router)
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(RateLimitExceededError, rate_limit_exceeded_handler)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(auth.router)
    api_v1.include_router(me.router)
    api_v1.include_router(publications.router)
    api_v1.include_router(topics.router)
    api_v1.include_router(reading_list.router)
    api_v1.include_router(feed.router)
    api_v1.include_router(stats.router)
    app.include_router(api_v1)
    return app
