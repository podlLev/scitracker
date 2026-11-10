import pytest

from scitracker.observability.redact import REDACTED, redact_text, redact_value

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("Authorization: Bearer abcdefgh12345", "abcdefgh12345"),
        (f"token was {JWT}", JWT),
        ("connect postgresql+psycopg://user:hunter2@127.0.0.1:5433/db", "hunter2"),
        ("login failed password=hunter2&next=/", "hunter2"),
        ('{"password": "hunter2", "email": "a@b.c"}', "hunter2"),
        ("{'access_token': 'abcdefgh12345'}", "abcdefgh12345"),
        ("JWT_SECRET=very-secret-value", "very-secret-value"),
    ],
)
def test_secrets_are_scrubbed(text: str, secret: str) -> None:
    cleaned = redact_text(text)
    assert secret not in cleaned
    assert REDACTED in cleaned


@pytest.mark.parametrize(
    "text",
    [
        "GET /api/v1/me 200",
        "token_type=bearer user=ann@example.com",
        "the bearer of news",
        "10.5555/abc",
    ],
)
def test_ordinary_text_is_left_alone(text: str) -> None:
    assert redact_text(text) == text


def test_sensitive_field_names_are_hidden_entirely() -> None:
    assert redact_value("password", "x") == REDACTED
    assert redact_value("Authorization", "Bearer abcdefgh12345") == REDACTED
    assert redact_value("status", 200) == 200
    assert redact_value("path", "/me") == "/me"


def test_surrounding_context_survives() -> None:
    assert redact_text("db at postgresql://u:p4ss@host/db failed") == (
        f"db at postgresql://u:{REDACTED}@host/db failed"
    )
