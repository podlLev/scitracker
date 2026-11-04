import re

from scitracker.domain.errors import InvalidValueError

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

_ARXIV_PREFIXES = ("https://arxiv.org/abs/", "http://arxiv.org/abs/", "arxiv:")
_ARXIV_VERSION_RE = re.compile(r"v\d+$")
_ARXIV_NEW_RE = re.compile(r"^\d{4}\.\d{4,5}$")
_ARXIV_OLD_RE = re.compile(r"^[a-z-]+(\.[a-z]{2})?/\d{7}$")
_ARXIV_DOI_PREFIX = "10.48550/arxiv."


def _strip_prefix(value: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if value.startswith(prefix):
            return value.removeprefix(prefix)
    return value


def normalize_doi(raw: str) -> str:
    """Lowercase the DOI and strip URL or 'doi:' prefixes (DOIs are case-insensitive)."""
    value = _strip_prefix(raw.strip().lower(), _DOI_PREFIXES)
    if not _DOI_RE.match(value):
        raise InvalidValueError(f"invalid DOI: {raw!r}")
    return value


def normalize_arxiv_id(raw: str) -> str:
    """Strip prefixes and the version suffix, so v1 and v2 of a paper are the same work."""
    value = _strip_prefix(raw.strip().lower(), _ARXIV_PREFIXES)
    value = _ARXIV_VERSION_RE.sub("", value)
    if not (_ARXIV_NEW_RE.match(value) or _ARXIV_OLD_RE.match(value)):
        raise InvalidValueError(f"invalid arXiv ID: {raw!r}")
    return value


def arxiv_id_from_doi(doi: str) -> str | None:
    """Return the arXiv ID embedded in an arXiv-issued DOI (10.48550/arXiv.<id>), else None."""
    value = doi.lower()
    if not value.startswith(_ARXIV_DOI_PREFIX):
        return None
    try:
        return normalize_arxiv_id(value.removeprefix(_ARXIV_DOI_PREFIX))
    except InvalidValueError:
        return None
