from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from pydantic import Field


class ConfigError(Exception):
    """A required setting is missing."""


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    crossref_mailto: str | None = None
    rate_limit_enabled: bool = True
    rate_limit_login_per_account: int = Field(default=5, ge=1)
    rate_limit_login_per_ip: int = Field(default=20, ge=1)
    rate_limit_login_window_seconds: int = Field(default=60, ge=1)
    rate_limit_register_per_ip: int = Field(default=5, ge=1)
    rate_limit_register_window_seconds: int = Field(default=600, ge=1)
    rate_limit_trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        url = env.get("DATABASE_URL", "").strip()
        if not url:
            raise ConfigError(
                "DATABASE_URL is not set (copy .env.example to .env and run "
                "`uv run --env-file .env scitracker ...`)"
            )
        return cls(url, env.get("CROSSREF_MAILTO", "").strip() or None)
