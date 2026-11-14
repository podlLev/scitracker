import os
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI
from sqlalchemy import text

from scitracker.api.app import create_app
from scitracker.api.caching import CacheSettings
from scitracker.api.ratelimit import RateLimits, RateLimitSettings
from scitracker.cache.memory import InMemoryTtlCache, NullCache
from scitracker.observability.logs import LogSettings, configure_logging
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.security.rate_limiter import InMemorySlidingWindowLimiter
from scitracker.security.tokens import JwtTokenService
from scitracker.services.cache import Cache
from scitracker.services.ports import UnitOfWork
from scitracker.storage.database import create_db_engine, create_session_factory
from scitracker.storage.unit_of_work import SqlUnitOfWork


def build_cache(settings: CacheSettings) -> Cache:
    if not settings.enabled:
        return NullCache()
    return InMemoryTtlCache(ttl_seconds=settings.ttl_seconds, max_entries=settings.max_entries)


def build_rate_limits(settings: RateLimitSettings) -> RateLimits:
    return RateLimits(
        enabled=settings.enabled,
        trusted_proxy_hops=settings.trusted_proxy_hops,
        login_account=InMemorySlidingWindowLimiter(
            limit=settings.login_per_account, window_seconds=settings.login_window_seconds
        ),
        login_ip=InMemorySlidingWindowLimiter(
            limit=settings.login_per_ip, window_seconds=settings.login_window_seconds
        ),
        register_ip=InMemorySlidingWindowLimiter(
            limit=settings.register_per_ip, window_seconds=settings.register_window_seconds
        ),
    )


def build_app() -> FastAPI:
    log = LogSettings.from_env(os.environ)
    configure_logging(log.level, log.format)
    rate_limits = build_rate_limits(RateLimitSettings.from_env(os.environ))
    cache = build_cache(CacheSettings.from_env(os.environ))
    session_factory = create_session_factory(create_db_engine(os.environ["DATABASE_URL"]))

    @contextmanager
    def scope() -> Iterator[UnitOfWork]:
        with session_factory() as session:
            yield SqlUnitOfWork(session)

    def ping() -> None:
        with session_factory() as session:
            session.execute(text("SELECT 1"))

    return create_app(
        scope=scope,
        ping=ping,
        hasher=Argon2PasswordHasher(),
        tokens=JwtTokenService(os.environ["JWT_SECRET"]),
        rate_limits=rate_limits,
        cache=cache,
    )
