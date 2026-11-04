from dataclasses import dataclass
from datetime import date

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.identifiers import arxiv_id_from_doi, normalize_arxiv_id, normalize_doi
from scitracker.domain.validation import require_text


@dataclass(slots=True)
class Author:
    name: str
    id: int | None = None

    def __post_init__(self) -> None:
        self.name = require_text(self.name, "author name", max_length=300)


@dataclass(slots=True)
class Publication:
    title: str
    authors: list[Author]
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    published_on: date | None = None
    url: str | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        self.title = require_text(self.title, "title", max_length=1000)
        if self.doi is not None:
            self.doi = normalize_doi(self.doi)
        if self.arxiv_id is not None:
            self.arxiv_id = normalize_arxiv_id(self.arxiv_id)
        elif self.doi is not None:
            self.arxiv_id = arxiv_id_from_doi(self.doi)
        if self.doi is None and self.arxiv_id is None:
            raise InvalidValueError("publication must have a DOI or an arXiv ID")
