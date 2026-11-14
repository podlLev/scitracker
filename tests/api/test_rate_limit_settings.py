import pytest

from scitracker.api.ratelimit import RateLimitSettings


def test_defaults() -> None:
    settings = RateLimitSettings.from_env({})
    assert settings.enabled is True
    assert settings.login_per_account == 5
    assert settings.login_per_ip == 20
    assert settings.login_window_seconds == 60
    assert settings.register_per_ip == 5
    assert settings.register_window_seconds == 600
    assert settings.trusted_proxy_hops == 0


def test_overrides() -> None:
    settings = RateLimitSettings.from_env(
        {
            "RATE_LIMIT_ENABLED": "false",
            "RATE_LIMIT_LOGIN_PER_ACCOUNT": "3",
            "RATE_LIMIT_TRUSTED_PROXY_HOPS": "1",
        }
    )
    assert settings.enabled is False
    assert settings.login_per_account == 3
    assert settings.trusted_proxy_hops == 1


@pytest.mark.parametrize("value", ["0", "false", "FALSE", " no ", "off"])
def test_disabled_values(value: str) -> None:
    assert RateLimitSettings.from_env({"RATE_LIMIT_ENABLED": value}).enabled is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", ""])
def test_other_values_keep_enabled(value: str) -> None:
    assert RateLimitSettings.from_env({"RATE_LIMIT_ENABLED": value}).enabled is True


@pytest.mark.parametrize(
    ("env", "match"),
    [
        ({"RATE_LIMIT_LOGIN_PER_ACCOUNT": "0"}, "RATE_LIMIT_LOGIN_PER_ACCOUNT must be >= 1"),
        ({"RATE_LIMIT_LOGIN_PER_IP": "abc"}, "RATE_LIMIT_LOGIN_PER_IP must be an integer"),
        ({"RATE_LIMIT_LOGIN_WINDOW_SECONDS": "0"}, "RATE_LIMIT_LOGIN_WINDOW_SECONDS must be >= 1"),
        ({"RATE_LIMIT_REGISTER_PER_IP": "-3"}, "RATE_LIMIT_REGISTER_PER_IP must be >= 1"),
        (
            {"RATE_LIMIT_REGISTER_WINDOW_SECONDS": "0"},
            "RATE_LIMIT_REGISTER_WINDOW_SECONDS must be >= 1",
        ),
        ({"RATE_LIMIT_TRUSTED_PROXY_HOPS": "-1"}, "RATE_LIMIT_TRUSTED_PROXY_HOPS must be >= 0"),
    ],
)
def test_invalid_values_rejected(env: dict[str, str], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        RateLimitSettings.from_env(env)
