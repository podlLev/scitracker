import base64

import pytest

from scitracker.api.pagination import MAX_ID, decode_cursor, encode_cursor
from scitracker.api.problems import ApiProblem


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


@pytest.mark.parametrize("value", [1, 42, 123_456, MAX_ID])
def test_cursor_roundtrip(value: int) -> None:
    assert decode_cursor(encode_cursor(value)) == value


@pytest.mark.parametrize(
    "token",
    [
        "",
        "!!!",
        "ы",
        b64("v2:5"),
        b64("v1:abc"),
        b64("v1:0"),
        b64("v1:-3"),
        b64(f"v1:{MAX_ID + 1}"),
    ],
)
def test_malformed_cursors_are_rejected(token: str) -> None:
    with pytest.raises(ApiProblem) as info:
        decode_cursor(token)
    assert info.value.slug == "invalid-cursor"
