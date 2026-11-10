import pytest

from scitracker.config import ConfigError, Settings


def test_settings_are_read_and_trimmed() -> None:
    settings = Settings.from_env({"DATABASE_URL": " postgresql://x ", "CROSSREF_MAILTO": " a@b.c "})
    assert (settings.database_url, settings.crossref_mailto) == ("postgresql://x", "a@b.c")


def test_mailto_is_optional() -> None:
    assert Settings.from_env({"DATABASE_URL": "postgresql://x"}).crossref_mailto is None


@pytest.mark.parametrize("env", [{}, {"DATABASE_URL": "  "}])
def test_missing_database_url_is_a_clear_error(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        Settings.from_env(env)
