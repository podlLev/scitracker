import pytest

from scitracker.api.caching import CacheSettings


def test_defaults() -> None:
    settings = CacheSettings.from_env({})
    assert (settings.enabled, settings.ttl_seconds, settings.max_entries) == (True, 60, 1000)


def test_overrides() -> None:
    settings = CacheSettings.from_env(
        {"CACHE_ENABLED": "off", "CACHE_TTL_SECONDS": "30", "CACHE_MAX_ENTRIES": "50"}
    )
    assert (settings.enabled, settings.ttl_seconds, settings.max_entries) == (False, 30, 50)


@pytest.mark.parametrize(
    ("env", "match"),
    [
        ({"CACHE_TTL_SECONDS": "0"}, "CACHE_TTL_SECONDS must be >= 1"),
        ({"CACHE_TTL_SECONDS": "abc"}, "CACHE_TTL_SECONDS must be an integer"),
        ({"CACHE_MAX_ENTRIES": "-1"}, "CACHE_MAX_ENTRIES must be >= 1"),
    ],
)
def test_invalid_values_rejected(env: dict[str, str], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        CacheSettings.from_env(env)
