import logging
from datetime import date
from typing import TYPE_CHECKING

from defusedxml.ElementTree import ParseError, fromstring

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.identifiers import normalize_doi
from scitracker.domain.publication import Author, Publication
from scitracker.services.errors import SourceError
from scitracker.services.ports import SourceResult
from scitracker.sources.http import HttpFetcher, ensure_limit

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

logger = logging.getLogger(__name__)

ARXIV_URL = "https://export.arxiv.org/api/query"
ARXIV_MIN_INTERVAL = 3.0  # arXiv API terms: one request every three seconds
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def _text(element: "Element", tag: str) -> str:
    child = element.find(f"{ATOM}{tag}")
    value = " ".join((child.text or "").split()) if child is not None else ""
    if not value:
        raise InvalidValueError(f"missing <{tag}>")
    return value


def _doi(element: "Element") -> str | None:
    child = element.find(f"{ARXIV_NS}doi")
    if child is None or not child.text:
        return None
    try:
        return normalize_doi(child.text)
    except InvalidValueError:
        return None  # a bad DOI does not make the whole record unusable


def _url(element: "Element") -> str | None:
    for link in element.findall(f"{ATOM}link"):
        if link.get("rel") == "alternate":
            return link.get("href")
    return None


def _parse_entry(entry: "Element") -> Publication:
    names = [" ".join((n.text or "").split()) for n in entry.findall(f"{ATOM}author/{ATOM}name")]
    summary = entry.find(f"{ATOM}summary")
    return Publication(
        title=_text(entry, "title"),
        authors=[Author(name) for name in names if name],
        arxiv_id=_text(entry, "id"),
        doi=_doi(entry),
        abstract=" ".join((summary.text or "").split()) or None if summary is not None else None,
        published_on=date.fromisoformat(_text(entry, "published")[:10]),
        url=_url(entry),
    )


def parse_feed(xml_text: str) -> SourceResult:
    try:
        root = fromstring(xml_text)
    except ParseError as exc:
        raise SourceError("arxiv", "response is not valid XML") from exc
    publications: list[Publication] = []
    rejected = 0
    for entry in root.findall(f"{ATOM}entry"):
        try:
            publications.append(_parse_entry(entry))
        except (InvalidValueError, ValueError):  # malformed record: skip and count
            rejected += 1
            logger.warning("arxiv: rejected a malformed record", exc_info=True)
    return SourceResult(publications, rejected)


class ArxivSource:
    name = "arxiv"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    async def search(self, query: str, *, limit: int = 50) -> SourceResult:
        phrase = query.replace('"', " ").strip()
        params: dict[str, str | int] = {
            "search_query": f'all:"{phrase}"',
            "start": 0,
            "max_results": ensure_limit(limit),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        response = await self._fetcher.get(ARXIV_URL, params)
        return parse_feed(response.text)
