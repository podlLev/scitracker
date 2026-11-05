import base64

from scitracker.api.problems import ApiProblem

MAX_ID = 2_147_483_647  # the database uses 32-bit integer ids
_PREFIX = "v1:"


def encode_cursor(after_id: int) -> str:
    """Opaque token. The version prefix lets the format change without breaking clients."""
    return base64.urlsafe_b64encode(f"{_PREFIX}{after_id}".encode()).decode().rstrip("=")


def decode_cursor(token: str) -> int:
    try:
        raw = base64.urlsafe_b64decode((token + "=" * (-len(token) % 4)).encode("ascii"))
        text = raw.decode("ascii")
        digits = text.removeprefix(_PREFIX)
        if not text.startswith(_PREFIX) or not digits.isdigit():
            raise ValueError(text)
        value = int(digits)
        if not 1 <= value <= MAX_ID:
            raise ValueError(text)
    except ValueError as exc:  # includes bad base64 and non-ASCII input
        raise ApiProblem(
            422,
            "invalid-cursor",
            "Invalid pagination cursor",
            "The cursor is malformed. Use the value of `next_cursor` from a previous response.",
        ) from exc
    return value
