import html
import logging
import re
from datetime import date
from typing import Any

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.publication import Author, Publication
from scitracker.services.errors import SourceError
from scitracker.services.ports import SourceResult
from scitracker.sources.http import HttpFetcher, ensure_limit

logger = logging.getLogger(__name__)

CROSSREF_URL = "https://api.crossref.org/works"
CROSSREF_MIN_INTERVAL = 0.2
SELECT_FIELDS = "DOI,title,author,abstract,issued,URL"
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: object) -> str | None:
    """Strip JATS/HTML tags and entities, collapse whitespace."""
    if not isinstance(value, str):
        return None
    return " ".join(html.unescape(_TAG_RE.sub(" ", value)).split()) or None


def _authors(raw: object) -> list[Author]:
    authors: list[Author] = []
    for entry in raw if isinstance(raw, list) else []:
        parts = (entry.get("given"), entry.get("family"))
        name = entry.get("name") or " ".join(p for p in parts if p)
        if name:
            authors.append(Author(name))
    return authors


def _issued(raw: Any) -> date | None:
    try:
        parts = raw["date-parts"][0]
        return date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _parse_item(item: object) -> Publication:
    if not isinstance(item, dict):
        raise InvalidValueError("record is not an object")
    titles = item.get("title")
    title = _clean(titles[0]) if isinstance(titles, list) and titles else None
    if title is None:
        raise InvalidValueError("missing title")
    return Publication(
        title=title,
        authors=_authors(item.get("author")),
        doi=item["DOI"],
        abstract=_clean(item.get("abstract")),
        published_on=_issued(item.get("issued")),
        url=item.get("URL"),
    )


def parse_works(payload: object) -> SourceResult:
    try:
        items = payload["message"]["items"]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise SourceError("crossref", "unexpected response structure") from exc
    if not isinstance(items, list):
        raise SourceError("crossref", "unexpected response structure")
    publications: list[Publication] = []
    rejected = 0
    for item in items:
        try:
            publications.append(_parse_item(item))
        except (InvalidValueError, KeyError, TypeError, ValueError, AttributeError):
            rejected += 1  # malformed record at the system boundary: skip and count
            logger.warning("crossref: rejected a malformed record", exc_info=True)
    return SourceResult(publications, rejected)


class CrossrefSource:
    name = "crossref"

    def __init__(self, fetcher: HttpFetcher, *, mailto: str | None = None) -> None:
        self._fetcher = fetcher
        self._mailto = mailto

    async def search(self, query: str, *, limit: int = 50) -> SourceResult:
        params: dict[str, str | int] = {
            "query": query,
            "rows": ensure_limit(limit),
            "select": SELECT_FIELDS,
        }
        if self._mailto:
            params["mailto"] = self._mailto  # "polite pool": more stable rate limits
        response = await self._fetcher.get(CROSSREF_URL, params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceError("crossref", "response is not valid JSON") from exc
        return parse_works(payload)
