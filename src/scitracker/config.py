from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self


class ConfigError(Exception):
    """A required setting is missing."""


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    crossref_mailto: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        url = env.get("DATABASE_URL", "").strip()
        if not url:
            raise ConfigError(
                "DATABASE_URL is not set (copy .env.example to .env and run "
                "`uv run --env-file .env scitracker ...`)"
            )
        return cls(url, env.get("CROSSREF_MAILTO", "").strip() or None)
