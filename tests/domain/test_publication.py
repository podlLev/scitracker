import pytest

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.publication import Author, Publication


def test_identifiers_are_normalized() -> None:
    pub = Publication(
        title="  Attention  ",
        authors=[Author("Ashish Vaswani")],
        doi="https://doi.org/10.5555/ABC",
        arxiv_id="arXiv:1706.03762v5",
    )
    assert pub.title == "Attention"
    assert pub.doi == "10.5555/abc"
    assert pub.arxiv_id == "1706.03762"


def test_publication_without_doi_is_allowed() -> None:
    pub = Publication(title="Preprint", authors=[], arxiv_id="2101.12345")
    assert pub.doi is None


def test_publication_requires_an_identifier() -> None:
    with pytest.raises(InvalidValueError):
        Publication(title="No ids", authors=[])


def test_blank_title_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        Publication(title="   ", authors=[], doi="10.1000/abc")


def test_blank_author_name_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        Author("  ")


def test_arxiv_id_is_derived_from_arxiv_doi() -> None:
    pub = Publication(title="T", authors=[], doi="10.48550/arXiv.1706.03762")
    assert pub.arxiv_id == "1706.03762"


def test_explicit_arxiv_id_is_not_overridden_by_doi() -> None:
    pub = Publication(title="T", authors=[], doi="10.48550/arXiv.1706.03762", arxiv_id="2101.00001")
    assert pub.arxiv_id == "2101.00001"
