"""HTTP-side caching helpers: settings, dependency, X-Cache header (ADR-012)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Response

from scitracker.cache.memory import NullCache
from scitracker.services.cache import Cache, CacheResult

_FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True, slots=True)
class CacheSettings:
    enabled: bool = True
    ttl_seconds: int = 60
    max_entries: int = 1000

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> CacheSettings:
        def number(name: str, default: int) -> int:
            raw = env.get(name, str(default))
            try:
                value = int(raw)
            except ValueError as error:
                raise ValueError(f"{name} must be an integer, got {raw!r}") from error
            if value < 1:
                raise ValueError(f"{name} must be >= 1")
            return value

        enabled = env.get("CACHE_ENABLED", "true").strip().lower() not in _FALSE_VALUES
        return cls(
            enabled=enabled,
            ttl_seconds=number("CACHE_TTL_SECONDS", 60),
            max_entries=number("CACHE_MAX_ENTRIES", 1000),
        )


def get_cache(request: Request) -> Cache:
    cache: Cache | None = getattr(request.app.state, "cache", None)
    return cache if cache is not None else NullCache()


CacheDep = Annotated[Cache, Depends(get_cache)]


def mark_cache(response: Response, result: CacheResult[object]) -> None:
    response.headers["X-Cache"] = "HIT" if result.hit else "MISS"
