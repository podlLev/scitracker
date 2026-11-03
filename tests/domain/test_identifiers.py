import pytest

from scitracker.domain.errors import InvalidValueError
from scitracker.domain.identifiers import normalize_arxiv_id, normalize_doi


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1000/ABC", "10.1000/abc"),
        ("https://doi.org/10.1000/ABC", "10.1000/abc"),
        ("doi:10.1000/abc", "10.1000/abc"),
        ("  10.1000/abc  ", "10.1000/abc"),
    ],
)
def test_normalize_doi(raw: str, expected: str) -> None:
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "11.1000/abc", "10.1/abc"])
def test_normalize_doi_rejects_invalid(raw: str) -> None:
    with pytest.raises(InvalidValueError):
        normalize_doi(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2101.12345", "2101.12345"),
        ("arXiv:2101.12345v2", "2101.12345"),
        ("https://arxiv.org/abs/2101.12345v1", "2101.12345"),
        ("hep-th/9901001v3", "hep-th/9901001"),
    ],
)
def test_normalize_arxiv_id(raw: str, expected: str) -> None:
    assert normalize_arxiv_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "12345", "2101.1", "not-an-id"])
def test_normalize_arxiv_id_rejects_invalid(raw: str) -> None:
    with pytest.raises(InvalidValueError):
        normalize_arxiv_id(raw)
