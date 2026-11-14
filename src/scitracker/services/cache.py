"""Cache port and key builder (ADR-012). Standard library only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class CacheResult[T]:
    value: T
    hit: bool


class Cache(Protocol):
    def get_or_compute[T](self, key: str, factory: Callable[[], T]) -> CacheResult[T]:
        """Return the cached value or compute, store and return it."""
        ...

    def invalidate(self, namespace: str) -> None:
        """Drop every entry whose key starts with ``namespace + ':'``."""
        ...

    def clear(self) -> None:
        """Drop all entries."""
        ...


def make_key(namespace: str, *, user_id: int | None, **params: object) -> str:
    """Build a cache key. ``user_id`` is mandatory so that results never leak across users."""
    payload = json.dumps(
        {"user": user_id, "params": params},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:24]
    return f"{namespace}:{digest}"
