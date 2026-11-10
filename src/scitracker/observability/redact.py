import re

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
)

_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "Bearer <token>": must be a proper token value
    (re.compile(r"(?i)\b(bearer)\s+(?![a-z_]+=)[A-Za-z0-9._~+/=-]{8,}(?!\S*@)"), rf"\1 {REDACTED}"),
    # a JWT anywhere in the text
    (re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"), REDACTED),
    # credentials inside URLs: scheme://user:password@host
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^\s:/@]+):[^\s@/]+@"), rf"\1:{REDACTED}@"),
    # key=value, key: value, "key": "value"
    (
        re.compile(
            r"""(?i)(["']?(?:password|passwd|secret|token|api[_-]?key|authorization)["']?\s*[:=]\s*)"""
            r"""("[^"]*"|'[^']*'|[^\s,;&}]+)"""
        ),
        rf"\1{REDACTED}",
    ),
)


def redact_text(text: str) -> str:
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text


def redact_value(key: str, value: object) -> object:
    """A field whose name looks sensitive is hidden completely, other strings are scrubbed."""
    lowered = key.lower()
    if any(part in lowered for part in SENSITIVE_KEYS):
        return REDACTED
    return redact_text(value) if isinstance(value, str) else value
