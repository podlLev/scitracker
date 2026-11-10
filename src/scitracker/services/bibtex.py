import itertools
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from scitracker.domain.publication import Author, Publication
from scitracker.domain.status import ReadingStatus
from scitracker.services.ports import ReadingListRepository

_SPECIAL = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_NOT_KEY_CHARS = re.compile(r"[^a-z0-9]")
_AND_WORD = re.compile(r"\band\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class BibtexExport:
    text: str
    entries: int


def escape(text: str) -> str:
    """Escape LaTeX special characters in a single pass (no double escaping)."""
    return "".join(_SPECIAL.get(char, char) for char in text)


def _raw(value: str) -> str:
    """DOI and URL stay as they are, only characters that break BibTeX braces are encoded."""
    return value.replace("{", "%7B").replace("}", "%7D").replace("\\", "%5C")


def _ascii(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _NOT_KEY_CHARS.sub("", folded.lower())


def _base_key(publication: Publication) -> str:
    surname = _ascii(publication.authors[0].name.split()[-1]) if publication.authors else ""
    year = str(publication.published_on.year) if publication.published_on else ""
    word = next((w for w in map(_ascii, publication.title.split()) if len(w) > 3), "")
    if surname or year or word:
        return f"{surname}{year}{word}"
    return f"pub{publication.id}" if publication.id is not None else "pub"


def _unique_key(base: str, used: set[str]) -> str:
    for number in itertools.count(1):
        key = base if number == 1 else f"{base}_{number}"
        if key not in used:
            used.add(key)
            return key
    raise AssertionError("unreachable")  # pragma: no cover


def _author(author: Author) -> str:
    text = escape(author.name)
    # A bare "and" would split the name in two: braces keep an organisation in one piece.
    return f"{{{text}}}" if _AND_WORD.search(author.name) else text


def format_entry(publication: Publication, key: str) -> str:
    fields: list[tuple[str, str]] = []
    if publication.authors:
        fields.append(("author", " and ".join(_author(a) for a in publication.authors)))
    fields.append(("title", "{" + escape(publication.title) + "}"))  # braces keep capitals
    if publication.published_on:
        fields.append(("year", str(publication.published_on.year)))
    if publication.doi:
        fields.append(("doi", _raw(publication.doi)))
    if publication.arxiv_id:
        fields.append(("eprint", publication.arxiv_id))
        fields.append(("archivePrefix", "arXiv"))
    if publication.url:
        fields.append(("url", _raw(publication.url)))
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
    return f"@misc{{{key},\n{body}\n}}"


def to_bibtex(publications: Iterable[Publication]) -> str:
    used: set[str] = set()
    entries = [format_entry(p, _unique_key(_base_key(p), used)) for p in publications]
    return "\n\n".join(entries) + "\n" if entries else ""


def export_reading_list(
    reading: ReadingListRepository, user_id: int, *, status: ReadingStatus | None = None
) -> BibtexExport:
    rows = reading.list_with_publications(user_id, status=status)
    return BibtexExport(to_bibtex(publication for _, publication in rows), len(rows))
